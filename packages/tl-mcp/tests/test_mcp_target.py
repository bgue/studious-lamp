"""The MCP server's entry point takes a SQLite file or a Postgres URL (P1-I0-S35).

Runs on the adapters named by ``--adapters``. The server itself is not started: the entry point
refuses before it listens, and every refusal here proves the ledger was reached through
``open_backend`` and that no message repeats the URL's password.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tl_adapters.db import DbTarget, create_schema, display_target, is_postgres
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mcp.main import main

GOOD = "correct horse battery"


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    found = new_db()
    create_schema(found)
    return found


def session_token(target: DbTarget) -> str:
    """A person's session token (not an agent token), made through the account services."""
    from tl_adapters.backend import open_backend

    with open_backend(target) as backend:
        with backend() as uow:
            accounts.create_account(
                uow,
                username="amy",
                display_name="Amy",
                kind="person",
                roles=["user"],
                password=prepare_password(GOOD, username="amy"),
                by="user:root",
            )
        _principal, token = sessions.sign_in(backend, username="amy", password=GOOD)
    return token


def test_a_ledger_is_found_through_the_target_and_a_session_token_is_refused(
    target: DbTarget, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    token = session_token(target)
    monkeypatch.setenv("TL_AGENT_TOKEN", token)
    assert main(["--db", str(target)]) == 2
    err = capsys.readouterr().err
    assert "must be an agent token" in err and token not in err
    monkeypatch.setenv("TL_DB", str(target))  # the variable works as well as the option
    assert main([]) == 2
    assert "must be an agent token" in capsys.readouterr().err


def test_a_target_without_a_ledger_says_to_run_init_without_the_password(
    new_db: Callable[[], DbTarget],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = new_db()  # no tables yet
    monkeypatch.setenv("TL_AGENT_TOKEN", "tla_" + "a" * 43)
    assert main(["--db", str(empty)]) == 2
    err = capsys.readouterr().err
    assert "tl init" in err and display_target(empty) in err
    if is_postgres(empty):
        assert "postgres:postgres@" not in err


def test_an_unreachable_server_and_a_bad_target_are_one_error_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_AGENT_TOKEN", "tla_" + "a" * 43)
    assert main(["--db", "postgresql://u:hunter2@127.0.0.1:1/tl?sslmode=disable"]) == 2
    err = capsys.readouterr().err
    assert "cannot reach the database" in err and "hunter2" not in err
    monkeypatch.setenv("TL_DB", "mysql://u:hunter2@h/d")
    assert main([]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "hunter2" not in err
    with pytest.raises(SystemExit) as raised:
        main(["--db", "mysql://u:hunter2@h/d"])
    assert raised.value.code == 2
    assert "hunter2" not in capsys.readouterr().err
