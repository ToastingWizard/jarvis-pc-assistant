"""Search URL templates for the Browser Agent.

Maps a spoken/typed site name + a query into a URL the executor can
navigate to. Site-specific quirks (YouTube uses ``search_query``,
Amazon uses ``s?k=``) are baked in here so the executor and planner
don't have to know them.

If the user names a site we don't have a template for, we fall back to
``https://<host>/?q=...`` and let the executor try to find a search
input on the page; if that fails the executor surfaces a clear error.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass


@dataclass
class SearchTarget:
    """Where to actually navigate to fulfil a search request."""

    url: str
    site: str  # canonical name (e.g. "youtube")
    query: str
    needs_input_fill: bool  # True if we couldn't construct a results URL and the executor must fill a search box


# Canonical site aliases. Keys are normalised (lowercased, no spaces).
# Each value is the URL template with ``{q}`` as a placeholder for the
# URL-encoded query.  ``input_selector`` is the CSS / role selector the
# executor should use as a fallback if the template URL doesn't work
# (e.g. for sites without a /search path that still have a search box
# on their homepage).
_SITE_TEMPLATES: dict[str, dict[str, str]] = {
    "google": {
        "url": "https://www.google.com/search?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "youtube": {
        "url": "https://www.youtube.com/results?search_query={q}",
        "input_selector": 'input[name="search_query"]',
    },
    "amazon": {
        "url": "https://www.amazon.com/s?k={q}",
        "input_selector": "#twotabsearchtextbox",
    },
    "github": {
        "url": "https://github.com/search?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "bing": {
        "url": "https://www.bing.com/search?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "duckduckgo": {
        "url": "https://duckduckgo.com/?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "ddg": {
        "url": "https://duckduckgo.com/?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "wikipedia": {
        "url": "https://en.wikipedia.org/w/index.php?search={q}",
        "input_selector": "#searchInput",
    },
    "wiki": {
        "url": "https://en.wikipedia.org/w/index.php?search={q}",
        "input_selector": "#searchInput",
    },
    "stackoverflow": {
        "url": "https://stackoverflow.com/search?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "stack overflow": {
        "url": "https://stackoverflow.com/search?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "reddit": {
        "url": "https://www.reddit.com/search/?q={q}",
        "input_selector": 'input[name="q"]',
    },
    "twitter": {
        "url": "https://twitter.com/search?q={q}",
        "input_selector": 'input[aria-label="Search query"]',
    },
    "x": {
        "url": "https://twitter.com/search?q={q}",
        "input_selector": 'input[aria-label="Search query"]',
    },
    "linkedin": {
        "url": "https://www.linkedin.com/search/results/all/?keywords={q}",
        "input_selector": 'input[aria-label="Search"]',
    },
    "facebook": {
        "url": "https://www.facebook.com/search/top/?q={q}",
        "input_selector": 'input[type="search"]',
    },
    "netflix": {
        "url": "https://www.netflix.com/search?q={q}",
        "input_selector": 'input[type="search"]',
    },
}


def _normalise_site(site: str) -> str:
    return re.sub(r"\s+", " ", (site or "").strip().lower())


def _domain_for(site: str) -> str | None:
    """Best-effort guess at a domain for a site we don't have a template for."""
    s = _normalise_site(site)
    if not s:
        return None
    s = s.replace(" ", "")
    if "." in s and " " not in s:
        return s
    return f"www.{s}.com"


def build_search_url(site: str, query: str) -> SearchTarget:
    """Resolve ``(site, query)`` to a :class:`SearchTarget`.

    If we have a template for the site, the URL points straight at the
    search results page. Otherwise we point at the site root and tell
    the executor it will need to locate a search input.
    """
    norm_site = _normalise_site(site)
    encoded = urllib.parse.quote_plus(query or "")
    template = _SITE_TEMPLATES.get(norm_site)
    if template is not None:
        url = template["url"].format(q=encoded)
        return SearchTarget(url=url, site=norm_site, query=query, needs_input_fill=False)

    domain = _domain_for(norm_site)
    if domain is None:
        # Last-ditch: search the web for "site + query" via Google.
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"{site} {query}")
        return SearchTarget(url=url, site="google", query=f"{site} {query}", needs_input_fill=False)
    return SearchTarget(url=f"https://{domain}/", site=norm_site, query=query, needs_input_fill=True)


def input_selector_for(site: str) -> str | None:
    """The fallback search-input selector for a site, if we know one."""
    template = _SITE_TEMPLATES.get(_normalise_site(site))
    if template is None:
        return None
    return template.get("input_selector")


def known_sites() -> list[str]:
    return sorted(_SITE_TEMPLATES.keys())


# Patterns users often use to phrase a search request. Used by the
# engine's command extractor so "search YouTube for X" / "google X" /
# "look up X on Amazon" all map to the same brain path.
_SEARCH_VERB_RE = re.compile(
    r"^\s*(?:search(?:\s+for)?|google|look\s+up|find|query)\s+(.+?)\s+on\s+([a-z0-9 .\-]+?)\s*$",
    re.IGNORECASE,
)
_SEARCH_VERB_REVERSE_RE = re.compile(
    r"^\s*(?:search(?:\s+for)?|google|look\s+up|find|query)\s+([a-z0-9 .\-]+?)\s+for\s+(.+?)\s*$",
    re.IGNORECASE,
)
_GOOGLE_BARE_RE = re.compile(
    r"^\s*(?:google|search(?:\s+for)?|look\s+up)\s+(.+)$",
    re.IGNORECASE,
)


def parse_search_command(text: str) -> tuple[str, str] | None:
    """Parse a user search command into ``(site, query)``.

    Returns ``None`` for commands the engine shouldn't try to interpret
    as a search.  Examples::

        "search YouTube for python tutorials" -> ("youtube", "python tutorials")
        "google best gpu 2025"                 -> ("google", "best gpu 2025")
        "look up datasheets on digikey"        -> ("digikey", "datasheets")
        "search the web for foo"               -> ("google", "foo")
    """
    norm = (text or "").strip()
    if not norm:
        return None
    m = _SEARCH_VERB_RE.match(norm)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = _SEARCH_VERB_REVERSE_RE.match(norm)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    m = _GOOGLE_BARE_RE.match(norm)
    if m:
        return "google", m.group(1).strip()
    return None
