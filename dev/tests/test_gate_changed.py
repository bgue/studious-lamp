"""dev/gate-changed.sh --dry-run on fixture git repos in tmp_path (V3-P2).

The fixture is a small tree with the paths the plan looks at (a module, the core, the
confidentiality walk set, a docs file). Each case commits one change on top of a base commit and
pins the plan the script prints. Nothing runs: no ruff, pyright, commit check or test session, and
no .gate directory is created.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "gate-changed.sh"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}
BASE_FILES = {
    "packages/tl-core/src/tl_core/confidentiality.py": "VALUE = 1\n",
    "packages/tl-core/tests/test_core.py": "def test_core() -> None:\n    pass\n",
    "packages/tl-modules/awp/src/awp.py": "VALUE = 1\n",
    "packages/tl-modules/awp/tests/test_awp.py": "def test_awp() -> None:\n    pass\n",
    "tests/confidentiality/test_twin_walk.py": "from twin_channels import LEAKS\n",
    "tests/confidentiality/twin_channels.py": "LEAKS = []\n",
    "tests/confidentiality/test_hidden_sql_equal_old.py": "def test_sql() -> None:\n    pass\n",
    "tests/confidentiality/test_paths_equal_old.py": "def test_paths() -> None:\n    pass\n",
    "tests/confidentiality/test_core.py": "def test_other() -> None:\n    pass\n",
    "docs/README.md": "base\n",
}
WALK = [
    "tests/confidentiality/test_hidden_sql_equal_old.py",
    "tests/confidentiality/test_paths_equal_old.py",
    "tests/confidentiality/test_twin_walk.py",
]


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=ENV,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _fixture(tmp_path: Path, change: dict[str, str]) -> tuple[Path, str]:
    """A repo with the base tree (and the script in dev/), then one commit with `change`.

    Returns the repo and the base sha. The script is copied in because it works from its own
    location.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "dev").mkdir()
    script = repo / "dev" / "gate-changed.sh"
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    _write(repo, BASE_FILES)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "V3-P2: base")
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, change)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "V3-P2: change")
    return repo, base


def _dry_run(repo: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["bash", "dev/gate-changed.sh", "--dry-run", *args],
        cwd=repo,
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (repo / ".gate").exists()
    return result.stdout.splitlines()


def _plan(base: str, changed: str, ruff: str, pyright: str, tests: str, pg: str) -> list[str]:
    return [
        f"gate-changed: base {base[:7]} (given)",
        changed,
        ruff,
        pyright,
        f"plan commit: dev/commit-check.sh {base[:7]}",
        tests,
        pg,
        "plan perf: skip (no tests/perf)",
        "gate: DRY-RUN",
    ]


def test_module_file_plan(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"packages/tl-modules/awp/src/awp.py": "VALUE = 2\n"})
    lines = _dry_run(repo, base)
    src = "packages/tl-modules/awp/src/awp.py"
    assert lines == _plan(
        base,
        "changed: 1 files, 1 .py",
        f"plan ruff: ruff check, ruff format --check {src}",
        f"plan pyright: {src}",
        "plan tests: flock /tmp/claude-0/tl-gate.lock bash dev/gate.sh "
        "packages/tl-modules/awp/tests " + " ".join(WALK),
        "plan gate-pg: skip (no adapter, confidentiality or projector path)",
    )


def test_core_confidentiality_plan(tmp_path: Path) -> None:
    src = "packages/tl-core/src/tl_core/confidentiality.py"
    repo, base = _fixture(tmp_path, {src: "VALUE = 2\n"})
    lines = _dry_run(repo, base)
    assert lines == _plan(
        base,
        "changed: 1 files, 1 .py",
        f"plan ruff: ruff check, ruff format --check {src}",
        f"plan pyright: {src}",
        "plan tests: flock /tmp/claude-0/tl-gate.lock bash dev/gate.sh "
        "packages/tl-core/tests " + " ".join(WALK),
        "plan gate-pg: flock /tmp/claude-0/tl-gate.lock "
        "bash dev/gate.sh --postgres tests/confidentiality",
    )


def test_docs_only_plan(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"docs/README.md": "changed\n"})
    lines = _dry_run(repo, base)
    assert lines == _plan(
        base,
        "changed: 1 files, 0 .py",
        "plan ruff: skip (no changed .py files)",
        "plan pyright: skip (no changed .py files)",
        "plan tests: flock /tmp/claude-0/tl-gate.lock bash dev/gate.sh " + " ".join(WALK),
        "plan gate-pg: skip (no adapter, confidentiality or projector path)",
    )


def test_default_base_is_merge_base_with_forms_branch(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"docs/README.md": "changed\n"})
    _git(repo, "branch", "p2/v3-forms", base)
    lines = _dry_run(repo)
    assert lines[0] == f"gate-changed: base {base[:7]} (merge-base with p2/v3-forms)"


def test_unknown_base_is_a_usage_error(tmp_path: Path) -> None:
    repo, _ = _fixture(tmp_path, {"docs/README.md": "changed\n"})
    result = subprocess.run(
        ["bash", "dev/gate-changed.sh", "--dry-run", "no-such-ref"],
        cwd=repo,
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "base not found" in result.stderr


def test_unknown_option_is_a_usage_error(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"docs/README.md": "changed\n"})
    result = subprocess.run(
        ["bash", "dev/gate-changed.sh", "--bogus", base],
        cwd=repo,
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
