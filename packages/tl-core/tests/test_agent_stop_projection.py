"""P2-X2-S3: ``cur_agent_stop`` rebuilt from the ledger equals the live table (both adapters)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory, rebuild_projections
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.services.agent_stop import (
    ResumeAgent,
    StopAgent,
    handle_resume_agent,
    handle_stop_agent,
)
from tl_core.services.commands import CreateRecord
from tl_core.services.proposals import submit

_AUTH = str(Path(__file__).resolve().parents[3] / "tests" / "auth")
if _AUTH not in sys.path:
    sys.path.insert(0, _AUTH)

from authworld import MovingClock, World  # noqa: E402

ADA = "user:ada"
STOP_SQL = "SELECT agent, account_id, stopped, stopped_at, stopped_by, reason, resumed_at, resumed_by, last_seq FROM cur_agent_stop ORDER BY agent"  # noqa: E501
ACCOUNT_SQL = "SELECT account_id, version, last_seq, status FROM cur_account ORDER BY account_id"


@pytest.fixture
def world(db: DbTarget) -> Iterator[World]:
    factory = make_uow_factory(db)
    made = World(db, factory, MovingClock())
    made.create("ada", roles=("admin",))
    for name in ("bot", "bot2"):
        made.create(name, kind="agent")
        with factory() as uow:  # an agent files only on an explicit grant (P2-X2 S1)
            found = find_account(uow.conn(), username=name)
            assert found is not None
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor=ADA, source="test", scope="company", account_id=found.account_id,
                    project="project:P1", module="*", role="user", reason="test",
                ),
            )  # fmt: skip
    try:
        yield made
    finally:
        factory.dispose()


def file(w: World, agent: str) -> None:
    cmd = CreateRecord(
        actor=agent, source="mcp:x", scope="project:P1", record_type="core.Record",
        title="t", key=f"K-{agent}",
    )  # fmt: skip
    submit(w.factory, tool="create_record", agent=agent, command=cmd, summary="s", budget=9)


def stop(w: World, agent: str, reason: str | None = None) -> None:
    with w.factory() as uow:
        handle_stop_agent(
            uow,
            StopAgent(actor=ADA, source="t", scope="company", agent=agent, reason=reason),
        )


def resume(w: World, agent: str) -> None:
    with w.factory() as uow:
        handle_resume_agent(uow, ResumeAgent(actor=ADA, source="t", scope="company", agent=agent))


def test_rebuild_equals_live(world: World, db: DbTarget) -> None:
    for agent in ("agent:bot", "agent:bot2"):
        file(world, agent)
    stop(world, "agent:bot", "first")
    stop(world, "agent:bot2")
    resume(world, "agent:bot")
    stop(world, "agent:bot", "again")  # stop, resume, stop: the row is the last word
    resume(world, "agent:bot2")
    live = (world.rows(STOP_SQL), world.rows(ACCOUNT_SQL))
    assert [(r[0], r[2], r[5]) for r in live[0]] == [
        ("agent:bot", 1, "again"),
        ("agent:bot2", 0, None),
    ]
    rebuild_projections(db)
    assert (world.rows(STOP_SQL), world.rows(ACCOUNT_SQL)) == live


def test_rebuild_of_an_empty_stop_table_is_empty(world: World, db: DbTarget) -> None:
    rebuild_projections(db)
    assert world.rows(STOP_SQL) == []


def test_the_events_are_append_only_rows(world: World) -> None:
    file(world, "agent:bot")
    stop(world, "agent:bot")
    resume(world, "agent:bot")
    kinds = world.rows("SELECT event_type FROM events WHERE event_type LIKE 'Agent.%' ORDER BY seq")
    assert [r[0] for r in kinds] == ["Agent.Stopped", "Agent.Resumed"]
    with pytest.raises(Exception, match="(?i)append|immutable|update|delete"):
        with world.factory() as uow:
            uow.conn().execute(
                text("UPDATE events SET actor = 'x' WHERE event_type = 'Agent.Stopped'")
            )


@pytest.mark.parametrize("only", [["accounts"], ["agent_stop"], ["accounts", "agent_stop"]])
def test_a_partial_rebuild_leaves_stop_resume_and_account_commands_working(
    world: World, db: DbTarget, only: list[str]
) -> None:
    file(world, "agent:bot")
    stop(world, "agent:bot")
    resume(world, "agent:bot")
    stop(world, "agent:bot")
    live = world.rows(ACCOUNT_SQL)
    rebuild_projections(db, types=only)
    assert world.rows(ACCOUNT_SQL) == live  # the version is the stream head again
    resume(world, "agent:bot")
    stop(world, "agent:bot")
    resume(world, "agent:bot")
    bot = str(world.rows("SELECT account_id FROM cur_account WHERE username = 'bot'")[0][0])
    with world.factory() as uow:
        accounts.disable(uow, account_id=bot, by=ADA, reason=None)
