"""Shared AI client used by NaiTRO's chat, code reviewer, and Browser Agent.

Extracted from the previously-duplicated Ollama-then-Gemini fallback in
``naitro_app.chat`` and ``naitro_reviewer``.  Centralises:

    * which providers to try, in what order
    * the actual HTTP plumbing (urllib, no extra SDKs)
    * response-format handling: free text vs. forced JSON

Exposes one public function:

    query_ai(prompt, *, response_format="text"|"json", config, log)
        -> str   (raw text from the model; caller parses JSON if needed)

Provider order is "NVIDIA NIM first (cloud, key-based), then Ollama
(local, no internet), then Gemini (cloud, key-based)".  NVIDIA is tried
first when a key is configured so the cloud model of choice takes
priority; Ollama is the local fallback when NVIDIA is unavailable or
unconfigured.  If no provider is available the function raises
:class:`AIClientError` so callers can fall back to their own defaults.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

# Increase the default urllib timeout for AI calls specifically. Chat is
# 120s, reviewer is 300s; the AI client lets the caller pass a custom
# timeout but defaults to a safe 60s for general use.
DEFAULT_TIMEOUT = 60

# Provider error classes so callers can distinguish "no providers
# configured" from "every provider failed".  A single class is enough for
# now — the message is the actionable bit.
class AIClientError(RuntimeError):
    """Raised when no configured AI provider could fulfil the request."""


def _ollama_generate(prompt: str, model: str, timeout: int, response_format: str) -> str:
    """POST to /api/generate on a local Ollama instance.

    ``response_format="json"`` adds ``"format": "json"`` to the payload,
    which tells Ollama to constrain output to a JSON object — important
    for the structured-output callers (reviewer, browser planner).
    """
    options: dict[str, Any] = {"temperature": 0.2}
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    if response_format == "json":
        payload["format"] = "json"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    return str(data.get("response", ""))


def _nvidia_generate(prompt: str, api_key: str, model: str, timeout: int, response_format: str) -> str:
    """POST to the NVIDIA NIM OpenAI-compatible chat completions endpoint.

    Uses ``Bearer`` token auth with the ``nvidia_api_key``.  When JSON
    output is requested we set ``response_format: {"type": "json_object"}``
    (the OpenAI-compatible knob this endpoint exposes) so the model
    returns valid JSON only — important for the structured-output
    callers (reviewer, browser planner).
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2048,
    }
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    return str(data["choices"][0]["message"]["content"])


def _gemini_generate(prompt: str, api_key: str, timeout: int, response_format: str) -> str:
    """POST to the Gemini generateContent endpoint.

    Uses ``gemini-2.5-flash`` (same model the reviewer used).  When JSON
    output is requested we set ``responseMimeType: application/json``;
    the Gemini API also respects the schema-less case for plain text.
    """
    gen_config: dict[str, Any] = {
        "maxOutputTokens": 2048,
        "temperature": 0.2,
    }
    if response_format == "json":
        gen_config["responseMimeType"] = "application/json"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }
    body = json.dumps(payload).encode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    return str(data["candidates"][0]["content"]["parts"][0]["text"])


def query_ai(
    prompt: str,
    *,
    config: dict[str, Any] | None = None,
    response_format: str = "text",
    timeout: int = DEFAULT_TIMEOUT,
    log: Callable[[str], None] | None = None,
) -> str:
    """Try NVIDIA NIM, then Ollama, then Gemini; raise :class:`AIClientError` if all fail.

    Parameters
    ----------
    prompt:
        The full prompt (system + user content already combined).
    config:
        Full NaiTRO config dict.  Used to read ``reviewer.ollama_model``,
        ``nvidia_api_key``, ``nvidia_model``, and ``gemini_api_key``.
        Optional — if missing or empty we skip the corresponding provider.
    response_format:
        ``"text"`` (default) or ``"json"``.  ``"json"`` makes NVIDIA set
        its JSON response_format, Ollama constrain to JSON, and Gemini set
        its JSON mime type.
    timeout:
        Per-provider HTTP timeout in seconds.
    log:
        Optional logger for per-provider failures.  Never raises from
        the log callback.

    Returns
    -------
    The raw model response text.  Callers parse JSON if they asked for
    ``response_format="json"``.
    """
    cfg = config or {}
    if response_format not in ("text", "json"):
        raise ValueError(f"response_format must be 'text' or 'json', got {response_format!r}")

    model = str(cfg.get("reviewer", {}).get("ollama_model", "phi3:mini"))
    nvidia_key = str(cfg.get("nvidia_api_key", "")).strip()
    nvidia_model = str(cfg.get("nvidia_model", "meta/llama-3.3-70b-instruct"))
    gemini_key = str(cfg.get("gemini_api_key", "")).strip()

    nvidia_error: Exception | None = None
    ollama_error: Exception | None = None

    # 1. NVIDIA NIM — cloud, needs an API key.  Try it first.
    if nvidia_key:
        try:
            return _nvidia_generate(prompt, api_key=nvidia_key, model=nvidia_model, timeout=timeout, response_format=response_format)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, json.JSONDecodeError, KeyError, UnicodeDecodeError, ValueError) as exc:
            nvidia_error = exc
            if log:
                log(f"AI client: NVIDIA failed ({exc.__class__.__name__}); trying Ollama")

    nvidia_status = (
        f"NVIDIA failed: {nvidia_error}" if nvidia_key else "NVIDIA skipped (no API key)"
    )

    # 2. Ollama — local, no API key required.
    try:
        return _ollama_generate(prompt, model=model, timeout=timeout, response_format=response_format)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, json.JSONDecodeError, KeyError, UnicodeDecodeError, ValueError) as exc:
        ollama_error = exc
        if log:
            log(f"AI client: Ollama unavailable ({exc.__class__.__name__}); trying Gemini")

    # 3. Gemini — last cloud fallback, only if a key is configured.
    if gemini_key:
        try:
            return _gemini_generate(prompt, api_key=gemini_key, timeout=timeout, response_format=response_format)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, json.JSONDecodeError, KeyError, UnicodeDecodeError, ValueError) as exc:
            if log:
                log(f"AI client: Gemini failed ({exc.__class__.__name__})")
            raise AIClientError(
                f"{nvidia_status}; Ollama failed: {ollama_error}; Gemini also failed: {exc}"
            ) from exc

    raise AIClientError(
        f"{nvidia_status}; Ollama failed: {ollama_error}; no Gemini API key configured."
    )
