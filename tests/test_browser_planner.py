"""Tests for browser_agent.planner — reflexive plans and JSON parsing."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Python"))

from browser_agent.types import BrowserActionType
from browser_agent.planner import (
    reflexive_plan,
    parse_plan,
    _extract_json_object,
)


# ---- reflexive_plan: navigation ----

def test_open_url():
    p = reflexive_plan("open https://example.com")
    assert p is not None
    assert p.actions[0].type == BrowserActionType.NAVIGATE
    assert p.actions[0].target == "https://example.com"


def test_go_to_url():
    p = reflexive_plan("go to https://google.com")
    assert p.actions[0].type == BrowserActionType.NAVIGATE


def test_bare_domain():
    p = reflexive_plan("open example.com")
    assert p.actions[0].type == BrowserActionType.NAVIGATE
    assert p.actions[0].target == "https://example.com"


def test_bare_url_in_text():
    p = reflexive_plan("visit https://test.com/page")
    assert p.actions[0].type == BrowserActionType.NAVIGATE


# ---- reflexive_plan: search ----

def test_search_on_site():
    p = reflexive_plan("search python tutorials on youtube")
    assert p.actions[0].type == BrowserActionType.SEARCH
    assert p.actions[0].value == "youtube"
    assert p.actions[0].target == "python tutorials"


def test_google_bare():
    p = reflexive_plan("google best gpu 2025")
    assert p.actions[0].type == BrowserActionType.SEARCH
    assert p.actions[0].value == "google"


# ---- reflexive_plan: navigation actions ----

def test_go_back():
    p = reflexive_plan("go back")
    assert p.actions[0].type == BrowserActionType.BACK


def test_go_forward():
    p = reflexive_plan("forward")
    assert p.actions[0].type == BrowserActionType.FORWARD


def test_reload():
    p = reflexive_plan("reload page")
    assert p.actions[0].type == BrowserActionType.RELOAD


# ---- reflexive_plan: reading ----

def test_read_page():
    p = reflexive_plan("read page")
    assert p.actions[0].type == BrowserActionType.READ_TEXT


def test_whats_on_page():
    p = reflexive_plan("what's on the page")
    assert p.actions[0].type == BrowserActionType.READ_TEXT


def test_read_title():
    p = reflexive_plan("page title")
    assert p.actions[0].type == BrowserActionType.READ_TITLE


def test_read_url():
    p = reflexive_plan("what's the url")
    assert p.actions[0].type == BrowserActionType.READ_URL


def test_extract_links():
    p = reflexive_plan("extract links")
    assert p.actions[0].type == BrowserActionType.EXTRACT_LINKS


# ---- reflexive_plan: scroll ----

def test_scroll_down():
    p = reflexive_plan("scroll down")
    assert p.actions[0].type == BrowserActionType.SCROLL
    assert p.actions[0].params["direction"] == "down"


def test_scroll_up():
    p = reflexive_plan("scroll to top")
    assert p.actions[0].params["direction"] == "top"


def test_scroll_bottom():
    p = reflexive_plan("scroll to bottom")
    assert p.actions[0].params["direction"] == "bottom"


# ---- reflexive_plan: screenshot ----

def test_screenshot():
    p = reflexive_plan("take a screenshot")
    assert p.actions[0].type == BrowserActionType.SCREENSHOT


# ---- reflexive_plan: click ----

def test_click_text():
    p = reflexive_plan('click "Submit"')
    assert p.actions[0].type == BrowserActionType.CLICK
    assert "submit" in p.actions[0].target.lower()


# ---- reflexive_plan: unknown ----

def test_unknown_returns_none():
    p = reflexive_plan("tell me a joke")
    assert p is None


# ---- _extract_json_object ----

def test_extract_plain_json():
    r = _extract_json_object('{"a": 1}')
    assert r == {"a": 1}


def test_extract_fenced():
    r = _extract_json_object('```json\n{"a": 1}\n```')
    assert r == {"a": 1}


def test_extract_with_preamble():
    r = _extract_json_object('Here is the plan:\n{"thought": "hi", "actions": []}')
    assert r is not None
    assert r["thought"] == "hi"


def test_extract_empty_returns_none():
    assert _extract_json_object("") is None
    assert _extract_json_object("no json here") is None


# ---- parse_plan ----

def test_parse_plan_valid():
    raw = '{"thought": "test", "actions": [{"type": "read_text"}]}'
    plan = parse_plan(raw)
    assert plan.thought == "test"
    assert len(plan.actions) == 1
    assert plan.actions[0].type == BrowserActionType.READ_TEXT


def test_parse_plan_fenced():
    raw = '```json\n{"thought": "hi", "actions": [{"type": "click", "target": "text=OK"}]}\n```'
    plan = parse_plan(raw)
    assert len(plan.actions) == 1


def test_parse_plan_mixed_valid_invalid():
    raw = '{"thought": "t", "actions": [{"type": "click", "target": "OK"}, {"type": "invalid"}]}'
    plan = parse_plan(raw)
    assert len(plan.actions) == 1  # invalid one skipped


def test_parse_plan_garbage():
    plan = parse_plan("not json at all")
    assert len(plan.actions) == 0
    assert plan.raw_response == "not json at all"
