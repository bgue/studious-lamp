"""dev/review-pack.sh prints one review pack per branch (P2-W0 ticket A2).

The fixture repository lives in ``tmp_path``: a base commit with the ticket, its provided test and
the test file, then one branch. The dirty branch changes a file outside Allowed paths, a test that
differs from its provided copy, and has a commit subject without the ticket id; the clean branch
changes only the allowed file. No network.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dev" / "review-pack.sh"
SECTIONS = ("DIFFSTAT", "SYMBOLS", "PATHS", "TESTS", "COMMITS", "GATE")

TICKET = """# P9-X1-T01 — a

## Allowed paths
- `src/a.py` (create)

## Tests to add
- `tests/test_a.py`: mapping `docs/tickets/P9-X1/provided/test_a.py` -> `tests/test_a.py`
"""
PROVIDED = "def test_a():\n    assert True\n"


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    done = subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    )
    return done.stdout


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo: Path, subject: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", subject)


def base_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "trunk")
    write(repo, "docs/tickets/P9-X1/T01-a.md", TICKET)
    write(repo, "docs/tickets/P9-X1/provided/test_a.py", PROVIDED)
    write(repo, "src/a.py", "def f():\n    return 1\n")
    write(repo, "tests/test_a.py", PROVIDED)
    commit_all(repo, "trunk: base")
    return repo


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=repo, capture_output=True, text=True, check=False
    )


def sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        if line in SECTIONS:
            current = line
            out[current] = []
        elif current:
            out[current].append(line)
    return out


def test_dirty_branch_names_the_boundary_test_and_message_findings(tmp_path: Path) -> None:
    repo = base_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "p9/x1-t01-a")
    write(repo, "src/a.py", "def f():\n    return 2\n")
    write(repo, "src/b.py", "def g():\n    return 3\n")
    write(repo, "tests/test_a.py", "def test_a():\n    assert False\n")
    commit_all(repo, "fix stuff")

    result = run(repo, "trunk", "p9/x1-t01-a")

    assert result.returncode == 1, result.stdout + result.stderr
    parts = sections(result.stdout)
    assert list(parts) == list(SECTIONS)
    assert parts["PATHS"] == ["src/b.py", "tests/test_a.py"]
    assert parts["TESTS"] == ["tests/test_a.py present", "cmp differs tests/test_a.py"]
    assert len(parts["COMMITS"]) == 1
    assert parts["COMMITS"][0].endswith("fix stuff  BAD-MSG")
    assert len(result.stdout.splitlines()) <= 60


def test_clean_branch_prints_ok_and_exits_zero(tmp_path: Path) -> None:
    repo = base_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "p9/x1-t01-b")
    write(repo, "src/a.py", "def f():\n    return 2\n")
    commit_all(repo, "P9-X1-T01: f returns 2")

    result = run(repo, "trunk", "p9/x1-t01-b", "docs/tickets/P9-X1/T01-a.md")

    assert result.returncode == 0, result.stdout + result.stderr
    parts = sections(result.stdout)
    assert parts["PATHS"] == ["OK"]
    assert parts["TESTS"] == ["tests/test_a.py present", "cmp same tests/test_a.py"]
    assert len(parts["COMMITS"]) == 1
    assert "BAD-MSG" not in parts["COMMITS"][0]
    assert parts["GATE"] == ["g-"]
    assert len(result.stdout.splitlines()) <= 60


def test_bad_usage_exits_two(tmp_path: Path) -> None:
    repo = base_repo(tmp_path)
    assert run(repo).returncode == 2
