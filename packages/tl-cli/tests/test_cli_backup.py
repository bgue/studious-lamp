"""`tl backup sqlite` (P0-I7-T02)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    values = {"TL_DB": str(tmp_path / "tl.db"), "TL_ENV": "dev"}
    result = runner.invoke(app, ["init"], env=values)
    assert result.exit_code == 0, result.output
    return values


def test_backup_sqlite_prints_one_summary_line_and_writes_the_snapshot(
    env: dict[str, str], tmp_path: Path
) -> None:
    snap = tmp_path / "snaps" / "one.db"
    result = runner.invoke(app, ["backup", "sqlite", "--to", str(snap)], env=env)
    assert result.exit_code == 0, result.output
    assert result.exception is None
    digest = hashlib.sha256(snap.read_bytes()).hexdigest()
    assert result.stdout.splitlines() == [
        f"backed up 0 events from {env['TL_DB']} to {snap} ({snap.stat().st_size} bytes, "
        f"sha256 {digest})"
    ]


def test_the_root_db_option_chooses_the_source(env: dict[str, str], tmp_path: Path) -> None:
    other = tmp_path / "other.db"
    assert runner.invoke(app, ["--db", str(other), "init"], env=env).exit_code == 0
    snap = tmp_path / "other-snap.db"
    result = runner.invoke(app, ["--db", str(other), "backup", "sqlite", "--to", str(snap)])
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert f"from {other} to {snap}" in result.stdout


def test_an_existing_destination_exits_1_with_an_error_on_stderr(
    env: dict[str, str], tmp_path: Path
) -> None:
    snap = tmp_path / "taken.db"
    snap.write_bytes(b"keep me")
    result = runner.invoke(app, ["backup", "sqlite", "--to", str(snap)], env=env)
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)  # a clean exit, not a crash
    assert re.search(r"^error: destination exists: .*taken\.db$", result.stderr, re.MULTILINE)
    assert result.stdout == ""
    assert snap.read_bytes() == b"keep me"


def test_a_missing_ledger_exits_1_without_creating_it(tmp_path: Path) -> None:
    missing = tmp_path / "none.db"
    result = runner.invoke(
        app, ["backup", "sqlite", "--to", str(tmp_path / "s.db")], env={"TL_DB": str(missing)}
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error: source database not found" in result.stderr
    assert not missing.exists() and not (tmp_path / "s.db").exists()


def test_to_is_required(env: dict[str, str]) -> None:
    result = runner.invoke(app, ["backup", "sqlite"], env=env)
    assert result.exit_code == 2
