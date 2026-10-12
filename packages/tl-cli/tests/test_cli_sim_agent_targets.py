"""The simulator's agent token on a SQLite file and on Postgres (P1-I0 workstream B, review fix).

On a file in a dev setup the operator mints the token as ``svc:sim`` (workstream A). A Postgres
ledger is not a file the operator owns: with no session, ``TL_ENV=dev`` alone must not mint an
agent token there; with a signed-in admin it does, as that admin. Runs on both adapters.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from auth_support import GOOD, bootstrap, login
from auth_support import run as tl
from sqlalchemy import text
from tl_adapters.db import DbTarget, is_postgres, open_uow
from tl_cli import sim_agent
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.tokens import token_kind
from typer import Exit

AUTO_SIGN_IN = False  # these tests decide who is signed in


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    return new_db()


@pytest.fixture
def env(target: DbTarget) -> dict[str, str]:
    values = {"TL_DB": str(target), "TL_ENV": "dev"}
    assert tl(values, "init").exit_code == 0
    return values


def makers(env: dict[str, str]) -> list[str]:
    """The actor of every account and agent-token event, oldest first."""
    with open_uow(env["TL_DB"], readonly=True) as uow:
        found = uow.conn().execute(
            text(
                "SELECT actor FROM events WHERE event_type IN "
                "('Account.Created', 'AgentToken.Issued') ORDER BY seq"
            )
        )
        return [str(row[0]) for row in found]


def test_without_a_session_a_file_mints_as_the_operator_and_a_server_mints_nothing(
    env: dict[str, str], target: DbTarget, capsys: pytest.CaptureFixture[str]
) -> None:
    if not is_postgres(target):
        get = sim_agent.provider(target)
        assert get is not None and token_kind(get()) == "agent"
        assert set(makers(env)) == {"svc:sim"}
        return
    assert sim_agent.provider(target) is None  # the simulator then asks for TL_SIM_AGENT_TOKEN
    with pytest.raises(Exit):
        sim_agent.issue_token(target)
    assert "not signed in" in capsys.readouterr().err
    assert makers(env) == []  # no sim-assistant account, no token, no event


def test_a_signed_in_user_without_the_admin_role_cannot_mint_one_on_a_server(
    env: dict[str, str], target: DbTarget, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bootstrap(env).exit_code == 0
    assert login(env).exit_code == 0
    made = tl(env, "admin", "user", "add", "amy", "--password-stdin", stdin=GOOD)
    assert made.exit_code == 0, made.output
    assert login(env, "amy").exit_code == 0
    before = makers(env)
    if not is_postgres(target):  # a file in a dev setup: the operator mints, whoever is signed in
        assert sim_agent.provider(target) is not None
        return
    assert sim_agent.provider(target) is None
    with pytest.raises(Exit):
        sim_agent.issue_token(target)
    assert "forbidden" in capsys.readouterr().err
    assert makers(env) == before  # nothing was made


def test_a_signed_in_admin_mints_it_on_a_server_and_the_events_name_that_admin(
    env: dict[str, str], target: DbTarget
) -> None:
    assert bootstrap(env).exit_code == 0
    assert login(env).exit_code == 0
    get = sim_agent.provider(target)
    assert get is not None
    first = get()
    assert token_kind(first) == "agent" and get() == first
    assert sim_agent.issue_token(target) != first
    who = makers(env)
    if is_postgres(target):
        assert "svc:sim" not in who  # never the operator on a server
        # the admin was made by the recovery command; then the agent and two tokens: by that admin
        assert who == ["svc:bootstrap", "user:root", "user:root", "user:root"]
    else:
        assert who.count("svc:sim") == 3  # the agent and two tokens


def test_outside_a_dev_setup_nothing_is_minted_whatever_the_ledger(
    env: dict[str, str], target: DbTarget, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert bootstrap(env).exit_code == 0
    assert login(env).exit_code == 0
    monkeypatch.setenv("TL_ENV", "prod")
    assert sim_agent.provider(target) is None
    with pytest.raises(ForbiddenError):
        sim_agent.issue_token(target)


def test_the_repr_of_the_run_environment_hides_a_ledger_url() -> None:
    from tl_sim.api import SimEnv

    shown = repr(SimEnv(db_path="postgresql://tl:s3cret@db.example/ledger"))
    assert "s3cret" not in shown and "db.example" not in shown
