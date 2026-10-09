"""End-to-end tests of the `tl` command against a temporary SQLite ledger (no network)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
_HASH = re.compile(r"\b[0-9a-f]{64}\b")


def _run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def _lines(result: RunResult) -> list[str]:
    return result.stdout.splitlines()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A TL_DB pointing at a fresh ledger under tmp_path, initialised once."""
    env = {"TL_DB": str(tmp_path / "tl.db")}
    result = _run(env, "init")
    assert result.exit_code == 0, result.output
    return env


def _create(env: dict[str, str], key: str = "DEMO-0001", title: str = "First") -> RunResult:
    return _run(env, "record", "create", "--project", "P123", "--key", key, "--title", title)


def test_init_creates_file_and_second_init_succeeds(tmp_path: Path) -> None:
    env = {"TL_DB": str(tmp_path / "data" / "tl.db")}
    first = _run(env, "init")
    assert first.exit_code == 0, first.output
    assert "initialised" in first.stdout
    assert (tmp_path / "data" / "tl.db").is_file()

    second = _run(env, "init")
    assert second.exit_code == 0, second.output
    assert "initialised" in second.stdout


def test_record_create_prints_stream_key_and_version(env: dict[str, str]) -> None:
    result = _create(env)

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert lines[0].startswith("created ")
    assert "key DEMO-0001" in lines
    assert "version 1" in lines


def test_record_show_prints_current_state(env: dict[str, str]) -> None:
    _create(env)

    result = _run(env, "record", "show", "--project", "P123", "DEMO-0001")

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert "title: First" in lines
    assert "version: 1" in lines
    assert "voided: false" in lines
    assert "status: -" in lines
    assert "psets: {}" in lines


def test_events_tail_last_event_is_record_created(env: dict[str, str]) -> None:
    _create(env)

    result = _run(env, "events", "tail", "--project", "P123", "-n", "1")

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert len(lines) == 1
    assert "Record.Created" in lines[0]
    assert _HASH.search(lines[0]) is not None


def test_record_void_then_show_reports_voided(env: dict[str, str]) -> None:
    _create(env)

    voided = _run(env, "record", "void", "--project", "P123", "DEMO-0001", "--reason", "test")
    assert voided.exit_code == 0, voided.output

    shown = _run(env, "record", "show", "--project", "P123", "DEMO-0001")
    assert shown.exit_code == 0, shown.output
    lines = _lines(shown)
    assert "voided: true" in lines
    assert "version: 2" in lines


def test_projections_rebuild_replays_and_show_is_unchanged(env: dict[str, str]) -> None:
    _create(env)
    _run(env, "record", "void", "--project", "P123", "DEMO-0001", "--reason", "test")
    before = _run(env, "record", "show", "--project", "P123", "DEMO-0001")
    assert before.exit_code == 0, before.output

    rebuilt = _run(env, "projections", "rebuild")
    assert rebuilt.exit_code == 0, rebuilt.output
    assert "replayed 2 events" in _lines(rebuilt)

    after = _run(env, "record", "show", "--project", "P123", "DEMO-0001")
    assert after.exit_code == 0, after.output
    assert after.stdout == before.stdout


def test_create_same_key_twice_fails(env: dict[str, str]) -> None:
    assert _create(env).exit_code == 0

    result = _create(env)

    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_show_unknown_key_fails(env: dict[str, str]) -> None:
    result = _run(env, "record", "show", "--project", "P123", "NOPE-0001")

    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_void_unknown_key_fails(env: dict[str, str]) -> None:
    result = _run(env, "record", "void", "--project", "P123", "NOPE-0001", "--reason", "test")

    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_void_twice_fails(env: dict[str, str]) -> None:
    _create(env)
    assert (
        _run(env, "record", "void", "--project", "P123", "DEMO-0001", "--reason", "test").exit_code
        == 0
    )

    result = _run(env, "record", "void", "--project", "P123", "DEMO-0001", "--reason", "again")

    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_create_without_key_is_a_usage_error(env: dict[str, str]) -> None:
    result = _run(env, "record", "create", "--project", "P123", "--title", "First")

    assert result.exit_code != 0
    assert "--key" in result.output
