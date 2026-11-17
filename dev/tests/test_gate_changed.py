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
    "dev/tests/test_x.py": "def test_x() -> None:\n    pass\n",
    "tests/conftest.py": "import pytest\n",
    "justfile": "gate:\n    true\n",
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


HEAVY = "heavy (slots tl-heavy.lock, tl-heavy.2.lock)"
DEVTESTS_SKIP = "plan devtests: skip (no dev/ change)"


def _plan(
    base: str,
    changed: str,
    ruff: str,
    pyright: str,
    tests: str,
    pg: str,
    devtests: str = DEVTESTS_SKIP,
) -> list[str]:
    return [
        f"gate-changed: base {base[:7]} (given)",
        changed,
        ruff,
        pyright,
        f"plan commit: dev/commit-check.sh {base[:7]}",
        devtests,
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
        f"plan tests: {HEAVY} bash dev/gate.sh packages/tl-modules/awp/tests " + " ".join(WALK),
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
        f"plan tests: {HEAVY} bash dev/gate.sh packages/tl-core/tests " + " ".join(WALK),
        f"plan gate-pg: {HEAVY} bash dev/gate.sh --postgres tests/confidentiality",
    )


def test_docs_only_plan(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"docs/README.md": "changed\n"})
    lines = _dry_run(repo, base)
    assert lines == _plan(
        base,
        "changed: 1 files, 0 .py",
        "plan ruff: skip (no changed .py files)",
        "plan pyright: skip (no changed .py files)",
        f"plan tests: {HEAVY} bash dev/gate.sh " + " ".join(WALK),
        "plan gate-pg: skip (no adapter, confidentiality or projector path)",
    )


def test_dev_change_plan_runs_dev_tests_unlocked(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"dev/notes.md": "changed\n"})
    lines = _dry_run(repo, base)
    assert lines == _plan(
        base,
        "changed: 1 files, 0 .py",
        "plan ruff: skip (no changed .py files)",
        "plan pyright: skip (no changed .py files)",
        f"plan tests: {HEAVY} bash dev/gate.sh " + " ".join(WALK),
        "plan gate-pg: skip (no adapter, confidentiality or projector path)",
        "plan devtests: bash dev/gate.sh dev/tests (light, no heavy slot)",
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


def test_top_level_tests_file_runs_all_of_tests(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"tests/conftest.py": "import pytest  # changed\n"})
    lines = _dry_run(repo, base)
    assert lines == _plan(
        base,
        "changed: 1 files, 1 .py",
        "plan ruff: ruff check, ruff format --check tests/conftest.py",
        "plan pyright: tests/conftest.py",
        f"plan tests: {HEAVY} bash dev/gate.sh tests",
        "plan gate-pg: skip (no adapter, confidentiality or projector path)",
    )


def test_justfile_change_warns_and_runs_nothing_extra(tmp_path: Path) -> None:
    repo, base = _fixture(tmp_path, {"justfile": "gate:\n    echo changed\n"})
    lines = _dry_run(repo, base)
    assert lines[0] == "warn: justfile maps to no tests"
    assert lines[1:] == [
        f"gate-changed: base {base[:7]} (given)",
        "changed: 1 files, 0 .py",
        "plan ruff: skip (no changed .py files)",
        "plan pyright: skip (no changed .py files)",
        f"plan commit: dev/commit-check.sh {base[:7]}",
        "plan devtests: skip (no dev/ change)",
        f"plan tests: {HEAVY} bash dev/gate.sh " + " ".join(WALK),
        "plan gate-pg: skip (no adapter, confidentiality or projector path)",
        "plan perf: skip (no tests/perf)",
        "gate: DRY-RUN",
    ]


# Stubs for the real run: uv answers ruff and pyright with an exit code from the environment,
# and the fixture's dev/gate.sh answers with STUB_GATE_RC. Nothing heavy runs; the locks are
# in tmp_path.
UV_STUB = """#!/usr/bin/env bash
case " $* " in
  *" ruff "*) exit "${STUB_RUFF_RC:-0}" ;;
  *" pyright "*) exit "${STUB_PYRIGHT_RC:-0}" ;;
esac
exit 0
"""
GATE_STUB = """#!/usr/bin/env bash
echo "part 1: exit ${STUB_GATE_RC:-0}, stub run"
exit "${STUB_GATE_RC:-0}"
"""


def _real_fixture(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name in ("gate-changed.sh", "commit-check.sh"):
        target = repo / "dev" / name
        target.parent.mkdir(exist_ok=True)
        target.write_text((REPO / "dev" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "dev" / "gate.sh").write_text(GATE_STUB, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text(UV_STUB, encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    _write(repo, {"packages/tl-core/tests/test_core.py": "def test_core() -> None:\n    pass\n"})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "V3-P2: base")
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, {"packages/tl-core/src/tl_core/x.py": "VALUE = 2\n"})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "V3-P2: change")
    env = {
        **ENV,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TL_HEAVY_LOCK_DIR": str(tmp_path / "locks"),
    }
    return repo, {"base": base, **env}


def _real_run(
    repo: Path, env: dict[str, str], base: str, **stubs: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "dev/gate-changed.sh", base],
        cwd=repo,
        env={**env, **stubs},
        check=False,
        capture_output=True,
        text=True,
    )


def test_real_run_all_green(tmp_path: Path) -> None:
    repo, env = _real_fixture(tmp_path)
    base = env.pop("base")
    result = _real_run(repo, env, base)
    lines = result.stdout.splitlines()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ruff: PASS 1 files" in lines
    assert "pyright: PASS 1 files" in lines
    assert "tests: PASS part 1: exit 0, stub run" in lines
    assert lines[-1] == "gate: PASS"


def test_real_run_stops_at_first_red(tmp_path: Path) -> None:
    repo, env = _real_fixture(tmp_path)
    base = env.pop("base")
    result = _real_run(repo, env, base, STUB_RUFF_RC="1")
    lines = result.stdout.splitlines()
    assert result.returncode == 1
    assert any(line.startswith("ruff: FAIL") for line in lines)
    assert not any(line.startswith(("pyright:", "tests:")) for line in lines)
    assert lines[-1] == "gate: FAIL"


def test_real_run_test_step_red_is_last_gate_fail(tmp_path: Path) -> None:
    repo, env = _real_fixture(tmp_path)
    base = env.pop("base")
    result = _real_run(repo, env, base, STUB_GATE_RC="1")
    lines = result.stdout.splitlines()
    assert result.returncode == 1
    assert any(line.startswith("tests: FAIL exit 1") for line in lines)
    assert lines[-1] == "gate: FAIL"
