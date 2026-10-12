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

AUTO_SIGN_IN = False  # these tests are about who is signed in (see conftest.py)


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


UNREACHABLE = "postgresql://someone:hunter2@127.0.0.1:1/tl?sslmode=disable"


def clean_exit(result: RunResult, code: int) -> None:
    assert result.exit_code == code, result.output
    assert isinstance(result.exception, SystemExit)  # a clean exit, not a traceback
    assert "Traceback" not in result.output
    assert "hunter2" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["record", "show", "--project", "P1", "REC-1"],
        ["events", "tail", "--project", "P1"],
        ["projections", "rebuild"],
        ["config", "ls"],
        ["ledger", "verify"],
    ],
)
def test_an_unreachable_server_is_one_error_line_in_every_command(args: list[str]) -> None:
    result = run(UNREACHABLE, *args)
    clean_exit(result, 1)
    assert "cannot reach the database" in result.output
    assert "127.0.0.1" in result.output


@pytest.mark.parametrize(
    "value",
    [
        "mysql://u:SeCrEt@h/d",
        "postgresql:///x",
        "postgresql://u:SeCr@Et@localhost/db",
    ],
)
def test_a_value_that_is_not_a_database_target_is_refused_and_creates_nothing(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run(value, "init")
    assert result.exit_code == 2, result.output
    assert "error:" in result.output
    assert "SeCr" not in result.output and "Et@" not in result.output
    assert list(tmp_path.iterdir()) == []


@pytest.mark.requires_postgres
def test_a_wrong_password_and_a_missing_database_are_named_without_the_secret(
    pg_db: str,
) -> None:
    from sqlalchemy.engine import make_url

    parsed = make_url(pg_db.replace("postgresql://", "postgresql+pg8000://", 1))
    wrong = parsed.set(password="wr0ng-s3cret").render_as_string(hide_password=False)
    result = run(
        wrong.replace("postgresql+pg8000://", "postgresql://", 1),
        "record",
        "show",
        "--project",
        "P1",
        "K",
    )
    assert result.exit_code == 1, result.output
    assert "password authentication failed" in result.output
    assert "wr0ng-s3cret" not in result.output
    missing = parsed.set(database="tl_p1i0b_no_such_database").render_as_string(hide_password=False)
    result = run(missing.replace("postgresql+pg8000://", "postgresql://", 1), "ledger", "verify")
    assert result.exit_code == 1, result.output
    assert "does not exist" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["record", "show", "--project", "P1", "REC-1"],
        ["events", "tail", "--project", "P1"],
        ["projections", "rebuild"],
        ["init"],
    ],
)
def test_an_unsupported_sslmode_is_one_error_line_before_any_command_runs(
    args: list[str],
) -> None:
    result = run("postgresql://someone:hunter2@127.0.0.1:1/tl?sslmode=bogus", *args)
    assert result.exit_code == 2, result.output
    assert "unsupported sslmode" in result.output
    assert "Traceback" not in result.output
    assert "hunter2" not in result.output


@pytest.mark.parametrize(
    "query", ["connect_timeout=5", "host=evil.example", "port=5999", "password=SeCrEt", "user=x"]
)
@pytest.mark.parametrize("args", [["init"], ["record", "show", "--project", "P1", "K"]])
def test_a_query_parameter_the_adapter_does_not_accept_is_one_error_line_not_a_type_error(
    query: str, args: list[str]
) -> None:
    result = run(f"postgresql://someone:SeCrEt@127.0.0.1:1/tl?sslmode=disable&{query}", *args)
    assert result.exit_code == 2, result.output
    assert "query parameter" in result.output and "allowed: sslmode, options" in result.output
    assert "TypeError" not in result.output and "Traceback" not in result.output
    assert "SeCrEt" not in result.output and "127.0.0.1" not in result.output
