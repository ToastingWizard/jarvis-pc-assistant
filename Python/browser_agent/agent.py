"""BrowserAgent — the orchestrator callers actually use.

Wires the four pieces together:

    planner   →  turn a user request into a :class:`BrowserActionPlan`
    validator →  shape + risk gate on every action before it runs
    executor  →  Playwright lifecycle + per-action execution
    memory    →  persistent tab / snapshot / action state

Public API (all blocking, safe to call from NaiTRO's main thread):

    run(user_request)     →  plan, validate, confirm, execute, summarize
    navigate(url)         →  one-shot NAVIGATE convenience
    execute_action(dict)  →  execute a single action (for the WebView/UI)
    tabs()                →  current tab list
    current_page()        →  current page snapshot
    browser_status()      →  running flag + tabs + snapshot + last action
    start_browser()       →  launch the browser (idempotent)
    close_browser()       →  tear down everything (no orphans)
    confirm() / cancel()  →  resume / abort a pending confirmation
"""
from __future__ import annotations

from typing import Any, Callable

from .executor import BrowserExecutor, PlaywrightNotInstalled
from .memory import BrowserMemory
from .planner import plan_actions
from .types import (
    BrowserAction,
    BrowserActionPlan,
    BrowserActionResult,
    BrowserActionType,
    PageSnapshot,
)
from .validator import first_confirmation_action, validate_action, validate_plan

# Confirmation phrases the agent understands when a plan is paused.
_CONFIRM_PHRASES = frozenset({"confirm", "yes", "yes confirm", "do it", "confirmed", "proceed", "continue", "go ahead"})
_CANCEL_PHRASES = frozenset({"cancel", "no", "stop", "abort", "never mind", "nevermind", "no thanks"})

# Interaction action types get a single snapshot+retry on failure. Reading
# and meta actions are excluded (a failed read is just a failed read).
_RETRYABLE_TYPES = frozenset({
    BrowserActionType.CLICK,
    BrowserActionType.DOUBLE_CLICK,
    BrowserActionType.RIGHT_CLICK,
    BrowserActionType.HOVER,
    BrowserActionType.TYPE_TEXT,
    BrowserActionType.FILL_FORM,
    BrowserActionType.SELECT_OPTION,
    BrowserActionType.CHECK,
    BrowserActionType.UNCHECK,
    BrowserActionType.UPLOAD_FILE,
    BrowserActionType.SCROLL,
})


class BrowserAgent:
    """One browser agent per NaiTRO engine. Lazily spawns a browser."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        log: Callable[[str], None] | None = None,
    ):
        self._config = config or {}
        self._log = log or (lambda text: None)
        self._memory = BrowserMemory()
        self._executor: BrowserExecutor | None = None
        self._pending_plan: BrowserActionPlan | None = None
        self._last_run: dict[str, Any] | None = None

    # ------------------------------------------------------------------ lifecycle

    def _get_executor(self) -> BrowserExecutor:
        """Create the executor lazily on first use."""
        if self._executor is None:
            self._executor = BrowserExecutor(
                config=self._config, memory=self._memory, log=self._log
            )
        return self._executor

    def start_browser(self) -> dict[str, Any]:
        try:
            self._get_executor().start()
            self._log("Browser launched")
            return {"ok": True, "message": "Browser launched"}
        except PlaywrightNotInstalled as exc:
            self._log(f"Browser unavailable: {exc}")
            return {"ok": False, "message": str(exc), "error": str(exc)}

    def close_browser(self) -> dict[str, Any]:
        if self._executor is not None:
            try:
                self._executor.close()
            except Exception as exc:
                self._log(f"Browser close error: {exc}")
        self._executor = None
        self._pending_plan = None
        self._log("Browser closed")
        return {"ok": True, "message": "Browser closed"}

    def browser_status(self) -> dict[str, Any]:
        running = self._executor is not None and self._executor.is_alive()
        snapshot = self._memory.get_current_snapshot()
        return {
            "running": running,
            "tabs": [t.to_dict() for t in self._memory.list_tabs()],
            "current_snapshot": snapshot.to_dict() if snapshot else None,
            "last_action": self._memory.last_action(),
            "pending_confirmation": (
                self._pending_plan.to_dict() if self._pending_plan is not None else None
            ),
        }

    # ------------------------------------------------------------------ direct actions

    def navigate(self, url: str) -> dict[str, Any]:
        """One-shot convenience: open a URL in the browser."""
        action = BrowserAction(type=BrowserActionType.NAVIGATE, target=url)
        results = self._execute_all([action])
        return self._result_dict(results, thought=f"Navigating to {url}")

    def execute_action(self, action_dict: dict[str, Any]) -> dict[str, Any]:
        """Execute a single action from a serialisable dict. This is what
        the WebView / React UI calls when the user drives the browser by
        hand."""
        try:
            action = BrowserAction.from_dict(action_dict)
        except ValueError as exc:
            return {"ok": False, "message": str(exc), "error": str(exc)}
        result = self._execute_single(action)
        return self._result_dict([result], thought="")

    # ------------------------------------------------------------------ main entry

    def run(self, user_request: str) -> dict[str, Any]:
        """Plan and execute a user request. Safe to call repeatedly."""
        request = (user_request or "").strip()

        # 1. Handle a pending confirmation first ("yes"/"no" to a paused plan).
        if self._pending_plan is not None:
            return self._handle_pending_response(request)

        if not request:
            return {"ok": False, "message": "Empty request"}

        # 2. Build a plan (reflexive first, then LLM).
        plan = plan_actions(
            user_request=request,
            config=self._config,
            memory=self._memory,
            log=self._log,
        )
        if not plan.actions:
            return {
                "ok": False,
                "message": "I couldn't plan that request. Try being more specific, "
                "e.g. 'open https://example.com' or 'search python on youtube'.",
                "thought": plan.thought,
            }

        # 3. Validate.
        results = validate_plan(plan)
        if any(not r.ok for r in results):
            bad = next((r for r in results if not r.ok), None)
            return {
                "ok": False,
                "message": f"Refused action: {bad.action.type.value} — {bad.reason}",
                "error": bad.reason,
                "thought": plan.thought,
            }

        # 4. Confirmation gate.
        first_risky = first_confirmation_action(plan)
        if first_risky is not None:
            return self._pause_for_confirmation(plan, first_risky)

        # 5. Execute.
        return self._execute_plan(plan)

    def confirm(self) -> dict[str, Any]:
        if self._pending_plan is None:
            return {"ok": False, "message": "Nothing to confirm"}
        plan = self._pending_plan
        self._pending_plan = None
        return self._execute_plan(plan)

    def cancel(self) -> dict[str, Any]:
        self._pending_plan = None
        return {"ok": True, "message": "Cancelled"}

    # ------------------------------------------------------------------ internals

    def _handle_pending_response(self, request: str) -> dict[str, Any]:
        lower = request.strip().lower()
        if lower in _CONFIRM_PHRASES:
            return self.confirm()
        if lower in _CANCEL_PHRASES:
            return self.cancel()
        # Unrelated command while a confirmation is pending: keep it
        # pending (matches NaiTRO's pending_confirmation behaviour) and
        # surface what's being asked.
        pending = self._pending_plan
        risky = first_confirmation_action(pending)
        return {
            "ok": False,
            "message": (
                f"A browser action needs your confirmation first: "
                f"{risky.type.value} {risky.target or ''}. "
                f"Say 'yes' to proceed or 'no' to cancel."
            ),
            "confirmation_required": True,
            "pending_action": risky.to_dict() if risky else None,
        }

    def _pause_for_confirmation(
        self, plan: BrowserActionPlan, risky: BrowserAction
    ) -> dict[str, Any]:
        # Execute the safe prefix, then pause before the risky action.
        prefix = plan.actions[: plan.actions.index(risky)]
        self._pending_plan = plan
        results = self._execute_all(prefix)
        return {
            "ok": False,
            "message": (
                f"Confirmation required: {risky.type.value} {risky.target or ''} — "
                f"{risky.reason or 'this looks risky'}."
            ),
            "confirmation_required": True,
            "pending_action": risky.to_dict(),
            "thought": plan.thought,
            "actions": [r.to_dict() for r in results],
        }

    def _execute_plan(self, plan: BrowserActionPlan) -> dict[str, Any]:
        results = self._execute_all(plan.actions)
        return self._result_dict(results, plan.thought)

    def _execute_all(self, actions: list[BrowserAction]) -> list[BrowserActionResult]:
        results: list[BrowserActionResult] = []
        for action in actions:
            result = self._execute_single(action)
            results.append(result)
            if not result.ok and result.error:
                # Stop at the first failure so the user sees a clear,
                # ordered trail instead of a cascade of errors.
                self._log(f"Browser action failed: {result.message or result.error}")
                break
        return results

    def _execute_single(self, action: BrowserAction) -> BrowserActionResult:
        executor = self._get_executor()
        result = executor.execute(action)
        # Intelligent retry: an interaction that failed may just need a
        # fresher page (the DOM changed between snapshot and click).
        if (
            not result.ok
            and action.type in _RETRYABLE_TYPES
            and not (isinstance(result.error, str) and "Playwright" in result.error)
        ):
            refreshed = executor.refresh_snapshot()
            if refreshed is not None and refreshed.ok:
                self._log(f"Retrying {action.type.value} after snapshot refresh")
                result = executor.execute(action)
        return result

    def _result_dict(
        self, results: list[BrowserActionResult], thought: str
    ) -> dict[str, Any]:
        ok = all(r.ok for r in results)
        errors = [r.error for r in results if r.error]
        snapshot = self._memory.get_current_snapshot()
        last = results[-1] if results else None
        # Compose a readable message from the trailing result.
        message = last.message if last else "Done"
        if not ok and errors:
            message = errors[-1] or message
        out: dict[str, Any] = {
            "ok": ok,
            "message": message,
            "thought": thought,
            "actions": [r.to_dict() for r in results],
            "error": errors[-1] if errors else None,
            "snapshot": snapshot.to_dict() if snapshot else None,
        }
        self._last_run = out
        return out

    def tabs(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._memory.list_tabs()]

    def current_page(self) -> dict[str, Any] | None:
        snap = self._memory.get_current_snapshot()
        return snap.to_dict() if snap else None

    def last_run(self) -> dict[str, Any] | None:
        return self._last_run
