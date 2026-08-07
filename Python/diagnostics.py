"""
diagnostics.py — NaiTRO packaging diagnostics.

Writes ``logs/startup.log`` (next to the EXE when frozen, at the repo
root in source mode) with:

  * the runtime environment: cwd, executable path, ``__file__``,
    ``sys.executable``, ``sys.frozen``, ``sys._MEIPASS`` (when present),
    and the resolved base directory
  * every config / asset / icon lookup, with found-or-missing results
  * full tracebacks for every uncaught exception, on the main thread and
    on every worker thread (``sys.excepthook`` + ``threading.excepthook``)
  * per-subsystem startup timings
  * a runtime verification pass over every file bundled by PyInstaller
    (reads ``bundle-manifest.txt`` from ``sys._MEIPASS``)

Design notes
------------
* A single daemon writer thread owns the file handle, so logging can
  never block the UI thread or a background task (requirement: the UI
  never blocks while waiting for startup tasks).
* Nothing here changes NaiTRO's behaviour.  It only *observes*: every
  function is a logging helper, and ``init()`` is idempotent and safe to
  call from any import site, including pytest (headless).
* This module must import cleanly in every runtime mode: source (a
  ``Python/`` script), frozen (inside a PyInstaller bundle), and tests.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

_START = time.monotonic()
_INITIALIZED = False
_QUEUE: "queue.Queue[tuple[str | None, threading.Event | None]]" = None
_WRITER_THREAD: threading.Thread | None = None

_STOP = object()  # sentinel for the writer thread


# --------------------------------------------------------------------------
# Path helpers
# --------------------------------------------------------------------------

def is_frozen() -> bool:
    """True when running inside a PyInstaller-compiled executable."""
    return bool(getattr(sys, "frozen", False))


def meipass() -> str | None:
    """``sys._MEIPASS`` (PyInstaller extraction dir) or None in source mode."""
    return getattr(sys, "_MEIPASS", None)


def base_dir() -> Path:
    """Directory that owns NaiTRO's writable state in this runtime mode.

    Frozen: the directory holding the EXE (the natural place for the
    user's config + logs).  Source: the repository root (one level up
    from this ``Python/`` module).
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def startup_log_path() -> Path:
    return base_dir() / "logs" / "startup.log"


# --------------------------------------------------------------------------
# Writer thread
# --------------------------------------------------------------------------

def _writer_loop(path: Path) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n========== NaiTRO startup log ==========  ({time.ctime()})\n")
        fh.flush()
        while True:
            line, event = _QUEUE.get()
            if line is _STOP:
                break
            if event is not None:
                event.set()  # flush barrier: drain completed
                continue
            fh.write(line + "\n")
            fh.flush()


def init() -> bool:
    """Idempotently start the logger and write the environment header.

    Returns True if logging is active, False if it could not be started
    (in which case the app must continue silently — never let diagnostics
    take the app down).
    """
    global _INITIALIZED, _QUEUE, _WRITER_THREAD
    if _INITIALIZED:
        return True
    try:
        path = startup_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _QUEUE = queue.Queue()
        _WRITER_THREAD = threading.Thread(
            target=_writer_loop, args=(path,), name="naitro-diagnostics", daemon=True
        )
        _WRITER_THREAD.start()
    except Exception as exc:
        # Never let diagnostics break the app.  Best-effort stderr note.
        try:
            sys.stderr.write(f"[diagnostics] could not start logger: {exc!r}\n")
        except Exception:
            pass
        return False
    _INITIALIZED = True

    _log_environment()
    _install_exception_hooks()
    if is_frozen():
        verify_bundled()
    flush()
    return True


def _log_environment() -> None:
    log("[env] === environment ===")
    log(f"[env] frozen               : {is_frozen()}")
    log(f"[env] cwd                  : {os.getcwd()}")
    log(f"[env] executable path      : {sys.executable}")
    log(f"[env] __file__ (diagnostics): {__file__}")
    log(f"[env] sys.executable       : {sys.executable}")
    log(f"[env] sys._MEIPASS         : {meipass() if is_frozen() else '(not frozen)'}")
    log(f"[env] base directory       : {base_dir()}")
    log(f"[env] startup log          : {startup_log_path()}")
    log(f"[env] python version       : {sys.version.split()[0]}")


def log_extra(name: str, value: object) -> None:
    """Log one extra environment fact (e.g. ``naitro_app.__file__``)."""
    log(f"[env] {name:<22}: {value}")


# --------------------------------------------------------------------------
# Logging helpers
# --------------------------------------------------------------------------

def log(message: str) -> None:
    """Append a timestamped line to startup.log (non-blocking)."""
    if not _INITIALIZED:
        return
    _QUEUE.put((f"[{time.monotonic() - _START:7.3f}s] {message}", None))


def flush() -> None:
    """Block until everything queued so far is on disk (used at milestones)."""
    if not _INITIALIZED:
        return
    event = threading.Event()
    _QUEUE.put((None, event))
    event.wait(timeout=1.0)


def lookup(kind: str, label: str, path: str) -> bool:
    """Log a config / asset / icon lookup.  Returns whether *path* exists.

    ``kind`` is one of ``config``, ``asset``, ``icon`` so the log can be
    filtered per requirement.
    """
    p = Path(path)
    exists = p.exists()
    if exists:
        log(f"[{kind}] {label}: FOUND   {p}")
    else:
        log(f"[{kind}] {label}: MISSING {p}")
    return exists


def report_missing(label: str, path: str) -> None:
    """Explicitly report a missing file instead of continuing silently."""
    log(f"[missing] {label}: {path}")


def log_config_search(used_path: str, candidates: list[str]) -> None:
    """Log every config file location considered, and which one is used.

    ``candidates`` are all locations the app knows about (EXE dir, source
    layout, bundled example); ``used_path`` is the one actually read.
    """
    log("[config] === config file search ===")
    for cand in candidates:
        lookup("config", "candidate", cand)
    log(f"[config] using: {used_path}")


def exception(context: str, exc: BaseException) -> None:
    """Log a full traceback for an exception caught at a call site."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log(f"[exception] {context}: {type(exc).__name__}: {exc}")
    for tb_line in tb.rstrip().splitlines():
        log(f"[exception]     {tb_line}")


# --------------------------------------------------------------------------
# Timing helpers
# --------------------------------------------------------------------------

class _Timing:
    def __init__(self, name: str):
        self.name = name
        self._t0 = time.monotonic()

    def __enter__(self) -> "_Timing":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed_ms = (time.monotonic() - self._t0) * 1000.0
        status = "OK" if exc_type is None else f"EXC:{exc_type.__name__}"
        log(f"[timing] {self.name}: {elapsed_ms:9.1f} ms  ({status})")
        flush()
        return False  # do not suppress the exception


def timing(name: str) -> _Timing:
    """Context manager that logs elapsed time for a subsystem block."""
    return _Timing(name)


def mark(name: str) -> None:
    """Log a one-shot milestone (no duration)."""
    log(f"[mark] {name}")


# --------------------------------------------------------------------------
# Exception hooks (log EVERY uncaught exception with a full traceback)
# --------------------------------------------------------------------------

def _install_exception_hooks() -> None:
    try:
        _install_sys_excepthook()
    except Exception as exc:
        log(f"[hooks] could not install sys.excepthook: {exc!r}")
    try:
        _install_threading_excepthook()
    except Exception as exc:
        log(f"[hooks] could not install threading.excepthook: {exc!r}")


def _report_uncaught(where: str, exc_type, exc_value, exc_tb) -> None:
    log(f"[uncaught] === unhandled exception on {where} ===")
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    for tb_line in tb.rstrip().splitlines():
        log(f"[uncaught]     {tb_line}")


def _install_sys_excepthook() -> None:
    prev = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            _report_uncaught("the main thread", exc_type, exc_value, exc_tb)
        finally:
            prev(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def _install_threading_excepthook() -> None:
    prev = threading.excepthook

    def _hook(args):
        try:
            name = getattr(getattr(args, "thread", None), "name", "<unknown>")
            _report_uncaught(f"thread {name!r}", args.exc_type, args.exc_value, args.exc_traceback)
        finally:
            prev(args)

    threading.excepthook = _hook


# --------------------------------------------------------------------------
# PyInstaller bundled-file verification
# --------------------------------------------------------------------------

BUNDLE_MANIFEST_NAME = "bundle-manifest.txt"


def verify_bundled() -> None:
    """When frozen, verify every file PyInstaller bundled exists at runtime.

    Reads ``sys._MEIPASS/bundle-manifest.txt`` (written at build time by
    NaiTRO.spec) and reports any entry that is missing from the extraction
    directory.  Every reported miss is a real packaging regression.
    """
    mp = meipass()
    if not mp:
        return
    manifest = Path(mp) / BUNDLE_MANIFEST_NAME
    if not manifest.is_file():
        report_missing("bundle-manifest.txt (cannot verify bundled files)", str(manifest))
        return
    total = 0
    missing: list[str] = []
    try:
        content = manifest.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        exception("reading bundle-manifest.txt", exc)
        return
    for raw in content:
        rel = raw.strip()
        if not rel or rel.startswith("#"):
            continue
        total += 1
        if not (Path(mp) / rel).exists():
            missing.append(rel)
    log(f"[bundle] verified {total} bundled file(s); {len(missing)} missing")
    for rel in missing:
        report_missing("bundled file not found at runtime", f"{mp}\\{rel}")
    flush()
