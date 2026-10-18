"""`tl proposal accept` runs an agent's proposed dispatch as the person (P1-I7 WS-B, ADR-0018)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from thread_cli_support import P, create, run, thread_env
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_api.thread_runner import thread_runner
from tl_core.auth import accounts
from tl_core.services import proposals
from tl_core.threads.dispatch import build_dispatch_proposal


def test_a_person_accepts_an_agents_dispatch_proposal(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = thread_env(new_db, monkeypatch, tmp_path)
    key = create(env, "Gate valve")
    other = create(env, "Check valve")
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
        text=f"/link {other}",
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
    done = run(env, "proposal", "accept", view.proposal_id)
    assert done.exit_code == 0, done.output
    assert done.stdout.splitlines()[0] == f"accepted {view.proposal_id}"
    shown = run(env, "thread", "show", "--project", P, key).stdout
    assert f"/link {other}" in shown and "-> link:" in shown
