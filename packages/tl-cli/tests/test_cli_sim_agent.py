"""The simulator's agent account and token on the dev ledger (P1-I0-T11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from auth_support import new_ledger, rows
from tl_adapters.db import make_uow_factory
from tl_cli import sim_agent
from tl_core.auth import sessions
from tl_core.auth.errors import InvalidCredentialsError
from tl_core.auth.tokens import token_kind
from tl_sim import cli as sim_cli
from tl_sim.mcp_caller import stdio_caller


def live_tokens(env: dict[str, str]) -> int:
    return int(rows(env, "SELECT COUNT(*) FROM cur_agent_token WHERE revoked = 0")[0][0])


def test_the_provider_makes_the_agent_and_one_live_token_per_use(tmp_path: Path) -> None:
    env = new_ledger(tmp_path)
    db = Path(env["TL_DB"])
    get = sim_agent.provider(db)
    assert get is not None
    first = get()
    assert token_kind(first) == "agent" and get() == first  # made once per process
    factory = make_uow_factory(db)
    try:
        assert sessions.principal_for_bearer(factory, first).actor == "agent:sim-assistant"
        second = sim_agent.provider(db)()  # type: ignore[misc]
        assert second != first and live_tokens(env) == 1  # the earlier run's token was revoked
        with pytest.raises(InvalidCredentialsError):
            sessions.principal_for_bearer(factory, first)
        assert sessions.principal_for_bearer(factory, second).actor == "agent:sim-assistant"
    finally:
        factory.dispose()
    created = rows(env, "SELECT actor FROM events WHERE event_type = 'Account.Created'")
    assert created == [("svc:sim",)]
    assert first not in str(rows(env, "SELECT payload FROM events"))


def test_twenty_runs_do_not_exhaust_the_agents_token_allowance(tmp_path: Path) -> None:
    env = new_ledger(tmp_path)
    for _ in range(25):
        sim_agent.issue_token(Path(env["TL_DB"]))
    assert live_tokens(env) == 1


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
