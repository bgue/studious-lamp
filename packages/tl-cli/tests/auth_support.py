"""Helpers shared by the CLI account tests (login, admin user and token, the TUI-free parts).

Written by the supervisor (P1-I0-S3); provided tests import it as ``from auth_support import ...``
(this directory is on ``sys.path`` through ``conftest.py``).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from tl_cli import session
from tl_cli.main import app
from tl_core.auth import sessions
from tl_core.services.errors import ServiceError
from typer.testing import CliRunner
from typer.testing import Result as RunResult

GOOD = "correct horse battery"
OTHER = "another long passphrase"
WRONG = "this is not the password"

runner = CliRunner()


def new_ledger(tmp_path: Path, name: str = "tl.db", tl_env: str = "dev") -> dict[str, str]:
    """An initialised ledger and the environment that points the CLI at it."""
    env = {"TL_DB": str(tmp_path / name), "TL_ENV": tl_env}
    result = runner.invoke(app, ["init"], env=env)
    assert result.exit_code == 0, result.output
    return env


def run(env: dict[str, str], *args: str, stdin: str | None = None) -> RunResult:
    """Run ``tl <args>`` with ``env`` and optional standard input."""
    return runner.invoke(app, list(args), env=env, input=stdin)


def bootstrap(env: dict[str, str], name: str = "root", password: str = GOOD) -> RunResult:
    """Create (or reset) an admin through the real recovery command."""
    return run(env, "admin", "bootstrap", "--username", name, "--password-stdin", stdin=password)


def login(env: dict[str, str], name: str = "root", password: str = GOOD) -> RunResult:
    """``tl login NAME --password-stdin``."""
    return run(env, "login", name, "--password-stdin", stdin=password)


def rows(env: dict[str, str], sql: str, *params: Any) -> list[tuple[Any, ...]]:
    """Read rows straight from the ledger file (tests only)."""
    with sqlite3.connect(env["TL_DB"]) as conn:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]


def live_sessions(env: dict[str, str]) -> int:
    """How many sessions the ledger holds."""
    return int(rows(env, "SELECT COUNT(*) FROM auth_session")[0][0])


def last_actor(env: dict[str, str]) -> str:
    """The actor of the newest event that is not an account event."""
    found = rows(
        env,
        "SELECT actor FROM events WHERE event_type NOT LIKE 'Account.%' "
        "AND event_type NOT LIKE 'AgentToken.%' ORDER BY seq DESC",
    )
    return str(found[0][0])


def separate_session(env: dict[str, str], tmp_path: Path, name: str) -> dict[str, str]:
    """``env`` with its own session file, so two people can be signed in to one ledger at once."""
    return env | {"TL_SESSION_FILE": str(tmp_path / f"session-{name}.json")}


@contextmanager
def _environ(env: dict[str, str]) -> Iterator[None]:
    with mock.patch.dict(os.environ, env):
        yield


def sign_in(env: dict[str, str], name: str = "root", password: str = GOOD) -> None:
    """Sign in as `tl login` does, without the command, and store the session as it does.

    The session goes into the file ``env`` names (``TL_SESSION_FILE``). A failed sign-in raises
    the service error (``InvalidCredentialsError``, ``AccountLockedError``, ...).
    """
    db = Path(env["TL_DB"])
    with _environ(env):
        backend = session.open_backend(db)
        principal, token = sessions.sign_in(backend, username=name, password=password)
        session.save(
            session.StoredSession(
                target=session.db_target(db),
                username=name,
                actor=principal.actor,
                expires_at=session.expires_at_from(sessions.SESSION_TTL),
                token=token,
            )
        )


def failed_sign_ins(env: dict[str, str], name: str, times: int = 1) -> None:
    """Fail ``times`` sign-ins for ``name`` with a wrong password (stores nothing)."""
    backend = session.open_backend(Path(env["TL_DB"]))
    for _ in range(times):
        with pytest.raises(ServiceError):
            sessions.sign_in(backend, username=name, password=WRONG)


def signed_in_actor(env: dict[str, str]) -> str | None:
    """The actor ``env``'s session names if the ledger still honours it, else None."""
    with _environ(env):
        principal = session.current_principal(Path(env["TL_DB"]))
    return None if principal is None else principal.actor
