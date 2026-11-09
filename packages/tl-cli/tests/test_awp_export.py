"""`tl awp export progress` (P2-I5 S3), on a copy of the S4 seed ledger."""

from __future__ import annotations

import csv
import io
import os
import stat
from pathlib import Path

import pytest
from test_cli_awp import Cli, seed_copy

HEADER = ["period", "scope", "cost_code", "earned_hours", "budget_hours", "earned_pct", "as_of_seq"]


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


def rows_of(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def test_export_progress_prints_the_header_and_one_row_per_cost_code_line(cli: Cli) -> None:
    result = cli.project("export", "progress", "--period", "2026-W45")
    assert result.exit_code == 0, result.output
    rows = rows_of(result.stdout)
    assert rows[0] == HEADER
    assert result.stdout.splitlines()[0].startswith('"period"')
    assert rows[-1][2] == "Unallocated"
    assert all(r[0] == "2026-W45" and r[1] == "project:P123" for r in rows[1:])
    head = cli.scalar("SELECT COALESCE(MAX(seq), 0) FROM events")
    assert {r[6] for r in rows[1:]} == {str(head)}


def test_out_writes_a_private_file_and_prints_the_row_count(cli: Cli, tmp_path: Path) -> None:
    target = tmp_path / "progress.csv"
    result = cli.project("export", "progress", "--period", "2026-W45", "--out", str(target))
    assert result.exit_code == 0, result.output
    data = target.read_text(encoding="utf-8")
    rows = rows_of(data)
    assert result.stdout == f"wrote {target} rows={len(rows) - 1}\n"
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    shown = cli.project("export", "progress", "--period", "2026-W45")
    assert shown.stdout == data


def test_out_keeps_the_mode_of_a_file_it_replaces(cli: Cli, tmp_path: Path) -> None:
    target = tmp_path / "progress.csv"
    target.write_text("old")
    target.chmod(0o644)
    cli.project("export", "progress", "--period", "2026-W45", "--out", str(target))
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert target.read_text().startswith('"period"')


@pytest.mark.parametrize("period", ["2026-W54", "2026-45", "week 45"])
def test_a_bad_period_exits_2_with_the_fixed_text(cli: Cli, period: str) -> None:
    result = cli.project("export", "progress", "--period", period)
    assert result.exit_code == 2
    assert result.stderr.splitlines() == ["error: period: expected YYYY-Www"]
    assert result.stdout == ""


def test_the_project_is_required_like_the_other_awp_reports(cli: Cli) -> None:
    result = cli.run("export", "progress", "--period", "2026-W45")
    assert result.exit_code == 2
    assert "--project" in result.output


def test_the_export_writes_nothing(cli: Cli) -> None:
    before = cli.scalar("SELECT COUNT(*) FROM events")
    cli.project("export", "progress", "--period", "2026-W45")
    assert cli.scalar("SELECT COUNT(*) FROM events") == before
