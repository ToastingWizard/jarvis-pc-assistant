"""Dataclasses, enums, and small value types for the Browser Agent.

This module is intentionally dependency-free apart from stdlib so it can be
imported and tested without Playwright / a browser installed.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class BrowserActionType(str, enum.Enum):
    """Every action the Browser Agent can execute.

    The string values are the canonical tokens the LLM emits in its plan
    JSON and the validator/executor use to dispatch. Keep them stable —
    they form a public contract with the planner prompt.
    """

    # Navigation
    NAVIGATE = "navigate"
    NEW_TAB = "new_tab"
    CLOSE_TAB = "close_tab"
    SWITCH_TAB = "switch_tab"
    RELOAD = "reload"
    BACK = "back"
    FORWARD = "forward"

    # Interaction
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    HOVER = "hover"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    FILL_FORM = "fill_form"
    SELECT_OPTION = "select_option"
    CHECK = "check"
    UNCHECK = "uncheck"
    UPLOAD_FILE = "upload_file"
    SCROLL = "scroll"
    SELECT_TEXT = "select_text"

    # Reading
    READ_TEXT = "read_text"
    READ_TITLE = "read_title"
    READ_URL = "read_url"
    EXTRACT_LINKS = "extract_links"
    EXTRACT_TABLE = "extract_table"
    EXTRACT_FORM = "extract_form"
    EXTRACT_BUTTONS = "extract_buttons"
    GET_PAGE_INFO = "get_page_info"

    # Search & downloads
    SEARCH = "search"
    DOWNLOAD = "download"
    SAVE_PDF = "save_pdf"

    # Meta
    WAIT_FOR = "wait_for"
    SCREENSHOT = "screenshot"
    CONFIRM_REQUIRED = "confirm_required"
    NOOP = "noop"


@dataclass
class BrowserAction:
    """One step in a plan.

    ``target`` is interpreted per action type: for CLICK it's a CSS / text /
    role selector, for NAVIGATE it's a URL, for FILL_FORM it's a selector,
    for TYPE_TEXT ``value`` is the text, etc.  See ``executor.py`` for the
    per-action semantics.

    ``requires_confirmation`` is a hint set by the LLM; the validator may
    also flip it on independently for known-risky patterns (defense in
    depth).
    """

    type: BrowserActionType
    target: str | None = None
    value: Any = None
    params: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    reason: str | None = None  # human-readable why, surfaced in logs/UI

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "target": self.target,
            "value": self.value,
            "params": self.params,
            "requires_confirmation": self.requires_confirmation,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrowserAction":
        if not isinstance(data, dict):
            raise ValueError(f"BrowserAction.from_dict expected dict, got {type(data).__name__}")
        type_str = data.get("type")
        if not type_str:
            raise ValueError("BrowserAction missing 'type'")
        try:
            action_type = BrowserActionType(type_str)
        except ValueError as exc:
            raise ValueError(f"Unknown BrowserActionType: {type_str!r}") from exc
        return cls(
            type=action_type,
            target=data.get("target"),
            value=data.get("value"),
            params=dict(data.get("params") or {}),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            reason=data.get("reason"),
        )


@dataclass
class BrowserActionPlan:
    """The full plan the LLM returns.

    ``thought`` is the model's one-sentence reasoning — surfaced in logs
    and the React UI so the user can see *why* the agent is about to do
    what it's about to do.
    """

    thought: str = ""
    actions: list[BrowserAction] = field(default_factory=list)
    raw_response: str = ""  # unparsed LLM output, for debugging

    def to_dict(self) -> dict[str, Any]:
        return {
            "thought": self.thought,
            "actions": [a.to_dict() for a in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrowserActionPlan":
        if not isinstance(data, dict):
            raise ValueError(f"BrowserActionPlan.from_dict expected dict, got {type(data).__name__}")
        actions_raw = data.get("actions") or []
        if not isinstance(actions_raw, list):
            raise ValueError("BrowserActionPlan 'actions' must be a list")
        actions: list[BrowserAction] = []
        for item in actions_raw:
            if isinstance(item, BrowserAction):
                actions.append(item)
            elif isinstance(item, dict):
                try:
                    actions.append(BrowserAction.from_dict(item))
                except ValueError:
                    # Skip malformed entries rather than failing the whole plan;
                    # the LLM occasionally emits noise alongside valid actions.
                    continue
        return cls(
            thought=str(data.get("thought") or ""),
            actions=actions,
        )


@dataclass
class BrowserActionResult:
    """Outcome of executing one action."""

    ok: bool
    action: BrowserAction
    message: str = ""
    data: Any = None  # action-specific payload (e.g. list of links, page text)
    error: str | None = None
    screenshot_path: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action.to_dict(),
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "screenshot_path": self.screenshot_path,
            "duration_ms": self.duration_ms,
        }


@dataclass
class PageSnapshot:
    """Structured view of a page, used by the planner and persisted in memory.

    A snapshot is plain data so it can be serialised to JSON, sent to the
    LLM, and stored across restarts. It deliberately does *not* hold any
    Playwright handles.
    """

    url: str = ""
    title: str = ""
    visible_text: str = ""
    links: list[dict[str, str]] = field(default_factory=list)  # [{"text":..., "href":...}]
    forms: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[dict[str, str]] = field(default_factory=list)
    scroll_position: int = 0
    selected_text: str = ""
    captured_at: str = ""

    def truncate(self, max_text_chars: int = 6000) -> "PageSnapshot":
        """Return a copy with very long text fields truncated.

        Snapshots are sent to the LLM, so we cap their size to keep prompts
        well-bounded. The full text is still in memory / on disk.
        """
        out = PageSnapshot(
            url=self.url,
            title=self.title,
            visible_text=self.visible_text[:max_text_chars],
            links=self.links[:50],
            forms=self.forms[:10],
            tables=self.tables[:5],
            buttons=self.buttons[:30],
            scroll_position=self.scroll_position,
            selected_text=self.selected_text[:2000],
            captured_at=self.captured_at,
        )
        if len(self.visible_text) > max_text_chars:
            out.visible_text += f"\n... [truncated, full text is {len(self.visible_text)} chars]"
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "visible_text": self.visible_text,
            "links": self.links,
            "forms": self.forms,
            "tables": self.tables,
            "buttons": self.buttons,
            "scroll_position": self.scroll_position,
            "selected_text": self.selected_text,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PageSnapshot":
        if not isinstance(data, dict):
            return cls()
        return cls(
            url=str(data.get("url") or ""),
            title=str(data.get("title") or ""),
            visible_text=str(data.get("visible_text") or ""),
            links=list(data.get("links") or []),
            forms=list(data.get("forms") or []),
            tables=list(data.get("tables") or []),
            buttons=list(data.get("buttons") or []),
            scroll_position=int(data.get("scroll_position") or 0),
            selected_text=str(data.get("selected_text") or ""),
            captured_at=str(data.get("captured_at") or ""),
        )


@dataclass
class TabInfo:
    """Lightweight metadata about one open tab."""

    tab_id: str
    page_id: int  # Playwright page index inside the context, may be reused
    url: str = ""
    title: str = ""
    is_active: bool = False
    history: list[str] = field(default_factory=list)  # urls in order
    history_index: int = -1  # pointer into history
    last_snapshot: PageSnapshot | None = None
    last_action: str = ""
    opened_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "page_id": self.page_id,
            "url": self.url,
            "title": self.title,
            "is_active": self.is_active,
            "history": self.history,
            "history_index": self.history_index,
            "last_snapshot": self.last_snapshot.to_dict() if self.last_snapshot else None,
            "last_action": self.last_action,
            "opened_at": self.opened_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TabInfo":
        if not isinstance(data, dict):
            return cls(tab_id="", page_id=0)
        snap_raw = data.get("last_snapshot")
        snap = PageSnapshot.from_dict(snap_raw) if isinstance(snap_raw, dict) else None
        return cls(
            tab_id=str(data.get("tab_id") or ""),
            page_id=int(data.get("page_id") or 0),
            url=str(data.get("url") or ""),
            title=str(data.get("title") or ""),
            is_active=bool(data.get("is_active", False)),
            history=list(data.get("history") or []),
            history_index=int(data.get("history_index", -1)),
            last_snapshot=snap,
            last_action=str(data.get("last_action") or ""),
            opened_at=str(data.get("opened_at") or ""),
        )


@dataclass
class DownloadInfo:
    """Result of a DOWNLOAD action."""

    suggested_filename: str = ""
    save_path: str = ""
    completed: bool = False
    error: str | None = None
    cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggested_filename": self.suggested_filename,
            "save_path": self.save_path,
            "completed": self.completed,
            "error": self.error,
            "cancelled": self.cancelled,
        }
