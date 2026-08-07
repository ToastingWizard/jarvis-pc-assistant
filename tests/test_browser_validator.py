"""Tests for browser_agent.validator shape validation and risk flagging."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Python"))

from browser_agent.types import BrowserAction, BrowserActionPlan, BrowserActionType
from browser_agent.validator import (
    validate_action,
    validate_plan,
    plan_has_confirmation_required,
    first_confirmation_action,
    risky_actions,
)


# ---- Shape validation ----

def test_navigate_needs_valid_url():
    ok = validate_action(BrowserAction(type=BrowserActionType.NAVIGATE, target="https://example.com"))
    assert ok.ok is True

    bad = validate_action(BrowserAction(type=BrowserActionType.NAVIGATE, target="not-a-url"))
    assert bad.ok is False


def test_click_needs_target():
    bad = validate_action(BrowserAction(type=BrowserActionType.CLICK))
    assert bad.ok is False
    assert "target" in bad.reason.lower()


def test_click_rejects_javascript():
    bad = validate_action(BrowserAction(type=BrowserActionType.CLICK, target="javascript:alert(1)"))
    assert bad.ok is False


def test_type_text_needs_value_or_target():
    bad = validate_action(BrowserAction(type=BrowserActionType.TYPE_TEXT))
    assert bad.ok is False


def test_press_key_needs_value():
    bad = validate_action(BrowserAction(type=BrowserActionType.PRESS_KEY))
    assert bad.ok is False


def test_new_tab_optional_url():
    ok = validate_action(BrowserAction(type=BrowserActionType.NEW_TAB))
    assert ok.ok is True
    ok2 = validate_action(BrowserAction(type=BrowserActionType.NEW_TAB, target="https://example.com"))
    assert ok2.ok is True
    bad = validate_action(BrowserAction(type=BrowserActionType.NEW_TAB, target="not-url"))
    assert bad.ok is False


def test_upload_file_checks_path_exists(tmp_path):
    fake = tmp_path / "test.txt"
    fake.write_text("hello")
    ok = validate_action(BrowserAction(
        type=BrowserActionType.UPLOAD_FILE,
        target="#file",
        value=str(fake),
    ))
    assert ok.ok is True


def test_upload_file_rejects_missing_path():
    bad = validate_action(BrowserAction(
        type=BrowserActionType.UPLOAD_FILE,
        target="#file",
        value="/nonexistent/file.txt",
    ))
    assert bad.ok is False


# ---- Risk flagging ----

def test_delete_click_triggers_confirmation():
    a = BrowserAction(type=BrowserActionType.CLICK, target='text="Delete account"')
    result = validate_action(a)
    assert result.ok is True
    assert a.requires_confirmation is True
    assert result.flipped_confirmation is True


def test_checkout_url_triggers_confirmation():
    a = BrowserAction(type=BrowserActionType.NAVIGATE, target="https://shop.com/checkout")
    result = validate_action(a)
    assert a.requires_confirmation is True


def test_normal_click_no_confirmation():
    a = BrowserAction(type=BrowserActionType.CLICK, target="text=Submit")
    result = validate_action(a)
    assert a.requires_confirmation is False


def test_upload_always_requires_confirmation(tmp_path):
    fake = tmp_path / "test.txt"
    fake.write_text("x")
    a = BrowserAction(type=BrowserActionType.UPLOAD_FILE, target="#file", value=str(fake))
    result = validate_action(a)
    assert a.requires_confirmation is True


# ---- Plan-level ----

def test_plan_has_confirmation_after_validation():
    plan = BrowserActionPlan(actions=[
        BrowserAction(type=BrowserActionType.READ_TEXT),
        BrowserAction(type=BrowserActionType.CLICK, target='text="Delete"'),
    ])
    # Must validate first to flip the requires_confirmation flag
    validate_plan(plan)
    assert plan_has_confirmation_required(plan) is True


def test_first_confirmation_action_after_validation():
    plan = BrowserActionPlan(actions=[
        BrowserAction(type=BrowserActionType.READ_TEXT),
        BrowserAction(type=BrowserActionType.CLICK, target='text="Delete"'),
    ])
    validate_plan(plan)
    first = first_confirmation_action(plan)
    assert first is not None
    assert first.type == BrowserActionType.CLICK


def test_risky_actions_yields_only_flagged():
    a1 = BrowserAction(type=BrowserActionType.READ_TEXT)
    a2 = BrowserAction(type=BrowserActionType.CLICK, target='text="Remove"')
    a2.requires_confirmation = True
    plan = BrowserActionPlan(actions=[a1, a2])
    risky = list(risky_actions(plan))
    assert len(risky) == 1
    assert risky[0].type == BrowserActionType.CLICK
