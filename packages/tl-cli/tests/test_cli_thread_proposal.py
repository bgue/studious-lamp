"""`tl proposal accept` runs an agent's proposed dispatch as the person (P1-I7 WS-B, ADR-0018)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from thread_cli_support import P, create, run, thread_env
from tl_adapters.db import DbTarget, is_postgres, make_uow_factory, open_uow
from tl_api.thread_runner import thread_runner
from tl_core.auth import accounts
from tl_core.services import proposals
from tl_core.threads.dispatch import build_dispatch_proposal


def agent_proposal(env: dict[str, str], key: str, line: str) -> str:
    """The id of a pending proposal of `line` on record `key`, filed by agent triage."""
    with open_uow(env["TL_DB"]) as uow:
        accounts.create_account(
            uow,
            username="triage",
            display_name="triage",
            kind="agent",
            roles=["user"],
            password=None,
            by="user:a",
        )
        rid = (
            uow.conn()
            .execute(
                text("SELECT id FROM cur_core_record WHERE key = :k"),
                {"k": key},
            )
            .scalar_one()
        )
    factory = make_uow_factory(env["TL_DB"])
    runner = thread_runner()
    command = build_dispatch_proposal(
        factory,
        scope=f"project:{P}",
        record_id=str(rid),
        text=line,
        agent="agent:triage",
        runner=runner,
    )
    view = proposals.submit(
        factory,
        tool="propose_dispatch",
        agent="agent:triage",
        command=command,
        summary="link",
        runner=runner,
    )
    return view.proposal_id


def test_a_person_accepts_an_agents_dispatch_proposal(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = thread_env(new_db, monkeypatch, tmp_path)
    key = create(env, "Gate valve")
    other = create(env, "Check valve")
    proposal_id = agent_proposal(env, key, f"/link {other}")
    done = run(env, "proposal", "accept", proposal_id)
    assert done.exit_code == 0, done.output
    assert done.stdout.splitlines()[0] == f"accepted {proposal_id}"
    shown = run(env, "thread", "show", "--project", P, key).stdout
    assert f"/link {other}" in shown and "-> link:" in shown


def test_a_person_with_no_account_cannot_accept_even_an_effect_only_dispatch(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = thread_env(new_db, monkeypatch, tmp_path)
    if is_postgres(env["TL_DB"]):  # conftest makes an admin account for every `--actor` it sees
        pytest.skip("the Postgres test wrapper signs any named actor in; core and API cover it")
    key = create(env, "Gate valve")
    assert run(env, "thread", "post", "--project", P, key, "something to summarise").exit_code == 0
    proposal_id = agent_proposal(env, key, "/summarise")
    ghost = run(env, "proposal", "accept", proposal_id, "--actor", "user:ghost")
    assert ghost.exit_code == 1 and ghost.stderr.startswith("error: "), ghost.output
    shown = run(env, "thread", "show", "--project", P, key).stdout
    assert "Thread summary" not in shown
    again = run(env, "proposal", "accept", proposal_id)
    assert again.exit_code == 0, again.output
    assert "Thread summary" in run(env, "thread", "show", "--project", P, key).stdout
