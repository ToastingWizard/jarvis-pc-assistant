"""NaiTRO Browser Agent — production-quality browser automation with LLM planning.

Public entry point: :class:`BrowserAgent` (defined in ``agent.py``).
Everything else in this package is an implementation detail used by it.

Module map:
    types        - pure dataclasses / enums (no third-party imports)
    memory       - persistent tab & page-snapshot state (no Playwright)
    search       - site templates and search URL construction
    validator    - pre-execution safety gate (pure)
    executor     - Playwright lifecycle and per-action execution
    planner      - LLM -> structured BrowserActionPlan
    agent        - the orchestrator callers actually use
"""
from .agent import BrowserAgent
from .types import (
    BrowserAction,
    BrowserActionPlan,
    BrowserActionResult,
    BrowserActionType,
    DownloadInfo,
    PageSnapshot,
    TabInfo,
)
from .memory import BrowserMemory

__all__ = [
    "BrowserAgent",
    "BrowserAction",
    "BrowserActionPlan",
    "BrowserActionResult",
    "BrowserActionType",
    "DownloadInfo",
    "PageSnapshot",
    "TabInfo",
    "BrowserMemory",
]
