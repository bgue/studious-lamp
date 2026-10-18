"""propose_dispatch: an agent proposes, a person accepts, the plan is made again for the person."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from thread_world import P1, TableRunner, make_record, planning_world, put_setting
from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.contract import Access
from tl_core.proposals.types import PROPOSABLE_TOOLS, ProposalView
from tl_core.services import proposals
from tl_core.services.commands import UpdateRecord
from tl_core.services.records import handle_update_record
from tl_core.threads.dispatch import DispatchFromThread, build_dispatch_proposal
from tl_core.threads.errors import DispatchDisabledError, DispatchRefusedError, DispatchSyntaxError

RUNNER = TableRunner()
AGENT = "agent:planner"
PERSON = "user:mlee"


@pytest.fixture(autouse=True)
def world() -> Iterator[None]:
    with planning_world():
        yield


def factory_of(db: DbTarget) -> Any:
    return lambda readonly=False: open_uow(db, readonly=readonly)


def propose(db: DbTarget, rid: str, line: str) -> ProposalView:
    factory = factory_of(db)
    command = build_dispatch_proposal(
        factory, scope=P1, record_id=rid, text=line, agent=AGENT, runner=RUNNER
    )
    return proposals.submit(
        factory,
        tool="propose_dispatch",
        agent=AGENT,
        command=command,
        summary=f"Dispatch {line}"[:200],
        runner=RUNNER,
    )


def accept(
    db: DbTarget, view: ProposalView, holds: Any = lambda level: level == "user"
) -> ProposalView:
    return proposals.accept_or_fail(
        factory_of(db), proposal_id=view.proposal_id, by=PERSON, holds=holds, runner=RUNNER
    )


def count(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_the_tool_is_proposable_and_maps_to_the_command() -> None:
    assert PROPOSABLE_TOOLS["propose_dispatch"] == "DispatchFromThread"
    assert proposals.access_of("DispatchFromThread") == "user"


def test_nothing_runs_until_a_person_accepts_and_then_it_runs_as_the_person(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    other = make_record(db, "REC-2")
    view = propose(db, rid, "/link REC-2")
    assert view.status == "pending" and view.command["token"]
    assert count(db, "SELECT COUNT(*) FROM cur_links") == 0
    assert count(db, "SELECT COUNT(*) FROM cur_thread_message") == 0
    done = accept(db, view)
    assert done.status == "accepted"
    with open_uow(db, readonly=True) as uow:
        link = uow.conn().execute(text("SELECT from_id, to_id FROM cur_links")).one()
        message = (
            uow.conn().execute(text("SELECT author, kind, body FROM cur_thread_message")).one()
        )
        sources = {
            r.source for r in uow.conn().execute(text("SELECT source FROM events WHERE seq > 3"))
        }
    assert (link.from_id, link.to_id) == (rid, other)
    assert (message.author, message.kind, message.body) == (PERSON, "dispatch", "/link REC-2")
    assert sources >= {f"thread:{rid}"}


def test_a_plan_that_changed_fails_the_proposal(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    view = propose(db, rid, "/link REC-2")
    with open_uow(db) as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor="u",
                source="t",
                scope=P1,
                stream_id=rid,
                expected_version=1,
                changes={"title": "changed"},
            ),
        )
    done = accept(db, view)
    assert done.status == "failed" and "DispatchStaleError" in (done.reason or "")
    assert count(db, "SELECT COUNT(*) FROM cur_links") == 0


class StrictRunner(TableRunner):
    """The table, except that adding a link needs the admin."""

    def access_of(self, command_type: str) -> Access | None:
        return "admin" if command_type == "AddLink" else super().access_of(command_type)


def test_a_person_who_may_not_run_every_command_cannot_accept(db: DbTarget) -> None:
    runner = StrictRunner()
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    factory = factory_of(db)
    command = build_dispatch_proposal(
        factory, scope=P1, record_id=rid, text="/link REC-2", agent=AGENT, runner=runner
    )
    view = proposals.submit(
        factory, tool="propose_dispatch", agent=AGENT, command=command, summary="s", runner=runner
    )

    def accept_with(holds: Any) -> ProposalView:
        return proposals.accept_or_fail(
            factory, proposal_id=view.proposal_id, by=PERSON, holds=holds, runner=runner
        )

    # the same proposal, two people: the one without the access gets a failure, nothing runs
    failed = accept_with(lambda level: level == "user")
    assert failed.status == "failed" and "DispatchRefusedError" in (failed.reason or "")
    assert count(db, "SELECT COUNT(*) FROM cur_links") == 0
    second = proposals.submit(
        factory, tool="propose_dispatch", agent=AGENT, command=command, summary="s", runner=runner
    )
    done = proposals.accept_or_fail(
        factory, proposal_id=second.proposal_id, by=PERSON, holds=lambda level: True, runner=runner
    )
    assert done.status == "accepted" and count(db, "SELECT COUNT(*) FROM cur_links") == 1


def test_a_proposal_for_a_plan_with_problems_is_refused_at_once(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    factory = factory_of(db)
    with pytest.raises(DispatchRefusedError):
        build_dispatch_proposal(
            factory, scope=P1, record_id=rid, text="/link NOPE", agent=AGENT, runner=RUNNER
        )
    with pytest.raises(DispatchRefusedError):
        build_dispatch_proposal(
            factory, scope=P1, record_id=rid, text="/assign @x W1", agent=AGENT, runner=RUNNER
        )
    with pytest.raises(DispatchSyntaxError):
        build_dispatch_proposal(
            factory, scope=P1, record_id=rid, text="hello", agent=AGENT, runner=RUNNER
        )


def test_agents_cannot_propose_when_the_setting_says_none(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-2")
    put_setting(db, "threads.agents.can_dispatch", "none")
    with pytest.raises(DispatchDisabledError):
        propose(db, rid, "/link REC-2")


def test_the_access_levels_are_not_a_request_field() -> None:
    fields = set(DispatchFromThread.model_fields)
    assert fields.isdisjoint({"holds", "roles", "actor_roles", "access", "runner"})
