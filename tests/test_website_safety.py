"""
Tests for the website safety confirmation flow.

Previously, a freshly discovered website (find_website's live-search
fallback in open_target) was opened immediately with no safety check --
a misleading or malicious search result could be opened without any
confirmation. Now, any result that trips a suspicious-URL heuristic
arms a pending confirmation (same pattern as push_project) instead of
opening right away, and only a confirmed-safe discovery is ever saved
into config so it starts showing up in the dashboard's website list.
"""


# ---------------- is_suspicious_url ----------------

def test_raw_ip_address_is_suspicious(engine):
    assert engine.is_suspicious_url("http://192.168.1.5/login") is True


def test_punycode_domain_is_suspicious(engine):
    assert engine.is_suspicious_url("https://xn--pypal-4ve.com") is True


def test_url_shortener_is_suspicious(engine):
    assert engine.is_suspicious_url("https://bit.ly/3xyzabc") is True


def test_throwaway_tld_is_suspicious(engine):
    assert engine.is_suspicious_url("https://totally-legit-bank.top") is True


def test_heavily_hyphenated_domain_is_suspicious(engine):
    assert engine.is_suspicious_url("https://secure-login-verify-account-now.com") is True


def test_normal_official_site_is_not_suspicious(engine):
    assert engine.is_suspicious_url("https://www.pcbway.com") is False


def test_malformed_url_is_treated_as_suspicious(engine):
    assert engine.is_suspicious_url("not a url") is True


# ---------------- open_target safety gating ----------------

def test_suspicious_discovery_is_not_opened_immediately(engine, monkeypatch):
    opened = []
    monkeypatch.setattr(engine, "find_website", lambda q: "http://192.168.1.5/pcbway")
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))

    result = engine.open_target("pcbway", announce=False)

    assert result.ok is True  # confirmation armed, not a failure
    assert opened == []  # never actually opened
    assert engine.pending_confirmation is not None
    assert engine.pending_confirmation["type"] == "open_url"
    assert "pcbway" not in engine.config.get("website_cache", {})
    assert "pcbway" not in engine.config.get("websites", {})


def test_safe_discovery_still_opens_immediately(engine, monkeypatch):
    opened = []
    monkeypatch.setattr(engine, "find_website", lambda q: "https://www.pcbway.com")
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))

    result = engine.open_target("pcbway", announce=False)

    assert result.ok is True
    assert opened == ["https://www.pcbway.com"]
    assert engine.pending_confirmation is None
    # A safe discovery is promoted straight into the visible websites list.
    assert engine.config["websites"]["pcbway"] == "https://www.pcbway.com"
    assert engine.config["website_cache"]["pcbway"] == "https://www.pcbway.com"


def test_confirm_open_opens_and_saves_the_suspicious_site(engine, monkeypatch):
    opened = []
    monkeypatch.setattr(engine, "find_website", lambda q: "http://192.168.1.5/pcbway")
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))

    engine.open_target("pcbway", announce=False)
    assert engine.pending_confirmation is not None

    result = engine.run_command("confirm open")

    assert result.ok is True
    assert opened == ["http://192.168.1.5/pcbway"]
    assert engine.pending_confirmation is None
    assert engine.config["websites"]["pcbway"] == "http://192.168.1.5/pcbway"


def test_cancel_open_never_opens_or_saves_the_site(engine, monkeypatch):
    opened = []
    monkeypatch.setattr(engine, "find_website", lambda q: "http://192.168.1.5/pcbway")
    monkeypatch.setattr(engine, "open_url", lambda url: opened.append(url))

    engine.open_target("pcbway", announce=False)
    result = engine.run_command("cancel")

    assert result.ok is True
    assert opened == []
    assert engine.pending_confirmation is None
    assert "pcbway" not in engine.config.get("websites", {})
    assert "pcbway" not in engine.config.get("website_cache", {})


def test_expired_open_confirmation_is_not_honored(engine, monkeypatch):
    monkeypatch.setattr(engine, "find_website", lambda q: "http://192.168.1.5/pcbway")
    monkeypatch.setattr(engine, "open_url", lambda url: None)

    engine.open_target("pcbway", announce=False)
    assert engine.pending_confirmation is not None
    engine.pending_confirmation["expires"] = 0  # force expiry

    result = engine.handle_pending_confirmation("confirm open")
    assert result is None  # falls through to normal parsing instead of firing
    assert engine.pending_confirmation is None


def test_saved_website_never_goes_through_safety_check(engine, monkeypatch):
    """Sites the user already saved themselves are trusted outright --
    the safety heuristic only ever applies to a brand-new live search
    result, never to config['websites'] or an existing cache entry."""
    engine.config["websites"]["evil"] = "http://192.168.1.5/whatever"
    called = []
    monkeypatch.setattr(engine, "find_website", lambda q: called.append(q) or "unused")
    monkeypatch.setattr(engine, "open_url", lambda url: None)

    result = engine.open_target("evil", announce=False)

    assert result.ok is True
    assert called == []  # find_website (and therefore the safety check) never runs
    assert engine.pending_confirmation is None
