"""AI-powered Git diff code review for NaiTRO."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ai_client import query_ai as _shared_query_ai


SEVERITIES = frozenset({"HIGH", "MEDIUM", "LOW"})


@dataclass
class ReviewIssue:
    file_path: str
    line_number: int
    description: str
    severity: str
    confidence: int
    suggestion: str

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line_number,
            "message": self.description,
            "severity": self.severity,
            "confidence": self.confidence,
            "fix": self.suggestion,
        }


@dataclass
class AnalysisResult:
    project_key: str
    project_path: str
    issues: list[ReviewIssue] = field(default_factory=list)
    status_text: str = ""
    diff_chars: int = 0
    source: str = "ai"
    reviewed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "HIGH")

    @property
    def medium_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "MEDIUM")

    def to_last_review(self) -> dict[str, Any]:
        return {
            "project": self.project_key,
            "path": self.project_path,
            "findings": [issue.to_display_dict() for issue in self.issues],
            "metrics": {
                "issue_count": self.issue_count,
                "high_count": self.high_count,
                "medium_count": self.medium_count,
                "diff_chars": self.diff_chars,
                "source": self.source,
                "reviewed_at": self.reviewed_at,
            },
        }


def changed_files_from_status(status_text: str) -> list[str]:
    files = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        rel = line[3:].strip()
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1].strip()
        files.append(rel.replace("\\", "/"))
    return files


def get_local_diff(run_git: Callable, project_path: Path, unified: int = 3) -> tuple[str, str]:
    """Return (status_short, combined_diff) for unstaged and staged changes."""
    status = run_git(project_path, ["status", "--short"])
    diff = run_git(project_path, ["diff", f"--unified={unified}"])
    staged = run_git(project_path, ["diff", "--cached", f"--unified={unified}"])
    combined = "\n".join(part for part in (diff.stdout, staged.stdout) if part)
    return status.stdout, combined


def truncate_diff(diff_text: str, max_chars: int) -> tuple[str, bool]:
    if len(diff_text) <= max_chars:
        return diff_text, False
    head = max_chars - 120
    return diff_text[:head] + "\n\n... [diff truncated for AI context] ...\n", True


def normalize_severity(value: str) -> str:
    upper = str(value or "LOW").strip().upper()
    if upper in SEVERITIES:
        return upper
    if "CRIT" in upper or "HIGH" in upper:
        return "HIGH"
    if "MED" in upper or "WARN" in upper:
        return "MEDIUM"
    return "LOW"


def parse_confidence(value: Any) -> int:
    try:
        num = int(float(value))
    except (TypeError, ValueError):
        return 50
    return max(0, min(100, num))


def extract_json_array(text: str) -> list[Any]:
    text = str(text or "").strip()
    if not text:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def coerce_review_issue(item: dict[str, Any], known_files: set[str]) -> ReviewIssue | None:
    if not isinstance(item, dict):
        return None
    file_path = (
        item.get("file_path")
        or item.get("file")
        or item.get("path")
        or "unknown"
    )
    file_path = str(file_path).replace("\\", "/").strip()
    if known_files and file_path != "unknown" and file_path not in known_files:
        basename = Path(file_path).name
        matches = [f for f in known_files if f == file_path or f.endswith("/" + basename) or f == basename]
        if not matches:
            return None
        if file_path not in known_files:
            file_path = matches[0]

    try:
        line_number = max(1, int(item.get("line_number") or item.get("line") or 1))
    except (TypeError, ValueError):
        line_number = 1

    description = str(item.get("description") or item.get("message") or "").strip()
    suggestion = str(item.get("suggestion") or item.get("fix") or "").strip()
    if not description:
        return None

    return ReviewIssue(
        file_path=file_path,
        line_number=line_number,
        description=description,
        severity=normalize_severity(item.get("severity", "LOW")),
        confidence=parse_confidence(item.get("confidence", 50)),
        suggestion=suggestion or "Review this change before pushing.",
    )


def parse_ai_issues(raw_text: str, known_files: list[str]) -> list[ReviewIssue]:
    known = {f.replace("\\", "/") for f in known_files}
    issues = []
    for item in extract_json_array(raw_text):
        if not isinstance(item, dict):
            continue
        issue = coerce_review_issue(item, known)
        if issue:
            issues.append(issue)
    issues.sort(key=lambda i: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[i.severity], -i.confidence))
    return issues[:20]


def build_review_prompt(diff_text: str, changed_files: list[str], truncated: bool) -> str:
    files_block = "\n".join(f"- {f}" for f in changed_files) or "- (none listed)"
    trunc_note = "Note: the diff was truncated; only report issues visible in the excerpt.\n" if truncated else ""
    return (
        "You are a senior code reviewer. Analyze ONLY the git diff below.\n"
        "Report real bugs, security risks, and poor practices in added or changed lines.\n"
        "Do not invent files or lines not supported by the diff.\n"
        f"{trunc_note}"
        f"Changed files:\n{files_block}\n\n"
        "Respond with ONLY a JSON array (no markdown, no prose). Each object must have:\n"
        '  "file_path", "line_number", "description", "severity" (HIGH|MEDIUM|LOW), '
        '"confidence" (0-100), "suggestion"\n'
        "Maximum 15 issues. If none, return [].\n\n"
        f"GIT DIFF:\n{diff_text}"
    )


def _query_review_ai(prompt: str, config: dict[str, Any], log: Callable[[str], None] | None) -> str:
    """Thin wrapper that pins the reviewer's preferred model + timeout
    and asks for JSON output. Delegates the actual provider fallback to
    the shared :mod:`ai_client` module so chat and review share one
    implementation of the Ollama-then-Gemini chain."""
    reviewer = config.get("reviewer", {})
    timeout = int(reviewer.get("ai_timeout_seconds", 300))
    return _shared_query_ai(
        prompt,
        config=config,
        response_format="json",
        timeout=timeout,
        log=log,
    )


def query_ai_structured(
    config: dict[str, Any],
    diff_text: str,
    changed_files: list[str],
    log: Callable[[str], None] | None = None,
) -> list[ReviewIssue]:
    reviewer = config.get("reviewer", {})
    max_chars = int(reviewer.get("max_diff_chars", 60000))
    diff_body, truncated = truncate_diff(diff_text, max_chars)
    prompt = build_review_prompt(diff_body, changed_files, truncated)

    try:
        raw = _query_review_ai(prompt, config, log)
    except Exception as exc:
        raise RuntimeError(f"AI review failed: {exc}") from exc

    issues = parse_ai_issues(raw, changed_files)
    if log and not issues and raw.strip() and raw.strip() not in ("[]", "{}"):
        log("AI review returned no parseable issues.")
    return issues


def merge_issues(ai_issues: list[ReviewIssue], rule_dicts: list[dict[str, Any]]) -> list[ReviewIssue]:
    merged = list(ai_issues)
    seen = {(i.file_path, i.line_number, i.description[:40]) for i in merged}
    for item in rule_dicts:
        issue = ReviewIssue(
            file_path=str(item.get("file", "unknown")),
            line_number=int(item.get("line") or 1),
            description=str(item.get("message", "")),
            severity=normalize_severity(item.get("severity", "LOW")),
            confidence=90,
            suggestion=str(item.get("fix", "")),
        )
        key = (issue.file_path, issue.line_number, issue.description[:40])
        if issue.description and key not in seen:
            merged.append(issue)
            seen.add(key)
    merged.sort(key=lambda i: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[i.severity], -i.confidence))
    return merged[:25]
