"""The root `--db` / `TL_DB` takes a SQLite path or a Postgres URL (P1-I0-S32).

Runs on the adapters named by ``--adapters``. Only the commands that live in ``tl_cli/main.py`` and
the root callback appear here (`init`, `projections rebuild`, `serve` and a read of the ledger);
each group of commands has its own parity test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.backend import ledger_exists
from tl_adapters.db import DbTarget, display_target, is_postgres
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


def run(target: DbTarget | str, *args: str) -> RunResult:
    return runner.invoke(app, list(args), env={"TL_DB": str(target), "TL_ENV": "dev"})


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    return new_db()


def test_init_creates_the_ledger_and_a_second_init_is_harmless(target: DbTarget) -> None:
    assert ledger_exists(target) is False
    for _ in range(2):
        result = run(target, "init")
        assert result.exit_code == 0, result.output
        assert result.exception is None
        assert f"initialised {display_target(target)}" in result.stdout
    assert ledger_exists(target) is True


def test_init_never_prints_the_password(target: DbTarget) -> None:
    result = run(target, "init")
    assert result.exit_code == 0, result.output
    if is_postgres(target):
        assert "postgres:postgres@" not in result.output
        assert "***" in result.stdout


def test_projections_rebuild_replays_the_ledger(target: DbTarget) -> None:
    assert run(target, "init").exit_code == 0
    result = run(target, "projections", "rebuild")
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert "replayed 0 events" in result.stdout


def test_the_ledger_verifies_through_the_root_target(target: DbTarget) -> None:
    assert run(target, "init").exit_code == 0
    result = run(target, "ledger", "verify")
    assert result.exit_code == 0, result.output
    assert "hash chains intact" in result.stdout


def test_a_ledger_that_was_never_created_is_not_created_by_serve(target: DbTarget) -> None:
    result = run(target, "serve", "--port", "0")
    assert result.exit_code == 2
    assert "tl init" in result.output
    assert "postgres:postgres@" not in result.output
    if not is_postgres(target):
        assert not Path(target).exists()


def test_init_names_an_unreachable_server_and_hides_the_password() -> None:
    result = run("postgresql://someone:hunter2@127.0.0.1:1/tl?sslmode=disable", "init")
    assert result.exit_code == 1
    assert "cannot reach the database" in result.output
    assert "hunter2" not in result.output
