"""Tests for browser_agent.search module."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Python"))

from browser_agent.search import (
    build_search_url,
    input_selector_for,
    known_sites,
    parse_search_command,
)


# ---- build_search_url ----

def test_known_site():
    target = build_search_url("google", "python tutorial")
    assert "google.com" in target.url
    assert "python+tutorial" in target.url
    assert target.needs_input_fill is False
    assert target.site == "google"


def test_youtube_site():
    target = build_search_url("youtube", "cats")
    assert "search_query=cats" in target.url
    assert target.needs_input_fill is False


def test_unknown_site_fallback():
    target = build_search_url("mysite", "query")
    assert target.needs_input_fill is True
    assert "mysite.com" in target.url


def test_empty_site_fallbacks_to_google():
    target = build_search_url("", "some query")
    assert "google.com" in target.url
    assert "some+query" in target.url


# ---- input_selector_for ----

def test_input_selector_known():
    sel = input_selector_for("google")
    assert sel is not None
    assert "q" in sel


def test_input_selector_unknown():
    sel = input_selector_for("mysite")
    assert sel is None


# ---- known_sites ----

def test_known_sites_list():
    sites = known_sites()
    assert "google" in sites
    assert "youtube" in sites
    assert "reddit" in sites


# ---- parse_search_command ----

def test_search_verb_on_site():
    site, query = parse_search_command("search python tutorials on youtube")
    assert site == "youtube"
    assert query == "python tutorials"


def test_search_verb_reverse():
    site, query = parse_search_command("search youtube for python tutorials")
    assert site == "youtube"
    assert query == "python tutorials"


def test_google_bare():
    site, query = parse_search_command("google best gpu 2025")
    assert site == "google"
    assert query == "best gpu 2025"


def test_look_up():
    site, query = parse_search_command("look up datasheets on digikey")
    assert site == "digikey"
    assert query == "datasheets"


def test_non_search_returns_none():
    assert parse_search_command("open notepad") is None
    assert parse_search_command("hello world") is None
    assert parse_search_command("") is None
