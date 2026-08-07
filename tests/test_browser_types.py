"""Round-trip serialization tests for browser_agent types."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Python"))

from browser_agent.types import (
    BrowserAction,
    BrowserActionPlan,
    BrowserActionResult,
    BrowserActionType,
    DownloadInfo,
    PageSnapshot,
    TabInfo,
)


# ---- BrowserAction ----

def test_action_roundtrip():
    a = BrowserAction(
        type=BrowserActionType.CLICK,
        target="text=Submit",
        value=None,
        params={"timeout_ms": 5000},
        requires_confirmation=False,
        reason="test",
    )
    d = a.to_dict()
    b = BrowserAction.from_dict(d)
    assert b.type == BrowserActionType.CLICK
    assert b.target == "text=Submit"
    assert b.params["timeout_ms"] == 5000
    assert b.requires_confirmation is False


def test_action_from_dict_errors():
    with pytest.raises(ValueError):
        BrowserAction.from_dict("not a dict")
    with pytest.raises(ValueError):
        BrowserAction.from_dict({"type": ""})
    with pytest.raises(ValueError):
        BrowserAction.from_dict({"type": "nonexistent_action"})


def test_action_all_types_serializable():
    for t in BrowserActionType:
        a = BrowserAction(type=t)
        d = a.to_dict()
        b = BrowserAction.from_dict(d)
        assert b.type == t


# ---- BrowserActionPlan ----

def test_plan_roundtrip():
    plan = BrowserActionPlan(
        thought="opening page",
        actions=[
            BrowserAction(type=BrowserActionType.NAVIGATE, target="https://example.com"),
            BrowserAction(type=BrowserActionType.READ_TEXT),
        ],
    )
    d = plan.to_dict()
    p2 = BrowserActionPlan.from_dict(d)
    assert p2.thought == "opening page"
    assert len(p2.actions) == 2
    assert p2.actions[0].type == BrowserActionType.NAVIGATE
    assert p2.actions[1].type == BrowserActionType.READ_TEXT


def test_plan_from_dict_skips_malformed():
    plan = BrowserActionPlan.from_dict({
        "thought": "test",
        "actions": [
            {"type": "click", "target": "text=OK"},  # valid
            {"type": "nonexistent"},                   # invalid → skipped
            "not a dict",                              # invalid → skipped
        ],
    })
    assert len(plan.actions) == 1


def test_plan_from_dict_non_list_actions():
    with pytest.raises(ValueError):
        BrowserActionPlan.from_dict({"thought": "x", "actions": "not a list"})


# ---- PageSnapshot ----

def test_snapshot_roundtrip():
    snap = PageSnapshot(
        url="https://example.com",
        title="Example",
        visible_text="Hello world",
        links=[{"text": "link1", "href": "/foo"}],
        forms=[{"action": "/submit", "method": "post", "fields": []}],
        buttons=[{"text": "Submit", "tag": "button"}],
    )
    d = snap.to_dict()
    s2 = PageSnapshot.from_dict(d)
    assert s2.url == "https://example.com"
    assert s2.visible_text == "Hello world"
    assert len(s2.links) == 1


def test_snapshot_truncate():
    snap = PageSnapshot(visible_text="x" * 10000, links=[{"text": "", "href": ""}] * 60)
    t = snap.truncate(max_text_chars=100)
    assert len(t.visible_text) < 200
    assert len(t.links) == 50  # capped at 50


def test_snapshot_from_dict_handles_missing():
    snap = PageSnapshot.from_dict({})
    assert snap.url == ""


# ---- TabInfo ----

def test_tab_roundtrip():
    tab = TabInfo(
        tab_id="abc123",
        page_id=1,
        url="https://test.com",
        title="Test",
        is_active=True,
        history=["https://test.com"],
        history_index=0,
    )
    d = tab.to_dict()
    t2 = TabInfo.from_dict(d)
    assert t2.tab_id == "abc123"
    assert t2.is_active is True
    assert t2.history == ["https://test.com"]


# ---- DownloadInfo ----

def test_download_roundtrip():
    dl = DownloadInfo(
        suggested_filename="file.pdf",
        save_path="/tmp/file.pdf",
        completed=True,
    )
    d = dl.to_dict()
    assert d["completed"] is True
    assert d["suggested_filename"] == "file.pdf"


# ---- BrowserActionResult ----

def test_result_roundtrip():
    r = BrowserActionResult(
        ok=True,
        action=BrowserAction(type=BrowserActionType.READ_TEXT),
        message="Read 100 chars",
        data={"text": "hello"},
    )
    d = r.to_dict()
    assert d["ok"] is True
    assert d["action"]["type"] == "read_text"
    assert d["data"]["text"] == "hello"
