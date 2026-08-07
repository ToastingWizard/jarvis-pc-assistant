"""Tests for browser_agent.agent BrowserAgent orchestration.

The executor and memory are mocked out so these run without Playwright/a browser.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Python"))

from browser_agent.agent import BrowserAgent
from browser_agent.types import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
)


class FakeExecutor:
    """Duck-typed stand-in for BrowserExecutor (matches its constructor signature)."""

    def __init__(self, config=None, memory=None, log=None):
        self.started = False
        self.closed = False
        self.executed: list[BrowserAction] = []

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def is_alive(self):
        return self.started and not self.closed

    def execute(self, action: BrowserAction) -> BrowserActionResult:
        self.executed.append(action)
        return BrowserActionResult(ok=True, action=action, message="ok")

    def refresh_snapshot(self):
        return None


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setattr("browser_agent.agent.BrowserExecutor", FakeExecutor)
    monkeypatch.setattr("browser_agent.memory.BrowserMemory._default_persist_path", lambda self: None)
    ag = BrowserAgent(config={}, log=lambda text: None)
    return ag


def test_start_and_status(agent):
    agent.start_browser()
    assert agent._executor is not None
    assert agent._executor.started is True
    status = agent.browser_status()
    assert status["running"] is True


def test_close(agent):
    agent.start_browser()
    agent.close_browser()
    assert agent._executor is None
    status = agent.browser_status()
    assert status["running"] is False


def test_navigate(agent):
    result = agent.navigate("https://example.com")
    assert result["ok"] is True
    assert agent._executor.executed[0].type == BrowserActionType.NAVIGATE


def test_run_empty_request(agent):
    result = agent.run("")
    assert result["ok"] is False


def test_run_navigate_request(agent):
    result = agent.run("open https://example.com")
    assert result["ok"] is True
    assert agent._executor.executed[0].type == BrowserActionType.NAVIGATE


def _plan_with_risky_action():
    from browser_agent.types import BrowserActionPlan
    risky = BrowserAction(
        type=BrowserActionType.CLICK,
        target="text=Delete",
        requires_confirmation=True,
        reason="risky",
    )
    return BrowserActionPlan(actions=[risky])


def test_run_pauses_for_confirmation(agent, monkeypatch):
    monkeypatch.setattr("browser_agent.agent.plan_actions", lambda **kw: _plan_with_risky_action())
    result = agent.run("do something")
    assert result["confirmation_required"] is True
    assert result["ok"] is False
    assert agent._pending_plan is not None


def test_confirm_executes_pending(agent, monkeypatch):
    monkeypatch.setattr("browser_agent.agent.plan_actions", lambda **kw: _plan_with_risky_action())
    paused = agent.run("do something")
    assert paused["confirmation_required"] is True
    result = agent.confirm()
    assert result["ok"] is True
    assert agent._pending_plan is None
    assert agent._executor.executed[0].type == BrowserActionType.CLICK


def test_cancel_clears_pending(agent):
    agent._pending_plan = _plan_with_risky_action()
    result = agent.cancel()
    assert result["ok"] is True
    assert agent._pending_plan is None


def test_confirm_with_nothing_pending(agent):
    result = agent.confirm()
    assert result["ok"] is False


def test_execute_action_dict(agent):
    result = agent.execute_action({"type": "read_text"})
    assert result["ok"] is True
    assert agent._executor.executed[0].type == BrowserActionType.READ_TEXT


def test_execute_action_invalid(agent):
    result = agent.execute_action({"type": "nonexistent"})
    assert result["ok"] is False


def test_tabs_empty_when_no_browser(agent):
    assert agent.tabs() == []


def test_browser_status_pending_confirmation(agent):
    agent._pending_plan = _plan_with_risky_action()
    status = agent.browser_status()
    assert status["pending_confirmation"] is not None
