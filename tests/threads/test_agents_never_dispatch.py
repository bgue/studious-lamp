"""An agent never previews or confirms a dispatch, by any path, and a dispatch never forwards a
workflow role or a risk acceptance (ADR-0018; security review of P1-I7 WS-A)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from thread_world import P1, TableRunner, everyone, make_person, make_record, planning_world
from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.contract import PlannedCommand
from tl_core.services import proposals
from tl_core.services.commands import CommandResult
from tl_core.services.errors import ProposalDeciderError
from tl_core.threads.dispatch import (
    DispatchFromThread,
    build_dispatch_proposal,
    handle_dispatch_from_thread,
)
from tl_core.threads.errors import DispatchForbiddenError
from tl_core.threads.planner import ThreadPlanner
from tl_core.threads.targets import TargetRegistry, core_targets

AGENT = "agent:planner"


class CountingRunner(TableRunner):
    """The real table, counting what is run through it."""

    def __init__(self) -> None:
        super().__init__()
        self.ran: list[str] = []

    def run(self, uow: Any, command: Any) -> CommandResult:
        self.ran.append(f"{type(command).__name__} as {command.actor}")
        return super().run(uow, command)


@pytest.fixture(autouse=True)
def world(db: DbTarget) -> Iterator[None]:
    make_person(db, "rgarcia")
    make_person(db, "planner", "agent")
    with planning_world():
        yield


def factory_of(db: DbTarget) -> Any:
    return lambda readonly=False: open_uow(db, readonly=readonly)


def person_token(db: DbTarget, rid: str, line: str) -> Any:
    with open_uow(db, readonly=True) as uow:
        return ThreadPlanner(factory=factory_of(db)).preview(
            uow,
            record_id=rid,
            text=line,
            actor="user:rgarcia",
            holds=everyone,
            runner=TableRunner(),
        )


def count(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_an_agent_has_no_preview(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    for actor in (AGENT, "svc:rule-x", "system:y"):
        with open_uow(db, readonly=True) as uow, pytest.raises(DispatchForbiddenError):
            ThreadPlanner(factory=factory_of(db)).preview(
                uow, record_id=rid, text="/link REC-2", actor=actor, holds=everyone,
                runner=TableRunner(),
            )  # fmt: skip


def test_an_agents_plan_runs_nothing_as_the_agent(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    runner = CountingRunner()
    command = build_dispatch_proposal(
        factory_of(db), scope=P1, record_id=rid, text="/link REC-2", agent=AGENT, runner=runner
    )
    assert runner.ran == [] and len(command.token) == 64
    assert count(db, "SELECT COUNT(*) FROM cur_links") == 0


def test_no_one_but_a_person_confirms_a_dispatch(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    found = person_token(db, rid, "/link REC-2")
    runner = CountingRunner()
    for actor in (AGENT, "svc:rule-x", "svc:action-y", "system:z"):
        cmd = DispatchFromThread(
            actor=actor, source="t", scope=P1, record_id=rid, text="/link REC-2", token=found.token
        )
        with pytest.raises(DispatchForbiddenError), open_uow(db) as uow:
            handle_dispatch_from_thread(uow, cmd, holds=everyone, runner=runner)
    assert runner.ran == [] and count(db, "SELECT COUNT(*) FROM cur_links") == 0


def test_an_agent_cannot_accept_its_own_proposal(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    factory = factory_of(db)
    runner = TableRunner()
    command = build_dispatch_proposal(
        factory, scope=P1, record_id=rid, text="/link REC-2", agent=AGENT, runner=runner
    )
    view = proposals.submit(
        factory, tool="propose_dispatch", agent=AGENT, command=command, summary="s", runner=runner
    )
    with pytest.raises(ProposalDeciderError):
        proposals.accept_or_fail(
            factory, proposal_id=view.proposal_id, by=AGENT, holds=lambda level: True, runner=runner
        )
    assert count(db, "SELECT COUNT(*) FROM cur_links") == 0


def test_a_planned_command_never_carries_a_role_or_a_risk_acceptance(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    registry = TargetRegistry()
    for target in core_targets():
        registry.register(target)

    class Sneaky:
        verb = "hold"
        name = "*"

        def plan(self, uow: Any, context: Any, parsed: Any) -> list[PlannedCommand]:
            return [
                PlannedCommand(
                    command_type="TransitionWorkflow",
                    command={"stream_id": rid, "transition": "issue", "actor_roles": ["boss"]},
                ),
                PlannedCommand(
                    command_type="ChangeSetting",
                    command={"key": "threads.enabled", "accept_risk": True},
                ),
            ]

    registry.register(Sneaky())  # type: ignore[arg-type]
    with open_uow(db, readonly=True) as uow:
        found = ThreadPlanner(targets=registry).preview(
            uow,
            record_id=rid,
            text="/hold now",
            actor="user:rgarcia",
            holds=everyone,
            runner=TableRunner(),
        )
    assert not isinstance(found, type(None)) and not found.can_dispatch  # type: ignore[union-attr]
    codes = [p.problem.code for p in found.planned if p.problem]  # type: ignore[union-attr]
    assert codes == ["reserved_field", "reserved_field"]
