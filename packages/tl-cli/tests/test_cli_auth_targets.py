"""Sign-in, the default actor and the demo account on a SQLite file and on Postgres (P1-I0-S35).

Workstream A's rules (ADR-0009 sections 4 and 7) hold on both databases, and a Postgres target adds
one: it is never a file the caller owns, so it always needs a session and `--actor` is honoured only
when it is the session's own actor. Runs on the adapters named by ``--adapters``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from auth_support import bootstrap, login
from auth_support import run as tl
from sqlalchemy import text
from tl_adapters.db import DbTarget, is_postgres, open_uow
from tl_cli import session

DEMO = "demo"

AUTO_SIGN_IN = False  # these tests are about who is signed in (see conftest.py)


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    return new_db()


def ledger(target: DbTarget, tl_env: str = "dev") -> dict[str, str]:
    env = {"TL_DB": str(target), "TL_ENV": tl_env}
    result = tl(env, "init")
    assert result.exit_code == 0, result.output
    return env


@pytest.fixture
def env(target: DbTarget) -> dict[str, str]:
    values = ledger(target)
    assert bootstrap(values).exit_code == 0
    return values


def rows(env: dict[str, str], sql: str) -> list[tuple[Any, ...]]:
    with open_uow(env["TL_DB"], readonly=True) as uow:
        return [tuple(r) for r in uow.conn().execute(text(sql)).fetchall()]


def last_actor(env: dict[str, str]) -> str:
    found = rows(
        env,
        "SELECT actor FROM events WHERE event_type NOT LIKE 'Account.%' "
        "AND event_type NOT LIKE 'AgentToken.%' ORDER BY seq DESC",
    )
    return str(found[0][0])


def create(env: dict[str, str], *extra: str) -> Any:
    return tl(env, "record", "create", "--project", "P123", "--title", "T", *extra)


def test_login_whoami_the_default_actor_and_logout_on_either_database(
    env: dict[str, str],
) -> None:
    signed_in = login(env)
    assert signed_in.exit_code == 0, signed_in.output
    assert signed_in.stdout.strip() == "signed in as user:root (admin)"
    assert tl(env, "whoami").stdout.splitlines() == ["user:root", "roles: admin"]
    assert create(env).exit_code == 0
    assert last_actor(env) == "user:root"  # the default actor is the signed-in user
    out = tl(env, "logout")
    assert out.exit_code == 0 and out.stdout.strip() == "signed out root"
    assert tl(env, "whoami").exit_code == 1


def test_the_session_file_names_the_ledger_and_never_a_password(
    env: dict[str, str], target: DbTarget
) -> None:
    assert login(env).exit_code == 0
    stored = session.session_file().read_text(encoding="utf-8")
    key = session.db_target(target)
    assert f'"{key}"' in stored or key.replace("\\", "\\\\") in stored
    if is_postgres(target):
        assert key.startswith("pg:postgres@localhost:5432/")
        assert "postgres:postgres@" not in stored  # user:password never reaches the file
        assert "sslmode" not in stored


def test_the_actor_rules_differ_only_where_a_database_server_is_not_a_file(
    env: dict[str, str], target: DbTarget
) -> None:
    server = is_postgres(target)
    # not signed in: a ledger file in a dev setup falls back to user:dev, a server never does
    unsigned = create(env)
    if server:
        assert unsigned.exit_code == 1 and unsigned.stderr.startswith("error: not signed in")
        named = create(env, "--actor", "user:other")
        assert named.exit_code == 1 and named.stderr.startswith("error: not signed in")
        assert "postgres:postgres@" not in unsigned.output + named.output
    else:
        assert unsigned.exit_code == 0 and last_actor(env) == "user:dev"
        assert create(env, "--actor", "user:other").exit_code == 0
    assert login(env).exit_code == 0
    assert create(env, "--actor", "user:root").exit_code == 0  # the session's own actor
    other = create(env, "--actor", "user:other")
    if server:
        assert other.exit_code == 1 and "is not the signed-in user" in other.stderr
    else:
        assert other.exit_code == 0 and last_actor(env) == "user:other"
    prod = create(env | {"TL_ENV": "prod"}, "--actor", "user:other")
    assert prod.exit_code == 1 and "is not the signed-in user" in prod.stderr


def test_a_session_belongs_to_one_ledger(
    env: dict[str, str], new_db: Callable[[], DbTarget]
) -> None:
    assert login(env).exit_code == 0
    elsewhere = ledger(new_db(), "prod")
    assert bootstrap(elsewhere).exit_code == 0
    assert tl(elsewhere, "whoami").exit_code == 1  # no session for that ledger
    assert tl(env, "whoami").exit_code == 0


def test_init_dev_makes_the_demo_account_where_the_environment_allows_it(
    target: DbTarget,
) -> None:
    env = {"TL_DB": str(target), "TL_ENV": "dev"}
    made = tl(env, "init", "--dev")
    assert made.exit_code == 0, made.output
    assert "demo" in made.stderr.lower()  # the warning that the demo account exists
    signed_in = login(env, DEMO, DEMO)
    assert signed_in.exit_code == 0, signed_in.output
    assert signed_in.stdout.strip() == "signed in as user:demo (admin)"
    assert create(env).exit_code == 0 and last_actor(env) == "user:demo"
    again = tl(env, "init", "--dev")  # idempotent
    assert again.exit_code == 0, again.output


def test_init_dev_is_refused_in_production_and_nothing_is_created(
    target: DbTarget,
) -> None:
    prod = tl({"TL_DB": str(target), "TL_ENV": "prod"}, "init", "--dev")
    assert prod.exit_code == 1 and "needs TL_ENV=dev" in prod.stderr
    if not is_postgres(target):
        assert not Path(target).exists()
