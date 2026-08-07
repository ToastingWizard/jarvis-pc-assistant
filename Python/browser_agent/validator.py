"""Pre-execution safety gate for browser action plans.

The validator runs *after* the planner produces a plan but *before* the
executor starts. It does two things:

1. **Shape validation** — every action is well-formed and well-typed.
2. **Risk flagging** — actions that match known-risky patterns are
   flipped to ``requires_confirmation=True`` *independently* of what the
   LLM said. This is the second line of defense (the planner prompt is
   the first): the LLM can be wrong or jailbroken, the validator
   cannot.

Pure module — no Playwright, no I/O. Trivially testable.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .types import BrowserAction, BrowserActionPlan, BrowserActionType


# Tokens in button / form-submit accessible names that should never run
# without a human in the loop. Lowercase, substring-matched.
_RISKY_NAME_TOKENS: tuple[str, ...] = (
    "delete",
    "remove",
    "pay",
    "purchase",
    "buy now",
    "checkout",
    "send",
    "submit order",
    "confirm purchase",
    "transfer",
    "wire",
    "close account",
    "deactivate",
    "sign out all",
    "log out all",
    "unsubscribe",
)

# URL fragments whose presence always means "be careful". Lowercase
# substring match against the *full* URL (including query string).
_RISKY_URL_FRAGMENTS: tuple[str, ...] = (
    "/checkout",
    "/payment",
    "/purchase",
    "/account/delete",
    "/account/close",
    "/signout",
    "/logout",
    "/transfer/",
    "/wire/",
    "delete_account=1",
)

# Folders the executor will refuse to write downloads to. The user's
# real Downloads folder is allowed (set in config); everything else on
# this list is a strong "no".
_DOWNLOAD_PATH_DENYLIST_PREFIXES: tuple[str, ...] = (
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/var/log",
    "/boot",
)


@dataclass
class ActionValidation:
    """Result of validating one action."""

    action: BrowserAction
    ok: bool
    reason: str = ""
    # When non-None, the validator flipped requires_confirmation on
    flipped_confirmation: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "action": self.action.to_dict(),
            "flipped_confirmation": self.flipped_confirmation,
        }


# --------------------------------------------------------------------------- shape


def _is_well_formed_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return True


def _looks_like_selector(value: str) -> bool:
    """Cheap heuristic: a selector should look like a CSS selector, a
    text/role query, or a URL. Anything starting with ``javascript:``,
    containing ``document.``, or matching a Playwright API call shape is
    rejected — the LLM is told to never emit those, but we re-check.
    """
    if not value:
        return False
    lower = value.strip().lower()
    if lower.startswith("javascript:"):
        return False
    bad_substrings = (
        "document.",
        "window.",
        "playwright.",
        "__import__",
        "eval(",
        "exec(",
        "subprocess",
    )
    for needle in bad_substrings:
        if needle in lower:
            return False
    return True


def _validate_shape(action: BrowserAction) -> str | None:
    """Return an error message if the action is malformed, else None."""
    t = action.type
    if t in (BrowserActionType.NAVIGATE, BrowserActionType.SAVE_PDF):
        if not _is_well_formed_url(action.target or ""):
            return f"{t.value} requires a well-formed http(s) URL, got {action.target!r}"
    elif t in (BrowserActionType.CLICK, BrowserActionType.DOUBLE_CLICK,
               BrowserActionType.RIGHT_CLICK, BrowserActionType.HOVER,
               BrowserActionType.FILL_FORM, BrowserActionType.SELECT_OPTION,
               BrowserActionType.CHECK, BrowserActionType.UNCHECK,
               BrowserActionType.SCROLL, BrowserActionType.SELECT_TEXT,
               BrowserActionType.SCREENSHOT):
        if not action.target:
            return f"{t.value} requires a non-empty target selector"
        if not _looks_like_selector(action.target):
            return f"{t.value} target looks unsafe: {action.target!r}"
    elif t == BrowserActionType.UPLOAD_FILE:
        if not action.target:
            return "upload_file requires a target (input selector)"
        if not action.value:
            return "upload_file requires a value (file path)"
        if not Path(str(action.value)).exists():
            return f"upload_file path does not exist: {action.value!r}"
    elif t == BrowserActionType.TYPE_TEXT:
        if not action.value and not action.target:
            return "type_text needs either value (text) or target (selector + value)"
    elif t == BrowserActionType.PRESS_KEY:
        if not action.value:
            return "press_key needs a value (key name)"
    elif t == BrowserActionType.DOWNLOAD:
        # value is the suggested filename; path may come from params.
        path = action.params.get("save_path")
        if path and not _is_safe_download_path(str(path)):
            return f"download save_path is not allowed: {path!r}"
    elif t == BrowserActionType.SWITCH_TAB:
        if not action.target and action.value is None:
            return "switch_tab needs a target (tab id) or value (ordinal)"
    elif t == BrowserActionType.NEW_TAB:
        # target (URL) is optional; if present it must be well-formed.
        if action.target and not _is_well_formed_url(action.target):
            return f"new_tab URL is not well-formed: {action.target!r}"
    elif t == BrowserActionType.WAIT_FOR:
        timeout = action.params.get("timeout_ms")
        if timeout is not None:
            try:
                ms = int(timeout)
            except (TypeError, ValueError):
                return "wait_for timeout_ms must be an integer"
            if ms < 0 or ms > 120_000:
                return "wait_for timeout_ms must be between 0 and 120000"
    return None


# ----------------------------------------------------------------------- risk

def _is_safe_download_path(path: str) -> bool:
    """A download path is allowed only if it's not under a system
    directory AND the parent directory already exists (we create the
    leaf, not the tree)."""
    try:
        p = Path(path).resolve()
    except Exception:
        return False
    s = str(p)
    for prefix in _DOWNLOAD_PATH_DENYLIST_PREFIXES:
        if s.startswith(prefix):
            return False
    parent = p.parent
    if not parent.exists():
        return False
    return True


def _selector_text_risky(selector: str) -> bool:
    """Does the selector text contain a risky button word?

    Catches things like ``button:has-text("Delete account")`` as well as
    plain ``text=Delete post`` or even ``a:has-text('Checkout')``.
    """
    if not selector:
        return False
    lower = selector.lower()
    return any(token in lower for token in _RISKY_NAME_TOKENS)


def _url_risky(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return any(frag in lower for frag in _RISKY_URL_FRAGMENTS)


# ----------------------------------------------------------- confirmations

_CONFIRMATION_REQUIRED_ACTIONS: frozenset[BrowserActionType] = frozenset({
    # These *always* require explicit confirmation regardless of the
    # LLM's flag — the user is sending data to a remote server.
    BrowserActionType.UPLOAD_FILE,
})


def _should_force_confirm(action: BrowserAction) -> tuple[bool, str]:
    """Return (force_confirm, reason). The validator flips confirmation
    on independently of the planner; this is the safety backbone."""
    if action.type in _CONFIRMATION_REQUIRED_ACTIONS:
        return True, f"action type {action.type.value} always requires user confirmation"
    if action.type in (BrowserActionType.CLICK, BrowserActionType.DOUBLE_CLICK, BrowserActionType.PRESS_KEY):
        if _selector_text_risky(action.target or ""):
            return True, f"selector text matches a risky action: {action.target!r}"
    if action.type == BrowserActionType.NAVIGATE:
        if _url_risky(action.target or ""):
            return True, f"URL looks risky: {action.target!r}"
    if action.type == BrowserActionType.FILL_FORM:
        # Filling a form by itself is fine, but if the field's accessible
        # name or surrounding selector mentions payment or account
        # deletion we ask first.
        if _selector_text_risky(action.target or ""):
            return True, f"form field is in a risky area: {action.target!r}"
    return False, ""


# --------------------------------------------------------------------- public


def validate_action(action: BrowserAction) -> ActionValidation:
    """Validate one action. Mutates ``action.requires_confirmation`` if
    the validator independently decides the action is risky — the
    planner's flag is preserved as a hint, never as the only signal."""
    shape_error = _validate_shape(action)
    if shape_error is not None:
        return ActionValidation(action=action, ok=False, reason=shape_error)

    force, reason = _should_force_confirm(action)
    flipped = False
    if force and not action.requires_confirmation:
        action.requires_confirmation = True
        action.reason = action.reason or reason
        flipped = True
    return ActionValidation(
        action=action,
        ok=True,
        reason=reason if force else "",
        flipped_confirmation=flipped,
    )


def validate_plan(plan: BrowserActionPlan) -> list[ActionValidation]:
    """Validate every action in a plan. Returns one result per action
    in order."""
    return [validate_action(a) for a in plan.actions]


def plan_has_confirmation_required(plan: BrowserActionPlan) -> bool:
    return any(a.requires_confirmation for a in plan.actions)


def first_confirmation_action(plan: BrowserActionPlan) -> BrowserAction | None:
    for a in plan.actions:
        if a.requires_confirmation:
            return a
    return None


# Convenience for the executor when it needs to know whether the
# *plan* is risky as a whole (used to drive the "do you want to proceed"
# banner that arms the existing pending_confirmation flow).
def risky_actions(plan: BrowserActionPlan) -> Iterable[BrowserAction]:
    return (a for a in plan.actions if a.requires_confirmation)
