"""LLM planner — converts a user request + page snapshot into a
:class:`BrowserActionPlan`.

Design
------
* The planner is a **pure function** (no Playwright, no side effects) so
  it can be unit-tested trivially.
* It builds a structured prompt that gives the LLM everything it needs:
  the user request, the current page state (truncated), available
  actions, and output-format instructions.
* The LLM returns JSON; ``parse_plan`` extracts a
  :class:`BrowserActionPlan` with robust fallbacks (fenced code blocks,
  partial JSON, etc.).
* When no AI backend is reachable, ``reflexive_plan`` provides a
  deterministic "best-effort" plan for simple patterns the executor can
  handle without intelligence (open a URL, search a site, scroll, etc.).
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .types import BrowserAction, BrowserActionPlan, BrowserActionType
from .memory import BrowserMemory
from .search import build_search_url, parse_search_command


# ---------------------------------------------------------------------------
# System prompt for the planner LLM
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a browser automation planner. Given a user request and the current
page state, produce a JSON plan of browser actions.

OUTPUT FORMAT — return ONLY a JSON object (no markdown, no prose):
{
  "thought": "one sentence explaining what you are about to do",
  "actions": [
    {"type": "<action_type>", "target": "<selector or URL>", "value": "<text or payload>", "params": {}}
  ]
}

AVAILABLE ACTION TYPES:
  NAVIGATE      — target: URL (http/https)
  NEW_TAB       — target: URL (optional)
  CLOSE_TAB     — target: tab id or ordinal (value)
  SWITCH_TAB    — target: tab id or value: ordinal (1-based)
  RELOAD        — no target needed
  BACK          — no target needed
  FORWARD       — no target needed
  CLICK         — target: CSS selector, text="...", or role="..." query
  DOUBLE_CLICK  — target: selector
  HOVER         — target: selector
  TYPE_TEXT     — target: selector (optional), value: text to type
  PRESS_KEY     — value: key name (Enter, Tab, Escape, ArrowDown, etc.)
  FILL_FORM     — target: selector, value: text
  SELECT_OPTION — target: selector, value: option value
  CHECK         — target: checkbox selector
  UNCHECK       — target: checkbox selector
  UPLOAD_FILE   — target: input selector, value: file path
  SCROLL        — target: selector (optional), params: {direction: "down"|"up"|"top"|"bottom", amount: pixels}
  SELECT_TEXT   — params: {start: N, end: N}
  READ_TEXT      — no target needed
  READ_TITLE     — no target needed
  READ_URL       — no target needed
  EXTRACT_LINKS  — no target needed
  EXTRACT_TABLE  — no target needed
  EXTRACT_FORM   — no target needed
  EXTRACT_BUTTONS — no target needed
  GET_PAGE_INFO   — no target needed
  SEARCH        — value: site name, target: query (or params: {site, query})
  DOWNLOAD      — target: selector, value: filename
  SAVE_PDF      — value: filename
  WAIT_FOR      — target: selector, params: {timeout_ms: N}
  SCREENSHOT    — value: filename (optional)
  CONFIRM_REQUIRED — for destructive actions (clicking "delete", etc.)

RULES:
- Never emit more than 6 actions per plan.
- Prefer semantic selectors (text="Login button", role="link") over CSS.
- If the user asks to "search X on Y", emit a single SEARCH action.
- If the user asks to "open URL", emit a single NAVIGATE action.
- If the user asks to "read" or "what does the page say", emit READ_TEXT.
- If the user asks to "click X", emit a CLICK action with text="X".
- If the user asks to "go back", emit BACK.
- Set requires_confirmation=true for any destructive action.
"""

_ACTION_TYPES_BLOCK = "\n".join(f"  {t.value}" for t in BrowserActionType)


def _build_prompt(
    user_request: str,
    snapshot: Any | None = None,
    tabs: list[dict[str, Any]] | None = None,
) -> str:
    """Build the full prompt for the planner LLM."""
    parts = [_SYSTEM_PROMPT]

    if snapshot is not None:
        snap_text = (
            f"CURRENT PAGE:\n"
            f"  URL: {snapshot.url}\n"
            f"  Title: {snapshot.title}\n"
            f"  Text (truncated): {snapshot.visible_text[:3000]}\n"
        )
        if snapshot.links:
            link_lines = [
                f"  {i+1}. [{l.get('text', '')}]({l.get('href', '')})"
                for i, l in enumerate(snapshot.links[:20])
            ]
            snap_text += "  Links:\n" + "\n".join(link_lines) + "\n"
        if snapshot.buttons:
            btn_lines = [
                f"  - {b.get('text', '')} ({b.get('tag', '')})"
                for b in snapshot.buttons[:15]
            ]
            snap_text += "  Buttons:\n" + "\n".join(btn_lines) + "\n"
        if snapshot.forms:
            snap_text += f"  Forms: {len(snapshot.forms)} form(s) on page\n"
        parts.append(snap_text)

    if tabs:
        tab_lines = [
            f"  Tab {i+1}: {t.get('title', t.get('url', 'untitled'))}"
            for i, t in enumerate(tabs[:5])
        ]
        parts.append("OPEN TABS:\n" + "\n".join(tab_lines))

    parts.append(f"USER REQUEST: {user_request}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# JSON extraction (robust)
# ---------------------------------------------------------------------------

def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from possibly-fenced LLM output."""
    text = text.strip()
    if not text:
        return None

    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    # Find first { ... }
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = -1  # try next { if any

    # Last resort: try the whole text
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def parse_plan(raw_text: str) -> BrowserActionPlan:
    """Parse LLM output into a :class:`BrowserActionPlan`.

    Handles fenced code blocks, partial JSON, and the occasional
    prose-before-JSON pattern the LLMs sometimes emit.
    """
    obj = _extract_json_object(raw_text)
    if obj is None:
        return BrowserActionPlan(thought="", raw_response=raw_text)

    thought = str(obj.get("thought") or "")
    actions_raw = obj.get("actions") or []
    if not isinstance(actions_raw, list):
        actions_raw = []

    actions: list[BrowserAction] = []
    for item in actions_raw:
        if not isinstance(item, dict):
            continue
        try:
            action = BrowserAction.from_dict(item)
            actions.append(action)
        except (ValueError, KeyError):
            continue

    plan = BrowserActionPlan(
        thought=thought,
        actions=actions,
        raw_response=raw_text,
    )
    return plan


# ---------------------------------------------------------------------------
# Deterministic reflexive fallback (no LLM needed)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+")
_SEARCH_PATTERNS: list[tuple[re.Pattern, str, str]] = []  # filled below


def reflexive_plan(
    user_request: str,
    snapshot: Any | None = None,
) -> BrowserActionPlan | None:
    """Try to produce a plan without the LLM.

    Returns ``None`` if the request is too ambiguous for deterministic
    handling. The caller should then fall back to the LLM planner.
    """
    text = user_request.strip()
    lower = text.lower()

    # "go to <url>" / "open <url>" / bare URL
    if any(lower.startswith(p) for p in ("go to ", "open ", "navigate to ", "navigate ")):
        url_match = _URL_RE.search(text)
        if url_match:
            url = url_match.group(0)
            return BrowserActionPlan(
                thought=f"Navigating to {url}",
                actions=[BrowserAction(type=BrowserActionType.NAVIGATE, target=url)],
            )
        # Bare domain like "open google.com"
        domain_match = re.search(r"([a-z0-9][-a-z0-9]*\.[a-z]{2,}\S*)", text)
        if domain_match:
            url = "https://" + domain_match.group(1)
            return BrowserActionPlan(
                thought=f"Navigating to {url}",
                actions=[BrowserAction(type=BrowserActionType.NAVIGATE, target=url)],
            )

    # Bare URL anywhere
    url_match = _URL_RE.search(text)
    if url_match and len(text) < 80:
        url = url_match.group(0)
        return BrowserActionPlan(
            thought=f"Navigating to {url}",
            actions=[BrowserAction(type=BrowserActionType.NAVIGATE, target=url)],
        )

    # Search commands: "search X on Y", "google X", etc.
    search = parse_search_command(text)
    if search:
        site, query = search
        return BrowserActionPlan(
            thought=f"Searching {site} for '{query}'",
            actions=[
                BrowserAction(
                    type=BrowserActionType.SEARCH,
                    target=query,
                    value=site,
                )
            ],
        )

    # Simple navigation
    if lower in ("back", "go back"):
        return BrowserActionPlan(
            thought="Going back",
            actions=[BrowserAction(type=BrowserActionType.BACK)],
        )
    if lower in ("forward", "go forward"):
        return BrowserActionPlan(
            thought="Going forward",
            actions=[BrowserAction(type=BrowserActionType.FORWARD)],
        )
    if lower in ("reload", "refresh") or lower.startswith("reload ") or lower.startswith("refresh "):
        return BrowserActionPlan(
            thought="Reloading page",
            actions=[BrowserAction(type=BrowserActionType.RELOAD)],
        )
    if lower in ("read page", "read text", "read", "what does it say", "what's on the page", "whats on the page"):
        return BrowserActionPlan(
            thought="Reading page content",
            actions=[BrowserAction(type=BrowserActionType.READ_TEXT)],
        )
    if lower in ("read title", "what's the title", "whats the title", "page title"):
        return BrowserActionPlan(
            thought="Reading page title",
            actions=[BrowserAction(type=BrowserActionType.READ_TITLE)],
        )
    if lower in ("read url", "what url", "what's the url", "whats the url", "current url"):
        return BrowserActionPlan(
            thought="Reading current URL",
            actions=[BrowserAction(type=BrowserActionType.READ_URL)],
        )
    if lower in ("extract links", "get links", "list links", "show links"):
        return BrowserActionPlan(
            thought="Extracting page links",
            actions=[BrowserAction(type=BrowserActionType.EXTRACT_LINKS)],
        )
    if lower in ("extract forms", "get forms", "show forms"):
        return BrowserActionPlan(
            thought="Extracting page forms",
            actions=[BrowserAction(type=BrowserActionType.EXTRACT_FORM)],
        )
    if lower in ("extract buttons", "get buttons", "show buttons", "list buttons"):
        return BrowserActionPlan(
            thought="Extracting page buttons",
            actions=[BrowserAction(type=BrowserActionType.EXTRACT_BUTTONS)],
        )

    # Scroll
    if "scroll" in lower:
        direction = "down"
        if "up" in lower:
            direction = "up"
        elif "top" in lower or "to top" in lower:
            direction = "top"
        elif "bottom" in lower or "to bottom" in lower:
            direction = "bottom"
        return BrowserActionPlan(
            thought=f"Scrolling {direction}",
            actions=[
                BrowserAction(
                    type=BrowserActionType.SCROLL,
                    params={"direction": direction},
                )
            ],
        )

    # Screenshot
    if "screenshot" in lower or "take a picture" in lower:
        return BrowserActionPlan(
            thought="Taking screenshot",
            actions=[BrowserAction(type=BrowserActionType.SCREENSHOT)],
        )

    # Click by text — "click <text>"
    click_match = re.match(r"(?:please\s+)?click\s+[\"']?(.+?)[\"']?\s*$", lower)
    if click_match:
        text_to_find = click_match.group(1).strip().rstrip('"').rstrip("'")
        return BrowserActionPlan(
            thought=f"Clicking '{text_to_find}'",
            actions=[
                BrowserAction(
                    type=BrowserActionType.CLICK,
                    target=f'text="{text_to_find}"',
                )
            ],
        )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_actions(
    user_request: str,
    config: dict[str, Any] | None = None,
    memory: BrowserMemory | None = None,
    log: Callable[[str], None] | None = None,
) -> BrowserActionPlan:
    """Produce a plan for ``user_request``.

    Tries the deterministic reflexive planner first. If that returns
    ``None``, calls the LLM via :mod:`ai_client`. Returns an empty plan
    if no AI backend is reachable.
    """
    log = log or (lambda text: None)
    snapshot = memory.get_current_snapshot() if memory else None
    tabs = [t.to_dict() for t in memory.list_tabs()] if memory else []

    # 1. Try reflexive (no LLM needed)
    plan = reflexive_plan(user_request, snapshot)
    if plan is not None:
        log(f"Browser plan (reflexive): {plan.thought} [{len(plan.actions)} actions]")
        return plan

    # 2. Call the LLM
    try:
        from ai_client import query_ai, AIClientError
    except ImportError:
        log("Browser planner: ai_client not importable")
        return BrowserActionPlan(thought="", raw_response="")

    prompt = _build_prompt(user_request, snapshot, tabs)
    try:
        raw = query_ai(
            prompt,
            config=config,
            response_format="json",
            timeout=30,
            log=log,
        )
        plan = parse_plan(raw)
        log(f"Browser plan (LLM): {plan.thought} [{len(plan.actions)} actions]")
        return plan
    except AIClientError as exc:
        log(f"Browser planner: AI unavailable ({exc})")
        return BrowserActionPlan(
            thought=f"AI unavailable for planning: {exc}",
            raw_response=str(exc),
        )
    except Exception as exc:
        log(f"Browser planner: unexpected error ({exc})")
        return BrowserActionPlan(
            thought=f"Planning error: {exc}",
            raw_response=str(exc),
        )
