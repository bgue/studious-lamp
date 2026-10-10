"""``run_tests`` (brief 25.3, FANOUT D12): filtered pytest in a child process, reports, refusals.

The pytest runs happen in a small repository built in ``tmp_path``; the child never sees the real
repository, the real environment or a real database.
"""

from __future__ import annotations

import dataclasses
import os
import re
import time
from pathlib import Path

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from tl_mcp.dev.server import build_dev_server

CONFTEST = """\
def pytest_configure(config):
    config.addinivalue_line("markers", "parity: cross-adapter parity test")
    config.addinivalue_line("markers", "requires_postgres: needs a Postgres")
"""

OK_TESTS = """\
def test_ok_one():
    assert 1 + 1 == 2


def test_ok_two():
    assert "a" < "b"
"""

FAIL_TESTS = """\
def test_fail_one():
    assert 1 == 2
"""

SLOW_TESTS = """\
import time


def test_slow_one():
    time.sleep(30)
"""

MARKER_TESTS = """\
import pytest


@pytest.mark.parity
def test_parity_one():
    assert True


def test_plain_one():
    assert True
"""

ENV_TESTS = """\
import os


def test_child_environment_is_minimal():
    assert "SECRET_TOKEN" not in os.environ
    assert os.environ.get("TL_ENV") == "dev"
"""

REPORT_NAME = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}\.txt$")


def _small_repo(tmp_path: Path) -> DevHarness:
    """A repository with AGENTS.md, a justfile, dev/ and a few test files, and a harness over it."""
    repo = tmp_path / "repo"
    (repo / "dev").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "AGENTS.md").write_text("# small repository for run_tests\n", encoding="utf-8")
    (repo / "justfile").write_text("# small repository\n", encoding="utf-8")
    (repo / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (repo / "tests" / "test_ok.py").write_text(OK_TESTS, encoding="utf-8")
    (repo / "tests" / "test_fail.py").write_text(FAIL_TESTS, encoding="utf-8")
    (repo / "tests" / "test_slow.py").write_text(SLOW_TESTS, encoding="utf-8")
    (repo / "tests" / "test_markers.py").write_text(MARKER_TESTS, encoding="utf-8")
    (repo / "tests" / "test_env.py").write_text(ENV_TESTS, encoding="utf-8")
    return DevHarness.build(tmp_path, repo_root=repo)


def _with_environ(env: DevHarness, environ: dict[str, str]) -> DevHarness:
    """The same harness with the server's environment replaced (the database stays the same)."""
    ctx = dataclasses.replace(env.ctx, environ=environ)
    return DevHarness(ctx, build_dev_server(ctx), env.db)


def _refusals(env: DevHarness) -> list[dict]:
    return [line for line in env.audit_lines() if line["tool"] == "run_tests"]


def _live_processes_running(needle: str) -> list[str]:
    """Command lines of live processes that mention ``needle`` (Linux only)."""
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    found: list[str] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        cmdline = raw.replace(b"\x00", b" ").decode(errors="replace")
        if needle in cmdline:
            found.append(cmdline)
    return found


# --- passing, failing and filtered runs -----------------------------------------------------------


def test_passing_file_returns_counts_and_stores_report(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    out = env.structured("run_tests", paths=["tests/test_ok.py"])
    assert out["exit_code"] == 0
    assert out["timed_out"] is False
    assert out["passed"] == 2
    assert out["failed"] in (None, 0)
    assert out["errors"] is None
    assert out["summary"].startswith("2 passed")

    report = env.ctx.reports_dir / out["report"]
    assert REPORT_NAME.match(out["report"])
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert text.startswith("python -m pytest ")
    assert "tests/test_ok.py" in text.splitlines()[0]
    assert "exit code: 0" in text.splitlines()[1]


def test_failing_test_is_reported_with_its_name(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    out = env.structured("run_tests", paths=["tests/test_fail.py"])
    assert out["exit_code"] == 1
    assert out["failed"] == 1
    assert out["passed"] is None
    assert "test_fail_one" in out["output_tail"]
    assert "exit code: 1" in (env.ctx.reports_dir / out["report"]).read_text(encoding="utf-8")


def test_keyword_deselects_slow_test(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    out = env.structured(
        "run_tests",
        paths=["tests/test_ok.py", "tests/test_slow.py"],
        keyword="not slow",
    )
    assert out["exit_code"] == 0
    assert out["passed"] == 2
    assert "deselected" in out["summary"]
    assert out["duration_s"] < 10  # test_slow_one (30 s) was never run


def test_marker_runs_only_marked_tests(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    out = env.structured("run_tests", paths=["tests/test_markers.py"], marker="parity")
    assert out["exit_code"] == 0
    assert out["passed"] == 1
    assert "deselected" in out["summary"]


def test_child_sees_only_the_allow_listed_environment(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    secret_env = _with_environ(
        env, {"PATH": os.environ.get("PATH", ""), "SECRET_TOKEN": "not-for-the-child"}
    )
    out = secret_env.structured("run_tests", paths=["tests/test_env.py"])
    assert out["exit_code"] == 0, out["output_tail"]
    assert out["passed"] == 1


# --- timeout and process group --------------------------------------------------------------------


def test_timeout_kills_the_run_and_the_server_keeps_working(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    start = time.monotonic()
    out = env.structured("run_tests", paths=["tests/test_slow.py"], timeout_s=1)
    assert out["timed_out"] is True
    assert out["exit_code"] == -1
    assert time.monotonic() - start < 10
    assert _live_processes_running("tests/test_slow.py") == []

    again = env.structured("run_tests", paths=["tests/test_ok.py"])
    assert again["exit_code"] == 0


# --- refusals -------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["../etc", "/etc/passwd", "--co"])
def test_path_outside_the_allow_list_is_refused(tmp_path: Path, path: str) -> None:
    env = _small_repo(tmp_path)
    with pytest.raises(ToolError, match="refused"):
        env.call("run_tests", paths=[path])
    assert _refusals(env)[-1]["outcome"] == "refused"


def test_marker_outside_the_allow_list_is_rejected(tmp_path: Path) -> None:
    # The marker is a Literal in the tool's schema, so the SDK rejects "slow" before the body runs:
    # the call still fails with a ToolError, but there is no guard line in the audit file.
    env = _small_repo(tmp_path)
    before = len(_refusals(env))
    with pytest.raises(ToolError):
        env.call("run_tests", marker="slow")
    assert len(_refusals(env)) == before


def test_keyword_with_shell_characters_is_refused(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    with pytest.raises(ToolError, match="refused"):
        env.call("run_tests", paths=["tests/test_ok.py"], keyword="a; rm -rf /")
    assert _refusals(env)[-1]["outcome"] == "refused"


def test_no_filter_is_refused(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    with pytest.raises(ToolError, match="refused"):
        env.call("run_tests")
    assert _refusals(env)[-1]["outcome"] == "refused"


def test_more_than_twenty_paths_is_rejected_by_the_schema(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    with pytest.raises(ToolError):
        env.call("run_tests", paths=["tests/test_ok.py"] * 21)


def test_postgres_url_outside_the_dev_rule_refuses_the_run(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    outside = _with_environ(
        env,
        {
            "PATH": os.environ.get("PATH", ""),
            "TL_PG_URL": "postgresql://u:p@db.example.com/prod",
        },
    )
    with pytest.raises(ToolError, match="refused"):
        outside.call("run_tests", paths=["tests/test_markers.py"], marker="parity")
    assert _refusals(outside)[-1]["outcome"] == "refused"
    audit_text = (tmp_path / "audit.jsonl").read_text(encoding="ascii")
    assert "db.example.com" not in audit_text  # the URL is never written to the audit file
    assert "u:p" not in audit_text


# --- report files ---------------------------------------------------------------------------------


def test_reports_are_pruned_to_fifty_and_other_files_are_untouched(tmp_path: Path) -> None:
    env = _small_repo(tmp_path)
    reports = env.ctx.reports_dir
    reports.mkdir(parents=True)
    for i in range(55):
        (reports / f"20200101T0000{i:02d}Z-{i:06x}.txt").write_text("old", encoding="utf-8")
    (reports / "notes.txt").write_text("keep me", encoding="utf-8")

    out = env.structured("run_tests", paths=["tests/test_ok.py"])

    names = sorted(p.name for p in reports.iterdir())
    matching = [n for n in names if REPORT_NAME.match(n)]
    assert len(matching) == 50
    assert out["report"] in matching
    assert "notes.txt" in names
    assert (reports / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert "20200101T000005Z-000005.txt" not in names  # the six oldest went
    assert "20200101T000006Z-000006.txt" in names
