"""``run_tests``: one filtered pytest run in a child process (brief 25.3, FANOUT D12).

The filters come from fixed allow-lists (:func:`tl_mcp.dev.guard.select_pytest_args`); the child
gets no shell and a minimal environment (:meth:`DevContext.child_env`). The full output is kept as
a report file below ``dev/data/test-reports/``; the answer carries the counts and the tail.
"""

from __future__ import annotations

import os
import re
import secrets
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.guard import resolve_postgres, select_pytest_args
from tl_mcp.dev.runtime import DevContext, guarded

WRITES_REPORT = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

MAX_REPORT_BYTES = 1024 * 1024
"""A report keeps at most this many bytes of output (the end of the output is kept)."""
MAX_REPORTS = 50
"""Report files kept in ``dev/data/test-reports``; the oldest go first."""
OUTPUT_TAIL_CHARS = 6000
SUMMARY_CHARS = 300
_REPORT_NAME = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}\.txt$")
_PASSED = re.compile(r"(\d+) passed")
_FAILED = re.compile(r"(\d+) failed")
_ERRORS = re.compile(r"(\d+) error")
_POSTGRES_MARKERS = frozenset({"parity", "requires_postgres"})


class RunTestsOutput(BaseModel):
    """The answer of ``run_tests``."""

    exit_code: int  # -1 when timed out
    timed_out: bool
    passed: int | None
    failed: int | None
    errors: int | None
    summary: str  # pytest's last non-empty line, at most 300 characters
    output_tail: str  # the last 6000 characters of the output
    report: str  # the report file name only (below dev/data/test-reports)
    duration_s: float


def _count(pattern: re.Pattern[str], summary: str) -> int | None:
    match = pattern.search(summary)
    return int(match.group(1)) if match else None


def _summary_line(output: str) -> str:
    """pytest's last non-empty line, whole (the counts are read from it)."""
    for line in reversed(output.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _capped(output: str) -> str:
    raw = output.encode("utf-8", errors="replace")
    if len(raw) <= MAX_REPORT_BYTES:
        return output
    return raw[-MAX_REPORT_BYTES:].decode("utf-8", errors="ignore")


def _write_report(ctx: DevContext, args: list[str], exit_code: int, output: str) -> str:
    """Write the report file and prune the directory; returns the file name."""
    reports = ctx.reports_dir
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"{stamp}-{secrets.token_hex(3)}.txt"
    command = " ".join(["python", "-m", "pytest", *args])
    body = f"{command}\nexit code: {exit_code}\n\n{_capped(output)}"
    (reports / name).write_text(body, encoding="utf-8")
    kept = sorted(p.name for p in reports.iterdir() if _REPORT_NAME.match(p.name))
    for old in kept[: max(0, len(kept) - MAX_REPORTS)]:
        (reports / old).unlink()
    return name


def _run(args: list[str], env: dict[str, str], cwd: Path, timeout_s: int) -> tuple[int, bool, str]:
    """Run pytest in its own session; on timeout kill the whole process group, keep the output."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "pytest", *args],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate()
        return -1, True, output or ""
    return proc.returncode, False, output or ""


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=WRITES_REPORT)
    def run_tests(
        paths: Annotated[
            list[Annotated[str, Field(max_length=200)]],
            Field(
                max_length=20,
                description=(
                    "Test files or directories under packages/<package>/tests or tests, relative "
                    "to the repository, optionally ending in ::test_name."
                ),
            ),
        ] = Field(default_factory=list),  # noqa: B008 (pydantic default_factory, not a call)
        marker: Annotated[
            Literal["parity", "requires_postgres"] | None,
            Field(description="Run only tests with this pytest marker."),
        ] = None,
        keyword: Annotated[
            str | None,
            Field(
                max_length=200,
                description="pytest -k expression: letters, digits, _, spaces, parentheses only.",
            ),
        ] = None,
        adapters: Annotated[
            Literal["sqlite", "postgres", "sqlite,postgres"] | None,
            Field(description="Adapters the conftest should run (--adapters)."),
        ] = None,
        timeout_s: Annotated[
            int, Field(ge=1, le=900, description="Seconds before the run is killed.")
        ] = 300,
    ) -> RunTestsOutput:
        """Run one filtered pytest run in the repository and store its full output as a report.

        At least one path, marker or keyword is required; the whole suite is `just test`.
        Allowed markers: parity, requires_postgres. Allowed adapters: sqlite, postgres,
        sqlite,postgres (postgres or a parity/requires_postgres marker sets TL_REQUIRE_POSTGRES=1).
        Limits: 20 paths of at most 200 characters, keyword at most 200 characters, timeout 1 to 900
        seconds (default 300), 1 MiB of output kept per report, 50 reports kept. The answer holds
        the counts, the summary line and the last 6000 characters of output; read the report file
        below dev/data/test-reports for the rest.

        Example: paths=["tests/test_ok.py"], keyword="not slow", timeout_s=120.
        """
        detail = {
            "paths": paths,
            "marker": marker,
            "keyword": keyword,
            "adapters": adapters,
            "timeout_s": timeout_s,
        }
        with guarded(ctx, "run_tests", detail):
            args = select_pytest_args(
                repo_root=ctx.repo_root,
                paths=paths,
                marker=marker,
                keyword=keyword,
                adapters=adapters,
            )
            if not paths and marker is None and keyword is None:
                raise DevGuardError(
                    "name at least one path, marker or keyword; the whole suite is `just test`"
                )
            extra: dict[str, str] = {}
            if (adapters is not None and "postgres" in adapters) or marker in _POSTGRES_MARKERS:
                extra["TL_REQUIRE_POSTGRES"] = "1"
            env = ctx.child_env(extra)
            if "TL_PG_URL" in env:
                # a database outside the dev rule refuses the whole run
                resolve_postgres(env["TL_PG_URL"])
            started = time.monotonic()
            exit_code, timed_out, output = _run(args, env, ctx.repo_root, timeout_s)
            duration = time.monotonic() - started
            report = _write_report(ctx, args, exit_code, output)
            summary_line = _summary_line(output)
            return RunTestsOutput(
                exit_code=exit_code,
                timed_out=timed_out,
                passed=_count(_PASSED, summary_line),
                failed=_count(_FAILED, summary_line),
                errors=_count(_ERRORS, summary_line),
                summary=summary_line[:SUMMARY_CHARS],
                output_tail=output[-OUTPUT_TAIL_CHARS:],
                report=report,
                duration_s=round(duration, 3),
            )
