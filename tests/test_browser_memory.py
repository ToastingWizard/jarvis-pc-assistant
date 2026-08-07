"""Tests for browser_agent.memory BrowserMemory."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Python"))

from browser_agent.memory import BrowserMemory
from browser_agent.types import PageSnapshot


@pytest.fixture
def mem(tmp_path):
    """A BrowserMemory with no persist path to avoid stale data."""
    return BrowserMemory(persist_path=tmp_path / "nonexistent.json")


def test_new_tab_and_list(mem):
    tid = mem.new_tab(1, url="https://a.com")
    assert mem.current_tab_id() == tid
    tabs = mem.list_tabs()
    assert len(tabs) == 1
    assert tabs[0].url == "https://a.com"


def test_set_current_tab(mem):
    t1 = mem.new_tab(1)
    t2 = mem.new_tab(2)
    assert mem.current_tab_id() == t2
    mem.set_current_tab(t1)
    # set_current_tab updates is_active but not current_tab_id
    tab1 = mem.get_tab(t1)
    assert tab1.is_active is True


def test_close_tab(mem):
    t1 = mem.new_tab(1)
    t2 = mem.new_tab(2)
    mem.close_tab(t1)
    assert len(mem.list_tabs()) == 1


def test_navigation_history(mem):
    tid = mem.new_tab(1, url="https://a.com")
    mem.record_navigation(tid, "https://b.com")
    info = mem.get_tab(tid)
    assert info.url == "https://b.com"
    assert len(info.history) == 2


def test_back_forward(mem):
    tid = mem.new_tab(1, url="https://a.com")
    mem.record_navigation(tid, "https://b.com")
    url = mem.record_back(tid)
    assert url == "https://a.com"
    url = mem.record_forward(tid)
    assert url == "https://b.com"


def test_snapshot_lifecycle(mem):
    tid = mem.new_tab(1, url="https://test.com")
    snap = PageSnapshot(url="https://test.com", title="Test", visible_text="hello")
    mem.update_snapshot(tid, snap)
    current = mem.get_current_snapshot()
    assert current is not None
    assert current.title == "Test"


def test_snapshot_history_capped(mem):
    tid = mem.new_tab(1, url="https://a.com")
    for i in range(10):
        mem.update_snapshot(tid, PageSnapshot(url=f"https://{i}.com"))
    hist = mem.get_snapshot_history(tid)
    assert len(hist) <= 5


def test_summary(mem):
    mem.new_tab(1, url="https://a.com")
    s = mem.summary()
    assert s["tab_count"] == 1


def test_clear(mem):
    mem.new_tab(1, url="https://a.com")
    mem.clear()
    assert mem.summary()["tab_count"] == 0


def test_link_helpers(mem):
    tid = mem.new_tab(1, url="https://a.com")
    snap = PageSnapshot(
        url="https://a.com",
        links=[
            {"text": "Home", "href": "/"},
            {"text": "About", "href": "/about"},
        ],
    )
    mem.update_snapshot(tid, snap)
    link = mem.find_link_by_ordinal(1)
    assert link is not None
    assert link["text"] == "Home"

    link2 = mem.find_link_by_text("about")
    assert link2 is not None
    assert "/about" in link2["href"]


def test_persistence(tmp_path):
    persist_file = tmp_path / "mem.json"
    m1 = BrowserMemory(persist_path=persist_file)
    m1.new_tab(1, url="https://x.com")
    m1.save()

    m2 = BrowserMemory(persist_path=persist_file)
    tabs = m2.list_tabs()
    assert len(tabs) == 1
    assert tabs[0].url == "https://x.com"
