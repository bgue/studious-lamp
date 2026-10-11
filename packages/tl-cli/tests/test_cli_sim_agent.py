"""The simulator's agent account and token on the dev ledger (P1-I0-T11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from auth_support import GOOD, new_ledger, rows, run
from tl_adapters.db import make_uow_factory
from tl_cli import sim_agent
from tl_cli.session import open_backend
from tl_core.auth import sessions
from tl_core.auth.errors import ForbiddenError, InvalidAccountError, InvalidCredentialsError
from tl_core.auth.tokens import token_kind
from tl_sim import cli as sim_cli
from tl_sim.mcp_caller import stdio_caller


def live_tokens(env: dict[str, str]) -> int:
    return int(rows(env, "SELECT COUNT(*) FROM cur_agent_token WHERE revoked = 0")[0][0])


def test_the_provider_makes_the_agent_and_a_token_once_per_process(tmp_path: Path) -> None:
    env = new_ledger(tmp_path)
    db = Path(env["TL_DB"])
    get = sim_agent.provider(db)
    assert get is not None
    first = get()
    assert token_kind(first) == "agent" and get() == first  # made once per process
    factory = make_uow_factory(db)
    try:
        assert sessions.principal_for_bearer(factory, first).actor == "agent:sim-assistant"
        second = sim_agent.issue_token(db)  # another run, maybe at the same time
        assert second != first and live_tokens(env) == 2
        assert sessions.principal_for_bearer(factory, first).actor == "agent:sim-assistant"
        assert sessions.principal_for_bearer(factory, second).actor == "agent:sim-assistant"
    finally:
        factory.dispose()
    created = rows(env, "SELECT actor FROM events WHERE event_type = 'Account.Created'")
    assert created == [("svc:sim",)]
    assert first not in str(rows(env, "SELECT payload FROM events"))


def test_concurrent_runs_keep_their_tokens_and_the_oldest_go_beyond_the_rotating_set(
    tmp_path: Path,
) -> None:
    env = new_ledger(tmp_path)
    db = Path(env["TL_DB"])
    tokens = [sim_agent.issue_token(db) for _ in range(sim_agent.KEEP)]
    assert live_tokens(env) == sim_agent.KEEP
    factory = make_uow_factory(db)
    try:
        for token in tokens:  # ten runs at once: nobody was revoked
            sessions.principal_for_bearer(factory, token)
        newest = sim_agent.issue_token(db)
        assert live_tokens(env) == sim_agent.KEEP  # one went to make room: the oldest
        with pytest.raises(InvalidCredentialsError):
            sessions.principal_for_bearer(factory, tokens[0])
        for token in (*tokens[1:], newest):
            sessions.principal_for_bearer(factory, token)
    finally:
        factory.dispose()


def test_expired_tokens_are_revoked_whatever_the_rotating_set_holds(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from tl_core.auth import accounts, queries

    env = new_ledger(tmp_path)
    db = Path(env["TL_DB"])
    sim_agent.issue_token(db)
    past = datetime.now(UTC) - timedelta(days=3)
    backend = open_backend(db)
    with backend() as uow:
        agent = queries.find_account(uow.conn(), username="sim-assistant")
        assert agent is not None
        accounts.issue_agent_token(
            uow, account_id=agent.account_id, label="old run",
            expires_at=past + timedelta(days=1), by="svc:sim", clock=lambda: past,
        )  # fmt: skip
    assert live_tokens(env) == 2
    sim_agent.issue_token(db)
    assert live_tokens(env) == 2  # the expired one was revoked, the fresh two remain
    assert (
        rows(env, "SELECT COUNT(*) FROM cur_agent_token WHERE label = 'old run' AND revoked = 1")[
            0
        ][0]
        == 1
    )


def test_twenty_five_runs_do_not_exhaust_the_agents_token_allowance(tmp_path: Path) -> None:
    env = new_ledger(tmp_path)
    for _ in range(25):
        sim_agent.issue_token(Path(env["TL_DB"]))
    assert live_tokens(env) == sim_agent.KEEP


def test_issue_token_itself_refuses_outside_a_dev_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = new_ledger(tmp_path)
    monkeypatch.setenv("TL_ENV", "prod")
    with pytest.raises(ForbiddenError, match="only where TL_ENV is dev, demo or test"):
        sim_agent.issue_token(Path(env["TL_DB"]))
    assert rows(env, "SELECT COUNT(*) FROM cur_account")[0][0] == 0


def test_a_person_account_with_the_agents_name_is_a_clear_error(tmp_path: Path) -> None:
    env = new_ledger(tmp_path)
    assert (
        run(
            env, "admin", "bootstrap", "--username", "sim-assistant", stdin=f"{GOOD}\n{GOOD}\n"
        ).exit_code
        == 0
    )
    with pytest.raises(InvalidAccountError, match="is a person account, not an agent"):
        sim_agent.issue_token(Path(env["TL_DB"]))
    assert live_tokens(env) == 0


@pytest.mark.parametrize("mode", ["prod", "", "staging"])
def test_outside_a_dev_setup_it_makes_nothing(
    tmp_path: Path, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = new_ledger(tmp_path)
    monkeypatch.setenv("TL_ENV", mode)
    assert sim_agent.provider(Path(env["TL_DB"])) is None
    assert rows(env, "SELECT COUNT(*) FROM cur_account")[0][0] == 0


def test_no_ledger_file_means_no_provider(tmp_path: Path) -> None:
    assert sim_agent.provider(tmp_path / "none.db") is None


def test_tl_sim_is_wired_to_the_provider() -> None:
    from tl_cli import main  # noqa: F401  (importing it installs the hook)

    assert sim_cli.AGENT_TOKEN_SOURCE is sim_agent.provider


def test_the_token_it_makes_starts_the_mcp_server_as_the_agent(tmp_path: Path) -> None:
    env = new_ledger(tmp_path)
    db = Path(env["TL_DB"])
    get = sim_agent.provider(db)
    assert get is not None
    result = stdio_caller(db, get()).call_tool("search_records", {"scope": "project:sim-r1"})
    assert result["total"] == 0
