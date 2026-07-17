"""Shared pytest fixtures for the JARVIS test suite.

These tests exercise JarvisEngine directly (not the Tkinter JarvisUI),
since JarvisEngine holds all the actual decision-making logic — wake
word / conversation gating, git push, and code review rules — and can
be tested headlessly without a display.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import JARVIS_app  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    """A JarvisEngine pointed at a throwaway config file, with TTS
    disabled so tests don't spawn real speech threads."""
    config_path = tmp_path / "config.json"
    eng = JARVIS_app.JarvisEngine(config_path=config_path, log=lambda text: None)
    eng.config["voice"]["speak_responses"] = False
    return eng


@pytest.fixture
def git_repo(tmp_path):
    """A real, throwaway git repository on disk for push/review tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def engine_with_repo(engine, git_repo):
    """An engine configured so the 'jarvis' project points at git_repo."""
    engine.config["projects"] = {"jarvis": str(git_repo)}
    engine.config["reviewer"]["default_project"] = "jarvis"
    return engine
