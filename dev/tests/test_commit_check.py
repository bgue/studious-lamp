"""dev/commit-check.sh on fixture git repos in tmp_path (V3-P2).

Each case commits one change on top of a base commit and pins the script's output and exit
code: a clean commit, a model name in the body, a mention only in the trailer lines (clean), and
a model name in a docs/reports line.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "commit-check.sh"
TRAILERS = (
    "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
    "Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4"
)
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    out = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=ENV,
        input=stdin,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-F", "-", stdin=message)
    return _git(repo, "rev-parse", "HEAD")


def _fixture(tmp_path: Path, message: str, files: dict[str, str]) -> tuple[Path, str, str]:
    """A repo with a base commit and one commit under test. Returns (repo, base sha, tested sha)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    base = _commit(repo, "V3-P2: base\n\nFixture base commit.", {"README.md": "base\n"})
    tested = _commit(repo, message, files)
    return repo, base, tested


def _run(repo: Path, base: str) -> subprocess.CompletedProcess[str]:
    script = repo / "dev" / "commit-check.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    return subprocess.run(
        ["bash", str(script), base],
        cwd=repo,
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
    )


CASES = [
    pytest.param(
        "V3-P2: add the gate\n\nPlain body, no model names.",
        {"dev/x.sh": "x\n"},
        0,
        "",
        id="clean",
    ),
    pytest.param(
        "V3-P2: add the gate\n\nSee /tmp/claude-0/run.log and https://claude.ai/code/session_1.",
        {"dev/x.sh": "x\n"},
        0,
        "",
        id="path-and-url-tokens-clean",
    ),
    pytest.param(
        f"V3-P2: add the gate\n\nDrafted with Opus.\n\n{TRAILERS}",
        {"dev/x.sh": "x\n"},
        1,
        "{sha} body opus\n",
        id="body-hit",
    ),
    pytest.param(
        f"V3-P2: add the gate\n\nPlain body.\n\n{TRAILERS}",
        {"dev/x.sh": "x\n"},
        0,
        "",
        id="trailer-only-mention",
    ),
    pytest.param(
        "V3-P2: add the gate\n\nPlain body.",
        {"docs/reports/P2-FORMS/V3-P2.md": "# V3-P2\n\nReviewed by Sonnet.\n"},
        1,
        "{sha} report sonnet\n",
        id="report-line-hit",
    ),
]


@pytest.mark.parametrize(("message", "files", "rc", "expected"), CASES)
def test_commit_check_output(
    tmp_path: Path, message: str, files: dict[str, str], rc: int, expected: str
) -> None:
    repo, base, tested = _fixture(tmp_path, message, files)
    result = _run(repo, base)
    assert result.returncode == rc, result.stdout + result.stderr
    assert result.stdout == expected.replace("{sha}", tested[:7])


def test_unknown_base_is_a_usage_error(tmp_path: Path) -> None:
    repo, _, _ = _fixture(tmp_path, "V3-P2: add\n\nPlain.", {"dev/x.sh": "x\n"})
    result = _run(repo, "no-such-ref")
    assert result.returncode == 2
    assert "unknown base" in result.stderr
