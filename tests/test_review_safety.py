"""
Tests for the code-review safety rails:

  * check_tracked_secret_files() flags files like config.json that are
    already committed to git, even outside the current diff — being in
    .gitignore only stops FUTURE commits, it doesn't undo history.
  * apply_review_fix() only ever applies the whitelisted .gitignore
    auto-fix on its own; anything else must be opened for a human to
    approve rather than changed automatically by voice command.
"""
import subprocess


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def test_tracked_config_json_is_flagged(engine_with_repo, git_repo):
    (git_repo / "config.json").write_text('{"gemini_api_key": "sk-fake"}', encoding="utf-8")
    git(git_repo, "add", "config.json")
    git(git_repo, "commit", "-q", "-m", "oops committed config.json")

    findings = engine_with_repo.check_tracked_secret_files(git_repo)
    files_flagged = {f["file"] for f in findings}
    assert "config.json" in files_flagged
    assert all(f["severity"] == "HIGH" for f in findings if f["file"] == "config.json")


def test_untracked_config_json_is_not_flagged(engine_with_repo, git_repo):
    """If it was never committed (the normal, correct state), there's
    nothing to warn about."""
    (git_repo / "config.json").write_text("{}", encoding="utf-8")  # untracked
    findings = engine_with_repo.check_tracked_secret_files(git_repo)
    assert findings == []


def test_apply_review_fix_only_auto_applies_gitignore_fix(engine, tmp_path):
    """A HIGH-severity finding without auto_fix == 'gitignore' (e.g. a
    hardcoded secret in source) must require human approval — apply_review_fix
    must never silently 'fix' it on its own."""
    engine.last_review = {
        "path": str(tmp_path),
        "findings": [
            {
                "file": "app.py",
                "line": 12,
                "severity": "HIGH",
                "message": "Possible secret or API key added to source control.",
                "fix": "Move the secret into config.json or an environment variable.",
                # deliberately no "auto_fix" key
            }
        ],
    }
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    result = engine.apply_review_fix(1)
    assert result.ok is False
    assert result.message == "Manual fix required"


def test_apply_review_fix_applies_whitelisted_gitignore_fix(engine, tmp_path):
    """The one thing apply_review_fix is allowed to do unsupervised:
    add a pattern to .gitignore for build/local-artifact noise."""
    project = tmp_path / "proj"
    project.mkdir()
    engine.last_review = {
        "path": str(project),
        "findings": [
            {
                "file": "build/output.bin",
                "line": 1,
                "severity": "LOW",
                "message": "Generated or local artifact is showing up in git changes.",
                "fix": "Add build/ to .gitignore instead of committing local artifacts.",
                "auto_fix": "gitignore",
                "ignore_pattern": "build/",
            }
        ],
    }
    result = engine.apply_review_fix(1)
    assert result.ok is True
    assert "build/" in (project / ".gitignore").read_text(encoding="utf-8")


def test_apply_review_fix_never_edits_source_files(engine, tmp_path):
    """apply_review_fix must not touch any file other than .gitignore,
    even for a finding that looks fixable."""
    project = tmp_path / "proj"
    project.mkdir()
    source_file = project / "app.py"
    original = "except Exception:\n    pass\n"
    source_file.write_text(original, encoding="utf-8")
    engine.last_review = {
        "path": str(project),
        "findings": [
            {
                "file": "app.py",
                "line": 1,
                "severity": "MEDIUM",
                "message": "Broad exception handler can hide real failures.",
                "fix": "Catch a narrower exception or log the exception details.",
                # no auto_fix -> must require human approval
            }
        ],
    }
    engine.apply_review_fix(1)
    assert source_file.read_text(encoding="utf-8") == original
