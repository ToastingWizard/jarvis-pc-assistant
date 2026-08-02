"""Playwright-backed executor for browser actions.

Design
------
* One :class:`BrowserExecutor` per agent. It owns a single Playwright
  async context, one Chromium ``BrowserContext``, and a set of pages
  keyed by an internal ``page_id``.
* All Playwright calls run in a dedicated daemon thread with its own
  ``asyncio`` event loop. The thread is started lazily on first use so
  the cost of importing this module is paid only when the agent is
  actually invoked.
* From the engine's perspective, every method is **blocking** — it
  submits a coroutine to the event loop via
  ``asyncio.run_coroutine_threadsafe`` and waits for the result with a
  timeout. This is intentional: it gives us a sync API to call from
  ``NaitroEngine.run_command`` while keeping the Playwright world
  async-native underneath.
* Every public method returns a :class:`BrowserActionResult` (or the
  richer data for ``READ_TEXT`` etc.) and never raises for *expected*
  Playwright errors (timeout, navigation failure, missing element).
  Unexpected exceptions are caught and reported as
  ``ok=False, error=…`` so a single misbehaving action never tears down
  the whole agent.

Importing this module is safe even if Playwright is not installed —
:class:`PlaywrightNotInstalled` is raised on first use. This mirrors the
graceful-import pattern used elsewhere in NaiTRO.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .memory import BrowserMemory
from .search import SearchTarget, build_search_url, input_selector_for
from .types import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
    DownloadInfo,
    PageSnapshot,
)


# Try to import Playwright lazily. We don't want a hard import at module
# load because that breaks the rest of NaiTRO for users who never use
# the browser agent. The first call to :meth:`BrowserExecutor.start`
# does the real import.
class PlaywrightNotInstalled(RuntimeError):
    """Raised when the user invokes the browser agent without Playwright."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Selector helpers ----------------------------------------------------------

_CSS_PREFIXES = ("#", ".", "[", ">", "+", "~", "*", ":", " ")
_XPATH_PREFIX = ("//", "(//")


def _looks_like_xpath(selector: str) -> bool:
    s = selector.lstrip()
    return s.startswith("//") or s.startswith("(//")


def _to_playwright_selector(selector: str) -> str:
    """Wrap a plain text query so Playwright treats it as text=, not CSS.

    Playwright's CSS engine will choke on ``text=foo`` because it looks
    like an identifier. The convention is to keep the prefix explicit;
    we just pass through what the caller gave us unless it's a bare
    word with no CSS-identifier hint, in which case we treat it as a
    substring text query.
    """
    s = (selector or "").strip()
    if not s:
        return s
    if s.startswith(("text=", "role=", "css=", "xpath=", "label=", "placeholder=", "id=", "#")):
        return s
    if _looks_like_xpath(s):
        return f"xpath={s}"
    # If it looks like CSS, pass through.
    if any(s.startswith(p) for p in _CSS_PREFIXES):
        return s
    # Bare word -> text= substring
    # Quote-safe: Playwright accepts single or double quotes.
    safe = s.replace('"', '\\"')
    return f'text="{safe}"'


# ---------------------------------------------------------------------------


class BrowserExecutor:
    """Owns the Playwright lifecycle. Use one per agent."""

    DEFAULT_TIMEOUT_MS = 15_000
    DEFAULT_DOWNLOAD_DIRNAME = "NaiTRO Downloads"

    def __init__(
        self,
        config: dict[str, Any],
        memory: BrowserMemory,
        log: Callable[[str], None] | None = None,
    ):
        self._config = config or {}
        self._memory = memory
        self._log = log or (lambda text: None)

        browser_cfg = self._config.get("browser", {}) or {}
        self._headless: bool = bool(browser_cfg.get("headless", False))
        self._channel: str = str(browser_cfg.get("channel", "")).strip()  # "", "chrome", "msedge"
        self._executable_path: str = str(browser_cfg.get("executable_path", "")).strip()
        self._user_data_dir: Path = self._resolve_user_data_dir(browser_cfg.get("user_data_dir"))
        self._default_timeout_ms = int(browser_cfg.get("default_timeout_ms", self.DEFAULT_TIMEOUT_MS))
        self._download_dir: Path = self._resolve_download_dir(browser_cfg.get("download_dir"))
        self._screenshot_dir: Path = self._resolve_screenshot_dir(browser_cfg.get("screenshot_dir"))

        # Async machinery
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._started_lock = threading.Lock()
        self._closed = False

        # Playwright objects (set in the event loop)
        self._pw = None
        self._browser = None
        self._context = None
        # page_id -> Playwright Page
        self._pages: dict[int, Any] = {}
        # tab_id -> page_id (so we can resolve the memory layer's tab_id
        # to a real page when the agent asks us to act on a tab)
        self._tab_to_page: dict[str, int] = {}
        self._page_to_tab: dict[int, str] = {}
        # next page id to mint
        self._next_page_id = 1

    # ------------------------------------------------------------------ paths

    def _resolve_user_data_dir(self, raw: Any) -> Path:
        if raw:
            try:
                p = Path(str(raw)).expanduser().resolve()
                p.mkdir(parents=True, exist_ok=True)
                return p
            except Exception:
                pass
        # Default: %APPDATA%/NaiTRO/browser_profile on Windows, ~/.local/share/... elsewhere.
        if os.name == "nt":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            default = Path(base) / "NaiTRO" / "browser_profile"
        else:
            xdg = os.environ.get("XDG_DATA_HOME")
            base = xdg or str(Path.home() / ".local" / "share")
            default = Path(base) / "NaiTRO" / "browser_profile"
        try:
            default.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return default

    def _resolve_download_dir(self, raw: Any) -> Path:
        if raw:
            try:
                p = Path(str(raw)).expanduser().resolve()
                p.mkdir(parents=True, exist_ok=True)
                return p
            except Exception:
                pass
        # Default: user Downloads/NaiTRO Downloads
        try:
            downloads = Path.home() / "Downloads"
            if not downloads.exists():
                downloads = Path.cwd()
        except Exception:
            downloads = Path.cwd()
        target = downloads / self.DEFAULT_DOWNLOAD_DIRNAME
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return target

    def _resolve_screenshot_dir(self, raw: Any) -> Path:
        if raw:
            try:
                p = Path(str(raw)).expanduser().resolve()
                p.mkdir(parents=True, exist_ok=True)
                return p
            except Exception:
                pass
        target = self._download_dir.parent / "NaiTRO Screenshots"
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return target

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Start the event loop thread and launch the browser.

        Idempotent: calling it twice is a no-op. Raises
        :class:`PlaywrightNotInstalled` if Playwright is not importable.
        """
        with self._started_lock:
            if self._ready.is_set():
                return
            try:
                from playwright.async_api import async_playwright  # type: ignore
            except Exception as exc:  # pragma: no cover - import guard
                raise PlaywrightNotInstalled(
                    "Playwright is not installed. Run: pip install playwright && "
                    "python -m playwright install chromium"
                ) from exc

            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop, name="NaiTRO-BrowserLoop", daemon=True
            )
            self._thread.start()
            # Wait for the loop to be ready (or fail).
            if not self._ready.wait(timeout=30):
                raise PlaywrightNotInstalled("Browser event loop failed to start within 30 seconds")
            # _ready means the loop is alive; _context may still be None if
            # browser launch failed. We do that via _async_launch below.
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._async_launch(async_playwright), self._loop
                )
                fut.result(timeout=60)
            except Exception as exc:
                raise PlaywrightNotInstalled(f"Browser launch failed: {exc}") from exc

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        # Signal that the loop is up; _async_launch is what actually
        # opens the browser. _ready means "loop is alive", not "browser
        # is launched".
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _async_launch(self, async_playwright: Callable) -> None:
        self._pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self._headless,
        }
        if self._executable_path:
            launch_kwargs["executable_path"] = self._executable_path
        elif self._channel:
            launch_kwargs["channel"] = self._channel

        try:
            self._browser = await self._pw.chromium.launch(**launch_kwargs)
        except Exception as exc:
            # If a channel was requested but not installed, try the
            # default Chromium (which Playwright bundles) as a last resort.
            self._log(f"Browser launch with channel={self._channel!r} failed ({exc}); falling back to bundled chromium")
            launch_kwargs.pop("channel", None)
            launch_kwargs.pop("executable_path", None)
            self._browser = await self._pw.chromium.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 800},
        }
        if self._user_data_dir:
            # Persistent context gives us a real profile (cookies, etc.).
            # ``launch_persistent_context`` returns a context directly.
            try:
                self._browser = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self._user_data_dir),
                    headless=self._headless,
                    accept_downloads=True,
                    viewport={"width": 1280, "height": 800},
                    **({"channel": self._channel} if self._channel and not self._executable_path else {}),
                    **({"executable_path": self._executable_path} if self._executable_path else {}),
                )
                self._context = self._browser
                self._log(f"Browser launched (persistent profile at {self._user_data_dir})")
                return
            except Exception as exc:
                self._log(f"Persistent context launch failed ({exc}); using in-memory context")
                # The browser we just launched will be closed and replaced.
                try:
                    await self._browser.close()
                except Exception:
                    pass
                # Re-launch without persistent context, then create one.
                self._browser = await self._pw.chromium.launch(**launch_kwargs)

        self._context = await self._browser.new_context(**context_kwargs)
        self._log(f"Browser launched (in-memory context, download dir = {self._download_dir})")

    def close(self) -> None:
        """Tear everything down. Safe to call multiple times."""
        with self._started_lock:
            if self._closed:
                return
            self._closed = True
        if self._loop is None or not self._loop.is_running():
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(self._async_close(), self._loop)
            fut.result(timeout=10)
        except Exception as exc:
            self._log(f"Browser close error: {exc}")
        finally:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

    async def _async_close(self) -> None:
        for page in list(self._pages.values()):
            try:
                await page.close()
            except Exception:
                pass
        self._pages.clear()
        self._tab_to_page.clear()
        self._page_to_tab.clear()
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._browser is not None:
            try:
                # If we used launch_persistent_context, the "browser"
                # is actually a context; closing it once is enough.
                await self._browser.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass

    def is_alive(self) -> bool:
        return self._ready.is_set() and self._context is not None and not self._closed

    # ------------------------------------------------------------------ helpers

    def _run(self, coro: Any, timeout: float | None = None) -> Any:
        """Submit a coroutine to the event loop and wait synchronously."""
        if self._loop is None or self._closed:
            raise PlaywrightNotInstalled("Browser is not running")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def _page_id_for_tab(self, tab_id: str | None) -> int | None:
        if tab_id is None:
            tab = self._memory.get_current_tab()
            if tab is None:
                return None
            tab_id = tab.tab_id
        return self._tab_to_page.get(tab_id)

    def _page_for_action(self, action: BrowserAction) -> tuple[str, int, Any] | None:
        """Resolve an action's intended tab/page into (tab_id, page_id, page)."""
        tab_id: str | None = None
        # switch_tab carries the tab id in target.
        if action.type == BrowserActionType.SWITCH_TAB:
            if action.target:
                tab_id = action.target
            elif action.value is not None:
                tabs = self._memory.list_tabs()
                try:
                    idx = int(action.value) - 1
                except (TypeError, ValueError):
                    idx = -1
                if 0 <= idx < len(tabs):
                    tab_id = tabs[idx].tab_id
        else:
            tab = self._memory.get_current_tab()
            if tab is not None:
                tab_id = tab.tab_id
        if tab_id is None:
            return None
        page_id = self._tab_to_page.get(tab_id)
        if page_id is None:
            return None
        page = self._pages.get(page_id)
        if page is None:
            return None
        return tab_id, page_id, page

    async def _new_page_internal(self, url: str = "") -> tuple[str, int, Any]:
        assert self._context is not None
        page = await self._context.new_page()
        page_id = self._next_page_id
        self._next_page_id += 1
        self._pages[page_id] = page
        tab_id = self._memory.new_tab(page_id, url=url)
        self._tab_to_page[tab_id] = page_id
        self._page_to_tab[page_id] = tab_id
        if url:
            try:
                await page.goto(url, timeout=self._default_timeout_ms, wait_until="domcontentloaded")
            except Exception as exc:
                self._log(f"new_page initial navigation failed: {exc}")
        return tab_id, page_id, page

    # ------------------------------------------------------------------ public API

    def execute(self, action: BrowserAction) -> BrowserActionResult:
        """Execute one action and return its result. Never raises for
        expected Playwright errors."""
        start = time.time()
        try:
            self.start()  # idempotent
        except PlaywrightNotInstalled as exc:
            return BrowserActionResult(
                ok=False, action=action, error=str(exc),
                message=f"Browser unavailable: {exc}",
            )
        try:
            method = getattr(self, f"_do_{action.type.value}")
        except AttributeError:
            return BrowserActionResult(
                ok=False, action=action,
                error=f"No executor for action type {action.type.value}",
            )
        try:
            result = method(action)
            if asyncio.iscoroutine(result):
                result = self._run(result, timeout=self._default_timeout_ms / 1000 + 60)
        except Exception as exc:
            tb = traceback.format_exc(limit=2)
            self._log(f"Executor error on {action.type.value}: {exc}")
            return BrowserActionResult(
                ok=False, action=action, error=f"{exc}", message=tb,
            )
        # Annotate timing
        if isinstance(result, BrowserActionResult):
            result.duration_ms = int((time.time() - start) * 1000)
            # Record short action description in memory for the React UI
            short = action.type.value
            if action.target:
                short = f"{short} {action.target}"
            self._memory.record_action(short)
            return result
        # Defensive: method returned something unexpected.
        return BrowserActionResult(
            ok=False, action=action, error=f"Executor returned {type(result).__name__}",
        )

    # ----------------------- navigation -----------------------

    async def _do_navigate(self, action: BrowserAction) -> BrowserActionResult:
        url = action.target or ""
        if not url:
            return BrowserActionResult(ok=False, action=action, error="navigate needs a URL target")
        resolved = self._page_for_action(action)
        if resolved is None:
            # No active tab; create one.
            tab_id, page_id, page = await self._new_page_internal(url)
        else:
            tab_id, page_id, page = resolved
            await page.goto(url, timeout=self._default_timeout_ms, wait_until="domcontentloaded")
            self._memory.record_navigation(tab_id, url)
        self._memory.set_current_tab(tab_id)
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Navigated to {url}",
            data=snap.to_dict(),
        )

    async def _do_new_tab(self, action: BrowserAction) -> BrowserActionResult:
        url = action.target or ""
        tab_id, page_id, page = await self._new_page_internal(url)
        self._memory.set_current_tab(tab_id)
        if url:
            self._memory.record_navigation(tab_id, url)
        snap = await self._capture_snapshot(page, tab_id=tab_id) if url else None
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Opened new tab" + (f" at {url}" if url else ""),
            data={"tab_id": tab_id, "page_id": page_id, "snapshot": snap.to_dict() if snap else None},
        )

    async def _do_close_tab(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No tab to close")
        tab_id, page_id, page = resolved
        try:
            await page.close()
        except Exception as exc:
            self._log(f"Error closing page: {exc}")
        self._pages.pop(page_id, None)
        self._tab_to_page.pop(tab_id, None)
        self._page_to_tab.pop(page_id, None)
        self._memory.close_tab(tab_id)
        return BrowserActionResult(ok=True, action=action, message="Closed tab")

    async def _do_switch_tab(self, action: BrowserAction) -> BrowserActionResult:
        # _page_for_action already handles target/value resolution
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="Tab not found")
        tab_id, page_id, page = resolved
        self._memory.set_current_tab(tab_id)
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Switched to {snap.title or snap.url or tab_id}",
            data=snap.to_dict(),
        )

    async def _do_reload(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, page_id, page = resolved
        await page.reload(wait_until="domcontentloaded")
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(ok=True, action=action, message="Reloaded", data=snap.to_dict())

    async def _do_back(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, page_id, page = resolved
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Back failed: {exc}")
        url = page.url
        self._memory.record_back(tab_id)
        if url:
            self._memory.record_navigation(tab_id, url)
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(ok=True, action=action, message=f"Back to {url}", data=snap.to_dict())

    async def _do_forward(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, page_id, page = resolved
        try:
            await page.go_forward(wait_until="domcontentloaded", timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Forward failed: {exc}")
        url = page.url
        self._memory.record_forward(tab_id)
        if url:
            self._memory.record_navigation(tab_id, url)
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(ok=True, action=action, message=f"Forward to {url}", data=snap.to_dict())

    # ----------------------- interaction -----------------------

    async def _do_click(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, page_id, page = resolved
        selector = _to_playwright_selector(action.target or "")
        try:
            await page.click(selector, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Click failed: {exc}")
        # If the click navigated, record it
        await page.wait_for_load_state("domcontentloaded", timeout=self._default_timeout_ms)
        url = page.url
        if url:
            self._memory.record_navigation(tab_id, url)
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(ok=True, action=action, message=f"Clicked {selector}", data=snap.to_dict())

    async def _do_double_click(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        try:
            await page.dblclick(selector, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Double-click failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Double-clicked {selector}")

    async def _do_right_click(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        try:
            await page.click(selector, button="right", timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Right-click failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Right-clicked {selector}")

    async def _do_hover(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        try:
            await page.hover(selector, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Hover failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Hovered {selector}")

    async def _do_type_text(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        text = str(action.value or "")
        if action.target:
            selector = _to_playwright_selector(action.target)
            try:
                await page.fill(selector, text, timeout=self._default_timeout_ms)
            except Exception as exc:
                return BrowserActionResult(ok=False, action=action, error=f"Fill failed: {exc}")
        else:
            try:
                await page.keyboard.type(text, delay=20)
            except Exception as exc:
                return BrowserActionResult(ok=False, action=action, error=f"Type failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Typed {len(text)} chars")

    async def _do_press_key(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        key = str(action.value or "")
        try:
            await page.keyboard.press(key)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Key press failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Pressed {key}")

    async def _do_fill_form(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        value = str(action.value or "")
        try:
            await page.fill(selector, value, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Fill failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Filled {selector}")

    async def _do_select_option(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        value = action.value
        try:
            await page.select_option(selector, value=value, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Select failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Selected {value} in {selector}")

    async def _do_check(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        try:
            await page.check(selector, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Check failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Checked {selector}")

    async def _do_uncheck(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        try:
            await page.uncheck(selector, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Uncheck failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Unchecked {selector}")

    async def _do_upload_file(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        selector = _to_playwright_selector(action.target or "")
        path = str(action.value or "")
        try:
            await page.set_input_files(selector, path, timeout=self._default_timeout_ms)
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Upload failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Uploaded {path}")

    async def _do_scroll(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        # params may carry direction + amount; defaults: down, one viewport
        direction = str(action.params.get("direction", "down")).lower()
        amount = int(action.params.get("amount", 600))
        if direction == "top":
            await page.evaluate("() => window.scrollTo(0, 0)")
        elif direction == "bottom":
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "up":
            await page.evaluate(f"() => window.scrollBy(0, -{amount})")
        else:
            await page.evaluate(f"() => window.scrollBy(0, {amount})")
        pos = await page.evaluate("() => window.scrollY")
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        snap.scroll_position = int(pos or 0)
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Scrolled {direction} to {snap.scroll_position}",
            data=snap.to_dict(),
        )

    async def _do_select_text(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        # Params: start, end (chars on the page body), or selector+substring
        try:
            start = int(action.params.get("start", 0))
            end = int(action.params.get("end", 200))
            text = await page.evaluate(
                f"() => {{ const s = document.body.innerText || ''; return s.substring({start}, {end}); }}"
            )
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Select text failed: {exc}")
        snap = self._memory.get_current_snapshot()
        if snap is not None:
            snap.selected_text = str(text or "")
            self._memory.update_snapshot(tab_id, snap)
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Selected {end - start} chars",
            data={"selected_text": text},
        )

    # ----------------------- reading -----------------------

    async def _do_read_text(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        try:
            text = await page.evaluate("() => document.body.innerText || ''")
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Read text failed: {exc}")
        snap = self._memory.get_current_snapshot()
        if snap is not None:
            snap.visible_text = str(text or "")
            self._memory.update_snapshot(tab_id, snap)
        self._memory.set_last_extraction({"type": "text", "text": text})
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Read {len(text or '')} chars",
            data={"text": text},
        )

    async def _do_read_title(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        try:
            title = await resolved[2].title()
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Read title failed: {exc}")
        return BrowserActionResult(ok=True, action=action, message=f"Title: {title}", data={"title": title})

    async def _do_read_url(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        url = resolved[2].url
        return BrowserActionResult(ok=True, action=action, message=f"URL: {url}", data={"url": url})

    async def _do_extract_links(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        try:
            links = await page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]')).slice(0, 200).map(a => ({
                    text: (a.innerText || a.textContent || '').trim().slice(0, 200),
                    href: a.href
                }))"""
            )
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Extract links failed: {exc}")
        snap = self._memory.get_current_snapshot()
        if snap is not None:
            snap.links = list(links or [])
            self._memory.update_snapshot(tab_id, snap)
        self._memory.set_last_extraction({"type": "links", "links": links})
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Extracted {len(links or [])} links",
            data={"links": list(links or [])},
        )

    async def _do_extract_table(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        try:
            tables = await page.evaluate(
                """() => Array.from(document.querySelectorAll('table')).slice(0, 5).map(t => {
                    const headers = Array.from(t.querySelectorAll('th')).map(th => th.innerText.trim());
                    const rows = Array.from(t.querySelectorAll('tr')).slice(0, 50).map(tr =>
                        Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
                    );
                    return { headers, rows };
                })"""
            )
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Extract tables failed: {exc}")
        snap = self._memory.get_current_snapshot()
        if snap is not None:
            snap.tables = list(tables or [])
            self._memory.update_snapshot(tab_id, snap)
        self._memory.set_last_extraction({"type": "tables", "tables": tables})
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Extracted {len(tables or [])} tables",
            data={"tables": list(tables or [])},
        )

    async def _do_extract_form(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        try:
            forms = await page.evaluate(
                """() => Array.from(document.querySelectorAll('form')).slice(0, 10).map(f => {
                    const fields = Array.from(f.querySelectorAll('input, textarea, select')).slice(0, 30).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        required: !!el.required,
                    }));
                    return { action: f.action || '', method: (f.method || 'get').toLowerCase(), fields };
                })"""
            )
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Extract forms failed: {exc}")
        snap = self._memory.get_current_snapshot()
        if snap is not None:
            snap.forms = list(forms or [])
            self._memory.update_snapshot(tab_id, snap)
        self._memory.set_last_extraction({"type": "forms", "forms": forms})
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Extracted {len(forms or [])} forms",
            data={"forms": list(forms or [])},
        )

    async def _do_extract_buttons(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        try:
            buttons = await page.evaluate(
                """() => {
                    const list = [];
                    const sel = 'button, input[type="submit"], input[type="button"], [role="button"]';
                    for (const el of document.querySelectorAll(sel)) {
                        const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                        if (text) list.push({ text: text.slice(0, 200), tag: el.tagName.toLowerCase() });
                    }
                    return list.slice(0, 50);
                }"""
            )
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Extract buttons failed: {exc}")
        snap = self._memory.get_current_snapshot()
        if snap is not None:
            snap.buttons = list(buttons or [])
            self._memory.update_snapshot(tab_id, snap)
        self._memory.set_last_extraction({"type": "buttons", "buttons": buttons})
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Extracted {len(buttons or [])} buttons",
            data={"buttons": list(buttons or [])},
        )

    async def _do_get_page_info(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(ok=True, action=action, message="Page info captured", data=snap.to_dict())

    # ----------------------- search -----------------------

    async def _do_search(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        site = str(action.value or action.params.get("site") or "")
        query = str(action.target or action.params.get("query") or "")
        if not site or not query:
            return BrowserActionResult(ok=False, action=action, error="search needs site (value) and query (target)")
        target: SearchTarget = build_search_url(site, query)
        if resolved is None:
            tab_id, page_id, page = await self._new_page_internal(target.url)
        else:
            tab_id, page_id, page = resolved
            await page.goto(target.url, timeout=self._default_timeout_ms, wait_until="domcontentloaded")
            self._memory.record_navigation(tab_id, target.url)
        self._memory.set_current_tab(tab_id)
        if target.needs_input_fill:
            selector = input_selector_for(site) or 'input[type="search"], input[name="q"], input[name="search"]'
            try:
                await page.fill(selector, query, timeout=self._default_timeout_ms)
                await page.keyboard.press("Enter")
            except Exception as exc:
                self._log(f"Search input fill failed: {exc}")
                return BrowserActionResult(
                    ok=False, action=action,
                    error=f"Couldn't find a search box on {site}: {exc}",
                )
        snap = await self._capture_snapshot(page, tab_id=tab_id)
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Searched {site} for {query}",
            data=snap.to_dict(),
        )

    # ----------------------- downloads -----------------------

    async def _do_download(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        suggested = str(action.value or action.params.get("filename") or "download.bin")
        try:
            async with page.expect_download(timeout=self._default_timeout_ms) as dl_info:
                # If a target selector was given, click it; else the page
                # must already be at the download URL (e.g. a PDF link
                # that started downloading on its own).
                if action.target:
                    selector = _to_playwright_selector(action.target)
                    try:
                        await page.click(selector, timeout=self._default_timeout_ms)
                    except Exception:
                        # fall back: the page is already at the file URL
                        pass
                else:
                    # Try the current page URL as the download source.
                    url = page.url
                    if url and not url.startswith("data:"):
                        await page.goto(url, wait_until="domcontentloaded")
            download = await dl_info.value
            target_path = self._download_dir / suggested
            # Avoid clobbering
            counter = 1
            final_path = target_path
            while final_path.exists():
                final_path = target_path.with_name(f"{target_path.stem} ({counter}){target_path.suffix}")
                counter += 1
            await download.save_as(str(final_path))
            info = DownloadInfo(
                suggested_filename=suggested,
                save_path=str(final_path),
                completed=True,
            )
            return BrowserActionResult(
                ok=True, action=action,
                message=f"Downloaded to {final_path}",
                data=info.to_dict(),
            )
        except Exception as exc:
            return BrowserActionResult(
                ok=False, action=action, error=f"Download failed: {exc}",
                data=DownloadInfo(suggested_filename=suggested, error=str(exc)).to_dict(),
            )

    async def _do_save_pdf(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        tab_id, _, page = resolved
        suggested = str(action.value or action.params.get("filename") or "page.pdf")
        if not suggested.lower().endswith(".pdf"):
            suggested += ".pdf"
        target_path = self._download_dir / suggested
        counter = 1
        final_path = target_path
        while final_path.exists():
            final_path = target_path.with_name(f"{target_path.stem} ({counter}){target_path.suffix}")
            counter += 1
        try:
            await page.emulate_media(media="print")
            await page.pdf(path=str(final_path), format="A4", print_background=True)
            await page.emulate_media(media="screen")
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Save PDF failed: {exc}")
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Saved PDF to {final_path}",
            data={"path": str(final_path)},
        )

    # ----------------------- meta -----------------------

    async def _do_wait_for(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        timeout_ms = int(action.params.get("timeout_ms", self._default_timeout_ms))
        selector = action.target
        if selector:
            sel = _to_playwright_selector(selector)
            try:
                await page.wait_for_selector(sel, timeout=timeout_ms)
            except Exception as exc:
                return BrowserActionResult(ok=False, action=action, error=f"wait_for selector failed: {exc}")
        else:
            await page.wait_for_timeout(min(timeout_ms, 5000))
        return BrowserActionResult(ok=True, action=action, message="Waited")

    async def _do_screenshot(self, action: BrowserAction) -> BrowserActionResult:
        resolved = self._page_for_action(action)
        if resolved is None:
            return BrowserActionResult(ok=False, action=action, error="No active tab")
        _, _, page = resolved
        suggested = str(action.value or "screenshot.png")
        target_path = self._screenshot_dir / suggested
        counter = 1
        final_path = target_path
        while final_path.exists():
            final_path = target_path.with_name(f"{target_path.stem} ({counter}){target_path.suffix}")
            counter += 1
        try:
            await page.screenshot(path=str(final_path), full_page=bool(action.params.get("full_page", False)))
        except Exception as exc:
            return BrowserActionResult(ok=False, action=action, error=f"Screenshot failed: {exc}")
        return BrowserActionResult(
            ok=True, action=action,
            message=f"Screenshot saved to {final_path}",
            screenshot_path=str(final_path),
            data={"path": str(final_path)},
        )

    async def _do_confirm_required(self, action: BrowserAction) -> BrowserActionResult:
        return BrowserActionResult(
            ok=False,
            action=action,
            error="Confirmation required",
            message=action.reason or "This action needs your confirmation.",
        )

    async def _do_noop(self, action: BrowserAction) -> BrowserActionResult:
        return BrowserActionResult(ok=True, action=action, message="No action taken")

    # ----------------------- snapshot capture -----------------------

    async def _capture_snapshot(self, page: Any, tab_id: str | None = None) -> PageSnapshot:
        """Read the page's URL, title, visible text, and a few structural
        lists into a :class:`PageSnapshot`. Persists the snapshot to
        memory so future turns can use it."""
        try:
            url = page.url or ""
        except Exception:
            url = ""
        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            text = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
        except Exception:
            text = ""
        try:
            links = await page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]')).slice(0, 50).map(a => ({
                    text: (a.innerText || '').trim().slice(0, 200),
                    href: a.href
                }))"""
            )
        except Exception:
            links = []
        try:
            buttons = await page.evaluate(
                """() => {
                    const list = [];
                    const sel = 'button, input[type="submit"], input[type="button"], [role="button"]';
                    for (const el of document.querySelectorAll(sel)) {
                        const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                        if (text) list.push({ text: text.slice(0, 200), tag: el.tagName.toLowerCase() });
                    }
                    return list.slice(0, 30);
                }"""
            )
        except Exception:
            buttons = []
        try:
            scroll_y = await page.evaluate("() => window.scrollY || 0")
        except Exception:
            scroll_y = 0
        try:
            forms = await page.evaluate(
                """() => Array.from(document.querySelectorAll('form')).slice(0, 5).map(f => ({
                    action: f.action || '',
                    method: (f.method || 'get').toLowerCase(),
                    fields: Array.from(f.querySelectorAll('input,textarea,select')).slice(0, 10).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        name: el.name || '',
                    })),
                }))"""
            )
        except Exception:
            forms = []
        snap = PageSnapshot(
            url=url,
            title=title or "",
            visible_text=str(text or ""),
            links=list(links or []),
            forms=list(forms or []),
            tables=[],
            buttons=list(buttons or []),
            scroll_position=int(scroll_y or 0),
            selected_text="",
            captured_at=_now_iso(),
        )
        if tab_id:
            self._memory.update_snapshot(tab_id, snap)
        return snap

    # ----------------------- convenience -----------------------

    def snapshot(self) -> PageSnapshot | None:
        """Return the in-memory current snapshot without doing any new
        browser I/O. Use this from the agent for cheap "what's on
        screen" lookups; the executor's own action methods keep the
        snapshot fresh as a side effect."""
        return self._memory.get_current_snapshot()

    def refresh_snapshot(self) -> BrowserActionResult | None:
        """Force a fresh snapshot of the current page. Returns the
        wrapped result or None if there's no active tab."""
        if self._loop is None or self._closed:
            return None
        tab = self._memory.get_current_tab()
        if tab is None:
            return None
        page = self._pages.get(tab.page_id)
        if page is None:
            return None
        try:
            snap = self._run(
                self._capture_snapshot(page, tab_id=tab.tab_id),
                timeout=self._default_timeout_ms / 1000 + 5,
            )
        except Exception as exc:
            return BrowserActionResult(
                ok=False, action=BrowserAction(type=BrowserActionType.GET_PAGE_INFO),
                error=str(exc),
            )
        return BrowserActionResult(
            ok=True,
            action=BrowserAction(type=BrowserActionType.GET_PAGE_INFO),
            message="Snapshot refreshed",
            data=snap.to_dict(),
        )
