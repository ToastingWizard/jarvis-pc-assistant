"""
Regression tests for the git push confirmation flow.

Previously, saying "push to github" (or a misheard phrase matching that
pattern) would run `git push` immediately with no confirmation step.
Now push_project() only arms a pending confirmation; the actual push
only runs if the very next command is a clear confirmation phrase,
within a short timeout.
"""


def enable_push(engine):
    engine.config["reviewer"]["allow_push"] = True


def test_push_is_not_immediate(engine_with_repo, git_repo):
    """The core fix: calling push_project() must NOT push by itself."""
    enable_push(engine_with_repo)
    result = engine_with_repo.push_project("naitro")
    assert result.ok is True
    assert "confirm" in result.message.lower() or "await" in result.message.lower()
    assert engine_with_repo.pending_confirmation is not None
    assert engine_with_repo.pending_confirmation["type"] == "push"


def test_push_disabled_by_config_short_circuits_before_confirmation(engine_with_repo):
    engine_with_repo.config["reviewer"]["allow_push"] = False
    result = engine_with_repo.push_project("naitro")
    assert result.ok is False
    assert engine_with_repo.pending_confirmation is None


def test_confirm_push_runs_git_push(engine_with_repo, git_repo, tmp_path):
    enable_push(engine_with_repo)

    # Give the repo somewhere to push to: a bare remote.
    import subprocess
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=git_repo, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD"], cwd=git_repo, check=True)

    engine_with_repo.push_project("naitro")
    assert engine_with_repo.pending_confirmation is not None

    result = engine_with_repo.run_command("confirm push")
    assert result.ok is True
    assert engine_with_repo.pending_confirmation is None


def test_cancel_push_does_not_push(engine_with_repo, git_repo):
    enable_push(engine_with_repo)
    engine_with_repo.push_project("naitro")
    assert engine_with_repo.pending_confirmation is not None

    result = engine_with_repo.run_command("cancel")
    assert result.ok is True
    assert engine_with_repo.pending_confirmation is None


def test_expired_confirmation_is_not_honored(engine_with_repo, git_repo, monkeypatch):
    """A stale, timed-out confirmation should not fire just because the
    user happens to say 'confirm' minutes later for something unrelated."""
    enable_push(engine_with_repo)
    engine_with_repo.push_project("naitro")
    assert engine_with_repo.pending_confirmation is not None

    # Force it to look expired.
    engine_with_repo.pending_confirmation["expires"] = 0

    result = engine_with_repo.handle_pending_confirmation("confirm push")
    assert result is None  # falls through to normal command parsing
    assert engine_with_repo.pending_confirmation is None


def test_dirty_tree_blocks_push_before_confirmation(engine_with_repo, git_repo):
    enable_push(engine_with_repo)
    (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
    result = engine_with_repo.push_project("naitro")
    assert result.ok is False
    assert engine_with_repo.pending_confirmation is None
