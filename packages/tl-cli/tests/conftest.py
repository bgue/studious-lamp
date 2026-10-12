"""tl-cli test configuration: sibling helpers on `sys.path`, and a signed-in user on Postgres.

pytest runs in importlib mode (root pyproject), so sibling helpers are not importable by default
(L-P0-I2-B1). Do not add ``__init__.py`` here.

**Postgres needs a session (ADR-0009 section 7).** A ledger file in a dev setup lets a command
act as ``user:dev`` without signing in; a ``postgresql://`` target never does. The command-group
tests were written for the file rule and run on both databases (``--adapters sqlite,postgres``),
so on Postgres the fixture below signs a test account called ``dev`` (role admin, so its actor is
``user:dev``, the actor those tests expect) in to the ledger the first time a command runs against
it, exactly as ``tl login`` would (a command that names ``--actor user:<name>`` runs as that
person: an admin account made on demand and signed in for that command; the next one is ``dev``
again), through the session file ``TL_SESSION_FILE`` names. A command that names
``--actor user:<name>`` runs as that person (an admin account made on demand, and signed in for
that command; the next command is ``dev`` again). A test module
that is about signing in sets ``AUTO_SIGN_IN = False`` and does it itself. SQLite is untouched.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

TEST_USER = "dev"
TEST_PASSWORD = "correct horse battery"
# commands that create, inspect or end a sign-in themselves: never signed in on their behalf
_OWN_SESSION = {"init", "login", "logout", "whoami", "admin"}


def sign_in_test_user(env: dict[str, str], username: str = TEST_USER) -> None:
    """Make sure ``env``'s Postgres ledger has the account ``username`` and that its session is the
    one in force (an admin account, so any command may be run as it)."""
    import os
    from unittest import mock

    from tl_adapters.backend import BackendUnavailableError, ledger_exists
    from tl_adapters.db import as_target, is_postgres
    from tl_cli import session
    from tl_core.auth import accounts, queries, sessions
    from tl_core.auth.password import prepare_password

    target = as_target(env["TL_DB"])
    if not is_postgres(target):
        return
    try:
        if not ledger_exists(target):
            return
    except BackendUnavailableError:
        return  # a server that cannot be reached: the test is about that, let the command say so
    with mock.patch.dict(os.environ, env):
        current = session.current_principal(target)
        if current is not None and current.actor == f"user:{username}":
            return
        backend = session.open_backend(target)
        with backend() as uow:
            if queries.find_account(uow.conn(), username=username) is None:
                accounts.create_account(
                    uow,
                    username=username,
                    display_name=username,
                    kind="person",
                    roles=["admin"],
                    password=prepare_password(TEST_PASSWORD, username=username),
                    by="user:dev",
                )
        principal, token = sessions.sign_in(backend, username=username, password=TEST_PASSWORD)
        session.save(
            session.StoredSession(
                target=session.db_target(target),
                username=username,
                actor=principal.actor,
                expires_at=session.expires_at_from(sessions.SESSION_TTL),
                token=token,
            )
        )


def named_user(args: Any) -> str:
    """The person ``--actor user:<name>`` names in ``args``, else the default test user."""
    items = [str(a) for a in args] if isinstance(args, list | tuple) else []  # pyright: ignore
    for index, item in enumerate(items):
        value = items[index + 1] if item == "--actor" and index + 1 < len(items) else ""
        if item.startswith("--actor="):
            value = item.partition("=")[2]
        if value.startswith("user:") and len(value) > 5:
            return value[5:]
    return TEST_USER


@pytest.fixture(autouse=True)
def _signed_in_on_postgres(request: pytest.FixtureRequest) -> Iterator[None]:
    if not getattr(request.module, "AUTO_SIGN_IN", True):
        yield
        return
    real = CliRunner.invoke

    def invoke(self: CliRunner, cli: Any, args: Any = None, *rest: Any, **kwargs: Any) -> Any:
        env = kwargs.get("env")
        first = args[0] if isinstance(args, list) and args else None  # pyright: ignore[reportUnknownVariableType]
        if isinstance(env, dict) and "TL_DB" in env and first not in _OWN_SESSION:
            sign_in_test_user(dict(env), named_user(args))  # pyright: ignore
        return real(self, cli, args, *rest, **kwargs)

    CliRunner.invoke = invoke  # type: ignore[method-assign]
    try:
        yield
    finally:
        CliRunner.invoke = real  # type: ignore[method-assign]
