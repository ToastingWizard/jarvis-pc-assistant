"""
Tests for the website finder workflow (open_target -> find_website ->
website_cache), matching the priority order: apps > saved websites >
folders > learned cache > live search, search only as a last resort.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from naitro_app import ActionResult  # noqa: E402


class FakeDDGS:
    """Stand-in for ddgs.DDGS so tests never hit the network."""
    results = []

    def __init__(self, *args, **kwargs):
        pass

    def text(self, query, max_results=5):
        return FakeDDGS.results


class BoomDDGS:
    def __init__(self, *args, **kwargs):
        pass

    def text(self, *args, **kwargs):
        raise RuntimeError("network down")


# ---------------- find_website ----------------

def test_find_website_returns_first_valid_result(engine, monkeypatch):
    FakeDDGS.results = [{"title": "PCBWay", "href": "https://www.pcbway.com", "body": "..."}]
    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    assert engine.find_website("pcbway") == "https://www.pcbway.com"


def test_find_website_skips_search_engine_result_pages(engine, monkeypatch):
    FakeDDGS.results = [
        {"title": "x", "href": "https://www.google.com/search?q=pcbway"},
        {"title": "y", "href": "https://www.pcbway.com"},
    ]
    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    assert engine.find_website("pcbway") == "https://www.pcbway.com"


def test_find_website_returns_none_with_no_results(engine, monkeypatch):
    FakeDDGS.results = []
    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    assert engine.find_website("asdkjaskldjaskld") is None


def test_find_website_handles_search_errors_gracefully(engine, monkeypatch):
    monkeypatch.setattr("ddgs.DDGS", BoomDDGS)
    assert engine.find_website("pcbway") is None  # must not raise


# ---------------- open_target priority order ----------------

def test_open_target_app_match_never_calls_finder(engine, monkeypatch):
    def boom(query):
        raise AssertionError("should not search when an app already matched")
    monkeypatch.setattr(engine, "find_website", boom)
    monkeypatch.setattr(engine, "launch", lambda target: ActionResult(True, "launched"))
    engine.config["apps"]["notepad"] = {"type": "command", "target": "notepad"}
    result = engine.open_target("notepad", announce=False)
    assert result.ok is True


def test_open_target_uses_cache_without_searching(engine, monkeypatch):
    engine.config["website_cache"]["pcbway"] = "https://www.pcbway.com"
    called = []
    monkeypatch.setattr(engine, "find_website", lambda q: called.append(q) or "unused")
    opened = []
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))

    result = engine.open_target("pcbway", announce=False)

    assert result.ok is True
    assert opened == ["https://www.pcbway.com"]
    assert called == []  # cache hit means the finder is never called


def test_open_target_searches_and_caches_on_first_miss(engine, monkeypatch):
    opened = []
    monkeypatch.setattr(engine, "find_website", lambda q: "https://www.pcbway.com")
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))

    result = engine.open_target("pcbway", announce=False)

    assert result.ok is True
    assert opened == ["https://www.pcbway.com"]
    assert engine.config["website_cache"]["pcbway"] == "https://www.pcbway.com"


def test_open_target_second_lookup_hits_cache_not_finder(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "find_website", lambda q: calls.append(q) or "https://www.pcbway.com")
    monkeypatch.setattr(engine, "open_url", lambda url: None)

    engine.open_target("pcbway", announce=False)  # first time: searches, caches
    engine.open_target("pcbway", announce=False)  # second time: should hit cache

    assert calls == ["pcbway"]  # finder only called once


def test_open_target_reports_not_found_when_search_fails(engine, monkeypatch):
    monkeypatch.setattr(engine, "find_website", lambda q: None)
    result = engine.open_target("totally-unknown-thing-xyz", announce=False)
    assert result.ok is False
    assert "totally-unknown-thing-xyz" not in engine.config.get("website_cache", {})


# ---------------- search command parsing + search_web ----------------

def test_search_for_phrase_is_recognized_as_search_action(engine):
    assert engine.extract_action_target("search for pcbway") == ("search", "pcbway")
    assert engine.extract_action_target("google pcbway pricing") == ("search", "pcbway pricing")


def test_search_web_opens_a_query_url(engine, monkeypatch):
    opened = []
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))
    result = engine.search_web("pcbway pricing")
    assert result.ok is True
    assert opened and "pcbway" in opened[0].lower()


def test_search_web_handles_empty_query(engine):
    result = engine.search_web("   ")
    assert result.ok is False
