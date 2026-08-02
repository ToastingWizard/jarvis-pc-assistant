"""Browser Memory — persistent state about open tabs, history, and pages.

This module is *pure data* (no Playwright imports). It is thread-safe and
optionally persists to a JSON file on disk so "previous page" and
"current tab" survive across NaiTRO restarts.

The in-memory shape:
    tabs:            dict[tab_id, TabInfo]
    current_tab_id:  str | None
    tab_snapshots:   dict[tab_id, list[PageSnapshot]]   # most recent first
    last_action:     str                                # one-line description
    last_extraction: Any                                # result of last READ_TEXT etc.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import PageSnapshot, TabInfo

# Cap how many snapshots per tab we keep in memory and on disk. Older
# snapshots are dropped (FIFO). 5 is enough for "compare with the page
# before that" without bloating the JSON file.
MAX_SNAPSHOTS_PER_TAB = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrowserMemory:
    """Thread-safe browser state, with optional disk persistence."""

    def __init__(self, persist_path: Path | None = None):
        self._lock = threading.RLock()
        self._tabs: dict[str, TabInfo] = {}
        self._current_tab_id: str | None = None
        self._tab_snapshots: dict[str, list[PageSnapshot]] = {}
        self._last_action: str = ""
        self._last_extraction: Any = None
        self._persist_path: Path | None = None
        if persist_path is not None:
            self.set_persist_path(persist_path)
        else:
            self._restore_if_present()

    # ------------------------------------------------------------------ persistence

    def set_persist_path(self, path: Path) -> None:
        """Configure where memory is saved/loaded.

        Setting a path *replaces* the auto-restore from
        ``%APPDATA%/NaiTRO/browser_memory.json``; pass the same path on
        every launch to get continuity.
        """
        self._persist_path = Path(path)
        self._restore_if_present()

    def _default_persist_path(self) -> Path | None:
        """Best-effort path for auto-restore on launch.

        Windows: ``%APPDATA%/NaiTRO/browser_memory.json``
        macOS:   ``~/Library/Application Support/NaiTRO/browser_memory.json``
        Linux:   ``$XDG_DATA_HOME/NaiTRO/browser_memory.json`` or ``~/.local/share/...``
        """
        try:
            if os.name == "nt":
                base = os.environ.get("APPDATA")
                if not base:
                    return None
                return Path(base) / "NaiTRO" / "browser_memory.json"
            xdg = os.environ.get("XDG_DATA_HOME")
            if xdg:
                return Path(xdg) / "NaiTRO" / "browser_memory.json"
            home = Path.home()
            if home.exists():
                return home / ".local" / "share" / "NaiTRO" / "browser_memory.json"
        except Exception:
            return None
        return None

    def _restore_if_present(self) -> None:
        path = self._persist_path or self._default_persist_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        with self._lock:
            self._tabs = {}
            for tab_id, tab_data in (data.get("tabs") or {}).items():
                self._tabs[str(tab_id)] = TabInfo.from_dict(tab_data)
            self._current_tab_id = data.get("current_tab_id")
            self._tab_snapshots = {}
            for tab_id, snaps in (data.get("tab_snapshots") or {}).items():
                self._tab_snapshots[str(tab_id)] = [
                    PageSnapshot.from_dict(s) for s in (snaps or [])
                ]
            self._last_action = str(data.get("last_action") or "")
            self._last_extraction = data.get("last_extraction")

    def _save_locked(self) -> None:
        """Caller must hold ``self._lock``."""
        path = self._persist_path or self._default_persist_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "tabs": {tid: t.to_dict() for tid, t in self._tabs.items()},
                "current_tab_id": self._current_tab_id,
                "tab_snapshots": {
                    tid: [s.to_dict() for s in snaps]
                    for tid, snaps in self._tab_snapshots.items()
                },
                "last_action": self._last_action,
                "last_extraction": self._last_extraction,
                "saved_at": _now_iso(),
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except Exception:
            # Persistence is best-effort; never let a save error crash the
            # agent. The in-memory copy is still authoritative.
            pass

    def save(self) -> None:
        """Force a save right now (otherwise saves are debounced to mutating calls)."""
        with self._lock:
            self._save_locked()

    # ------------------------------------------------------------------ tabs

    def new_tab(self, page_id: int, url: str = "") -> str:
        """Register a new tab and return its id."""
        tab_id = uuid.uuid4().hex
        with self._lock:
            info = TabInfo(
                tab_id=tab_id,
                page_id=page_id,
                url=url,
                history=[url] if url else [],
                history_index=0 if url else -1,
                opened_at=_now_iso(),
            )
            self._tabs[tab_id] = info
            self._tab_snapshots[tab_id] = []
            self._current_tab_id = tab_id
            self._mark_active_locked(tab_id)
            self._save_locked()
        return tab_id

    def close_tab(self, tab_id: str) -> bool:
        with self._lock:
            if tab_id not in self._tabs:
                return False
            self._tabs.pop(tab_id, None)
            self._tab_snapshots.pop(tab_id, None)
            if self._current_tab_id == tab_id:
                self._current_tab_id = next(iter(self._tabs), None)
                if self._current_tab_id is not None:
                    self._tabs[self._current_tab_id].is_active = True
            self._save_locked()
        return True

    def set_current_tab(self, tab_id: str) -> bool:
        with self._lock:
            if tab_id not in self._tabs:
                return False
            self._mark_active_locked(tab_id)
            self._save_locked()
        return True

    def _mark_active_locked(self, tab_id: str) -> None:
        """Caller must hold ``self._lock``."""
        for tid, info in self._tabs.items():
            info.is_active = tid == tab_id

    def list_tabs(self) -> list[TabInfo]:
        with self._lock:
            # Return active tab first, then others in insertion order
            tabs = list(self._tabs.values())
        tabs.sort(key=lambda t: (not t.is_active, t.opened_at))
        return tabs

    def get_tab(self, tab_id: str) -> TabInfo | None:
        with self._lock:
            return self._tabs.get(tab_id)

    def get_current_tab(self) -> TabInfo | None:
        with self._lock:
            if self._current_tab_id is None:
                return None
            return self._tabs.get(self._current_tab_id)

    def current_tab_id(self) -> str | None:
        with self._lock:
            return self._current_tab_id

    # ------------------------------------------------------------------ navigation

    def record_navigation(self, tab_id: str, url: str) -> None:
        with self._lock:
            info = self._tabs.get(tab_id)
            if info is None:
                return
            if not url:
                return
            # Truncate any "forward" history past the current pointer
            if 0 <= info.history_index < len(info.history) - 1:
                info.history = info.history[: info.history_index + 1]
            if not info.history or info.history[-1] != url:
                info.history.append(url)
                info.history_index = len(info.history) - 1
            info.url = url
            self._save_locked()

    def record_back(self, tab_id: str) -> str | None:
        with self._lock:
            info = self._tabs.get(tab_id)
            if info is None or info.history_index <= 0:
                return None
            info.history_index -= 1
            info.url = info.history[info.history_index]
            self._save_locked()
            return info.url

    def record_forward(self, tab_id: str) -> str | None:
        with self._lock:
            info = self._tabs.get(tab_id)
            if info is None or info.history_index >= len(info.history) - 1:
                return None
            info.history_index += 1
            info.url = info.history[info.history_index]
            self._save_locked()
            return info.url

    def previous_url(self, tab_id: str | None = None) -> str | None:
        with self._lock:
            tid = tab_id or self._current_tab_id
            if tid is None:
                return None
            info = self._tabs.get(tid)
            if info is None or info.history_index <= 0:
                return None
            return info.history[info.history_index - 1]

    def next_url(self, tab_id: str | None = None) -> str | None:
        with self._lock:
            tid = tab_id or self._current_tab_id
            if tid is None:
                return None
            info = self._tabs.get(tid)
            if info is None or info.history_index >= len(info.history) - 1:
                return None
            return info.history[info.history_index + 1]

    # ------------------------------------------------------------------ snapshots

    def update_snapshot(self, tab_id: str, snapshot: PageSnapshot) -> None:
        with self._lock:
            info = self._tabs.get(tab_id)
            if info is None:
                return
            info.last_snapshot = snapshot
            info.url = snapshot.url or info.url
            info.title = snapshot.title or info.title
            snaps = self._tab_snapshots.setdefault(tab_id, [])
            snaps.insert(0, snapshot)
            del snaps[MAX_SNAPSHOTS_PER_TAB:]
            self._save_locked()

    def get_current_snapshot(self) -> PageSnapshot | None:
        with self._lock:
            if self._current_tab_id is None:
                return None
            info = self._tabs.get(self._current_tab_id)
            return info.last_snapshot if info else None

    def get_previous_snapshot(self, tab_id: str | None = None) -> PageSnapshot | None:
        """Return the *second-most-recent* snapshot for the current tab.

        Used by "compare this with the previous page" — the previous
        snapshot is whatever was on screen before the most recent
        update.
        """
        with self._lock:
            tid = tab_id or self._current_tab_id
            if tid is None:
                return None
            snaps = self._tab_snapshots.get(tid) or []
            if len(snaps) < 2:
                # Fall back to the tab's last_snapshot, then None.
                info = self._tabs.get(tid)
                return info.last_snapshot if info else None
            return snaps[1]

    def get_snapshot_history(self, tab_id: str | None = None) -> list[PageSnapshot]:
        with self._lock:
            tid = tab_id or self._current_tab_id
            if tid is None:
                return []
            return list(self._tab_snapshots.get(tid) or [])

    # ------------------------------------------------------------------ misc

    def record_action(self, description: str) -> None:
        with self._lock:
            self._last_action = description
            if self._current_tab_id is not None:
                info = self._tabs.get(self._current_tab_id)
                if info is not None:
                    info.last_action = description
            self._save_locked()

    def last_action(self) -> str:
        with self._lock:
            return self._last_action

    def set_last_extraction(self, data: Any) -> None:
        with self._lock:
            self._last_extraction = data
            self._save_locked()

    def get_last_extraction(self) -> Any:
        with self._lock:
            return self._last_extraction

    # ------------------------------------------------------------------ links

    def find_link_by_ordinal(self, n: int) -> dict[str, str] | None:
        """Return the Nth link (1-indexed) on the current page snapshot, or None.

        ``n=1`` is the first link. ``n<0`` counts from the end
        (``n=-1`` is the last link).
        """
        snap = self.get_current_snapshot()
        if snap is None or not snap.links:
            return None
        links = snap.links
        if n == 0:
            return None
        if n > 0 and n <= len(links):
            return links[n - 1]
        if n < 0 and abs(n) <= len(links):
            return links[n]
        return None

    def find_link_by_text(self, text: str) -> dict[str, str] | None:
        snap = self.get_current_snapshot()
        if snap is None:
            return None
        target = text.strip().lower()
        for link in snap.links:
            if target in (link.get("text") or "").strip().lower():
                return link
        return None

    # ------------------------------------------------------------------ diagnostics

    def summary(self) -> dict[str, Any]:
        """Compact, JSON-safe snapshot of the whole memory — useful for
        the React UI's 'Browser' view."""
        with self._lock:
            tabs = [t.to_dict() for t in self._tabs.values()]
            current = self._current_tab_id
            return {
                "tabs": tabs,
                "current_tab_id": current,
                "tab_count": len(tabs),
                "last_action": self._last_action,
            }

    def clear(self) -> None:
        with self._lock:
            self._tabs.clear()
            self._tab_snapshots.clear()
            self._current_tab_id = None
            self._last_action = ""
            self._last_extraction = None
            self._save_locked()
