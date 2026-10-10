"""The proposals service against a real ledger (P0-I6-S22; brief 11.3, FANOUT D4)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError, Event
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import (
    BudgetExceededError,
    GuardFailedError,
    InvalidProposalError,
    LockTimeoutError,
    ProposalDeciderError,
    ProposalNotFoundError,
    ProposalNotPendingError,
    RecordNotFoundError,
)
from tl_core.services.links import AddLink
from tl_core.services.psets import SetPsetValues
from tl_core.services.records import handle_create_record
from tl_core.services.workflow import TransitionWorkflow
from tl_core.workflow.definition import WorkflowDefinition
from tl_core.workflow.loader import WorkflowRegistry
from tl_core.workflow.provider import use_workflows

P1 = "project:P123"
AGENT = "agent:triage"
ALICE = "user:alice"

FLOW: dict[str, Any] = {
    "id": "t.flow",
    "version": 1,
    "record_type": "core.Record",
    "initial_state": "Draft",
    "states": [{"name": "Draft"}, {"name": "Review"}, {"name": "Done"}],
    "transitions": [
        {
            "name": "submit",
            "from": ["Draft"],
            "to": "Review",
            "guards": [
                {
                    "kind": "required_psets",
                    "psets": ["valve_data"],
                    "values": ["valve_data.manufacturer"],
                }
            ],
        },
        {
            "name": "finish",
            "from": ["Draft"],
            "to": "Done",
            "guards": [{"kind": "roles", "any_of": ["manager"]}],
        },
    ],
}


@pytest.fixture(autouse=True)
def flow() -> Iterator[None]:
    with use_workflows(WorkflowRegistry([WorkflowDefinition.model_validate(FLOW)])):
        yield


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db

    def factory(self, readonly: bool = False) -> Any:
        return open_uow(self.db, readonly=readonly)

    def create(self, key: str, scope: str = P1) -> str:
        with open_uow(self.db) as uow:
            return handle_create_record(
                uow,
                CreateRecord(
                    actor="user:seed",
                    source="t",
                    scope=scope,
                    record_type="core.Record",
                    title=key,
                    key=key,
                ),
            ).stream_id

    def head(self) -> int:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.head_seq()

    def events(self, stream_id: str) -> list[Event]:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.read_stream(stream_id)

    def all_events(self) -> list[Event]:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.read_after(0, limit=1000)

    def record(self, key: str) -> dict[str, Any] | None:
        with open_uow(self.db, readonly=True) as uow:
            row = (
                uow.conn()
                .execute(
                    text("SELECT id, title, status, version FROM cur_core_record WHERE key = :k"),
                    {"k": key},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def get(self, proposal_id: str) -> ProposalView:
        with open_uow(self.db, readonly=True) as uow:
            return proposals.get_proposal(uow.conn(), proposal_id)

    def pending(self, scope: str = P1) -> list[ProposalView]:
        with open_uow(self.db, readonly=True) as uow:
            return proposals.list_proposals(uow.conn(), scope)

    def submit(self, command: Any, tool: str, **kw: Any) -> ProposalView:
        kw.setdefault("summary", "a change")
        return proposals.submit(
            self.factory, tool=tool, agent=kw.pop("agent", AGENT), command=command, **kw
        )


@pytest.fixture
def world(new_db: Callable[[], DbTarget]) -> World:
    db = new_db()
    create_schema(db)
    return World(db)


def create_cmd(key: str | None = "P123-REC-0042", **extra: Any) -> CreateRecord:
    return CreateRecord(
        actor=AGENT,
        source="mcp:triage",
        scope=P1,
        record_type="core.Record",
        title="Weld NCR",
        key=key,
        **extra,
    )


def psets_cmd(record_id: str, version: int, manufacturer: str = "Acme") -> SetPsetValues:
    return SetPsetValues(
        actor=AGENT,
        source="mcp:triage",
        scope=P1,
        stream_id=record_id,
        expected_version=version,
        pset="valve_data",
        layer="standard",
        values={"manufacturer": manufacturer},
    )


# --- propose -----------------------------------------------------------------------------------


def test_a_proposal_is_recorded_pending_and_changes_nothing(world: World) -> None:
    view = world.submit(create_cmd(), "create_record", summary="Create the weld NCR")
    assert (view.status, view.tool, view.agent, view.scope) == (
        "pending",
        "create_record",
        AGENT,
        P1,
    )
    assert view.command_type == "CreateRecord" and view.summary == "Create the weld NCR"
    assert view.command["title"] == "Weld NCR" and view.command["source"] == "mcp:triage"
    assert world.record("P123-REC-0042") is None
    (created,) = world.events(view.proposal_id)
    assert (created.event_type, created.actor, created.source) == (
        "Proposal.Created",
        AGENT,
        "mcp:triage",
    )
    assert created.stream_type == "core.Proposal" and created.scope == P1
    assert [p.proposal_id for p in world.pending()] == [view.proposal_id]


def test_what_the_handler_would_refuse_is_refused_at_proposal_time(world: World) -> None:
    rid = world.create("P123-REC-0001")
    with pytest.raises(RecordNotFoundError):
        world.submit(psets_cmd("01NOSUCHRECORD", 1), "update_psets")
    with pytest.raises(ConcurrencyError):
        world.submit(psets_cmd(rid, 9), "update_psets")
    other = create_cmd("P123-REC-0001")
    with pytest.raises(Exception, match="already used"):
        world.submit(other, "create_record")
    link = AddLink(actor=AGENT, source="mcp:triage", scope=P1, from_id=rid, to_id="01NOSUCH")
    with pytest.raises(RecordNotFoundError):
        world.submit(link, "link_records")
    assert world.pending() == []


def test_a_refused_proposal_leaves_no_event_and_no_number_behind(world: World) -> None:
    head = world.head()
    with pytest.raises(RecordNotFoundError):
        world.submit(psets_cmd("01NOSUCHRECORD", 1), "update_psets")
    assert world.head() == head
    # the dry run of a numbered create is rolled back too: the first real record gets 0001
    view = world.submit(create_cmd(key=None), "create_record")
    assert world.head() == head + 1  # one event: Proposal.Created, not a Numbering.Allocated
    proposals.accept_or_fail(world.factory, proposal_id=view.proposal_id, by=ALICE)
    assert world.record("P123-REC-0001") is not None


def test_the_tool_must_match_the_command_and_the_summary_is_checked(world: World) -> None:
    with pytest.raises(InvalidProposalError, match="does not propose"):
        world.submit(create_cmd(), "post_feed")
    with pytest.raises(InvalidProposalError, match="carries a SetPsetValues"):
        world.submit(create_cmd(), "update_psets")
    with pytest.raises(InvalidProposalError, match="summary"):
        world.submit(create_cmd(), "create_record", summary="   ")
    with pytest.raises(InvalidProposalError, match="summary"):
        world.submit(create_cmd(), "create_record", summary="x" * 301)
    with pytest.raises(InvalidProposalError, match="agent:"):
        world.submit(create_cmd(), "create_record", agent="svc:thing")
    assert world.pending() == []


# --- accept ------------------------------------------------------------------------------------


def test_accepting_runs_the_command_as_the_person_with_the_agent_as_source(world: World) -> None:
    proposal = world.submit(create_cmd(), "create_record")
    view = proposals.accept_or_fail(
        world.factory, proposal_id=proposal.proposal_id, by=ALICE, source="cli"
    )
    assert (view.status, view.decided_by) == ("accepted", ALICE)
    record = world.record("P123-REC-0042")
    assert record is not None and view.result_stream_id == record["id"]
    created = world.events(proposal.proposal_id)[0]
    (made,) = world.events(record["id"])
    assert (made.actor, made.source) == (ALICE, "mcp:triage")
    assert made.causation_id == created.event_id and made.correlation_id == proposal.proposal_id
    accepted = world.events(proposal.proposal_id)[1]
    assert accepted.event_type == "Proposal.Accepted" and accepted.actor == ALICE
    assert accepted.source == "cli" and accepted.causation_id == created.event_id
    assert accepted.payload["result_stream_id"] == record["id"]
    assert world.pending() == []


def test_each_proposable_command_type_is_accepted(world: World) -> None:
    a, b = world.create("P123-REC-0001"), world.create("P123-REC-0002")
    steps = [
        ("update_psets", psets_cmd(a, 1)),
        ("link_records", AddLink(actor=AGENT, source="x", scope=P1, from_id=a, to_id=b)),
    ]
    for tool, command in steps:
        proposal = world.submit(command, tool)
        done = proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)
        assert done.status == "accepted", tool
    with open_uow(world.db, readonly=True) as uow:
        linked = uow.conn().execute(text("SELECT COUNT(*) FROM cur_links")).scalar_one()
    assert linked == 1
    assert {
        e.source for e in world.all_events() if e.event_type in ("Pset.ValuesSet", "Link.Added")
    } == {"mcp:triage"}


def test_a_stale_proposal_fails_and_changes_nothing(world: World) -> None:
    rid = world.create("P123-REC-0001")
    proposal = world.submit(psets_cmd(rid, 1), "update_psets")
    with open_uow(world.db) as uow:  # someone edits the record first
        from tl_core.services.commands import UpdateRecord
        from tl_core.services.records import handle_update_record

        handle_update_record(
            uow,
            UpdateRecord(
                actor=ALICE,
                source="t",
                scope=P1,
                stream_id=rid,
                expected_version=1,
                changes={"title": "New"},
            ),
        )
    head = world.head()
    view = proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)
    assert view.status == "failed" and view.decided_by == ALICE
    assert view.reason is not None and view.reason.startswith("ConcurrencyError")
    assert [e.event_type for e in world.all_events()[head:]] == ["Proposal.Failed"]
    assert not any(e.event_type == "Pset.ValuesSet" for e in world.all_events())
    with pytest.raises(ProposalNotPendingError):
        proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)


def test_a_command_refused_on_accept_leaves_only_the_failed_event(world: World) -> None:
    proposal = world.submit(create_cmd("P123-REC-0042"), "create_record")  # free when proposed
    world.create("P123-REC-0042")  # taken before a person looks at the queue
    head = world.head()
    done = proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)
    assert done.status == "failed" and (done.reason or "").startswith("DuplicateKeyError")
    assert [e.event_type for e in world.all_events()[head:]] == ["Proposal.Failed"]


def test_only_a_pending_proposal_can_be_decided_once(world: World) -> None:
    proposal = world.submit(create_cmd(), "create_record")
    proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)
    with pytest.raises(ProposalNotPendingError):
        proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by="user:bob")
    with open_uow(world.db) as uow, pytest.raises(ProposalNotPendingError):
        proposals.reject_proposal(uow, proposal_id=proposal.proposal_id, by=ALICE, reason="late")
    with pytest.raises(ProposalNotFoundError):
        proposals.accept_or_fail(world.factory, proposal_id="01NOSUCH", by=ALICE)


def test_an_agent_cannot_decide(world: World) -> None:
    proposal = world.submit(create_cmd(), "create_record")
    for decider in (AGENT, "svc:worker", "company"):
        with pytest.raises(ProposalDeciderError):
            proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=decider)
        with open_uow(world.db) as uow, pytest.raises(ProposalDeciderError):
            proposals.reject_proposal(
                uow, proposal_id=proposal.proposal_id, by=decider, reason="no"
            )
    assert world.get(proposal.proposal_id).status == "pending"
    assert world.record("P123-REC-0042") is None


# --- reject ------------------------------------------------------------------------------------


def test_rejecting_records_the_reason_and_never_runs_the_command(world: World) -> None:
    proposal = world.submit(create_cmd(), "create_record")
    with open_uow(world.db) as uow, pytest.raises(InvalidProposalError, match="reason"):
        proposals.reject_proposal(uow, proposal_id=proposal.proposal_id, by=ALICE, reason=" ")
    with open_uow(world.db) as uow:
        view = proposals.reject_proposal(
            uow, proposal_id=proposal.proposal_id, by=ALICE, reason="Duplicate of NCR-0040"
        )
    assert (view.status, view.reason, view.decided_by) == (
        "rejected",
        "Duplicate of NCR-0040",
        ALICE,
    )
    assert world.record("P123-REC-0042") is None
    assert world.pending() == []
    listed = []
    with open_uow(world.db, readonly=True) as uow:
        listed = proposals.list_proposals(uow.conn(), P1, status=None)
    assert [p.status for p in listed] == ["rejected"]


# --- workflow roles ----------------------------------------------------------------------------


def test_a_proposal_cannot_carry_roles_and_the_accepting_person_supplies_them(
    world: World,
) -> None:
    rid = world.create("P123-REC-0001")
    claimed = TransitionWorkflow(
        actor=AGENT, source="x", scope=P1, stream_id=rid, expected_version=1,
        transition="finish", actor_roles=["manager"],
    )  # fmt: skip
    with pytest.raises(InvalidProposalError, match="roles"):
        world.submit(claimed, "transition_workflow")
    plain = claimed.model_copy(update={"actor_roles": []})
    proposal = world.submit(plain, "transition_workflow")  # a role guard alone does not stop it
    without = proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)
    assert without.status == "failed" and (without.reason or "").startswith("GuardFailedError")
    again = world.submit(plain, "transition_workflow")
    done = proposals.accept_or_fail(
        world.factory, proposal_id=again.proposal_id, by=ALICE, roles=["manager"]
    )
    assert done.status == "accepted"
    record = world.record("P123-REC-0001")
    assert record is not None and record["status"] == "Done"


def test_other_guards_are_checked_when_the_agent_proposes(world: World) -> None:
    rid = world.create("P123-REC-0001")
    submit = TransitionWorkflow(
        actor=AGENT, source="x", scope=P1, stream_id=rid, expected_version=1, transition="submit"
    )
    with pytest.raises(GuardFailedError):
        world.submit(submit, "transition_workflow")


# --- budget ------------------------------------------------------------------------------------


def test_an_agent_has_a_daily_budget_per_utc_day(world: World) -> None:
    day1 = datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
    day2 = datetime(2026, 10, 10, 1, 0, tzinfo=UTC)
    for n in (1, 2):
        world.submit(create_cmd(f"P123-REC-{n:04d}"), "create_record", budget=2, now=day1)
    with pytest.raises(BudgetExceededError, match="agent:triage"):
        world.submit(create_cmd("P123-REC-0003"), "create_record", budget=2, now=day1)
    other = world.submit(
        create_cmd("P123-REC-0003"), "create_record", budget=2, now=day1, agent="agent:other"
    )
    assert other.agent == "agent:other"
    world.submit(create_cmd("P123-REC-0004"), "create_record", budget=2, now=day2)
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.proposals_today(uow.conn(), AGENT, now=day1) == 2
        assert proposals.proposals_today(uow.conn(), AGENT, now=day2) == 1


def test_the_budget_comes_from_the_environment_and_defaults_to_the_contract(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(proposals.BUDGET_ENV, raising=False)
    assert proposals.daily_budget() == 500
    monkeypatch.setenv(proposals.BUDGET_ENV, "1")
    assert proposals.daily_budget() == 1
    world.submit(create_cmd("P123-REC-0001"), "create_record")
    with pytest.raises(BudgetExceededError):
        world.submit(create_cmd("P123-REC-0002"), "create_record")
    monkeypatch.setenv(proposals.BUDGET_ENV, "-3")
    assert proposals.daily_budget() == 500  # not a number we accept: the default
    monkeypatch.setenv(proposals.BUDGET_ENV, "0")
    with pytest.raises(BudgetExceededError):
        world.submit(create_cmd("P123-REC-0003"), "create_record", agent="agent:fresh")


# --- the projection ----------------------------------------------------------------------------


def test_a_rebuild_gives_the_same_rows_as_the_live_run(world: World) -> None:
    rid = world.create("P123-REC-0001")
    a = world.submit(create_cmd(), "create_record")
    b = world.submit(psets_cmd(rid, 1), "update_psets")
    c = world.submit(create_cmd("P123-REC-0043"), "create_record")
    proposals.accept_or_fail(world.factory, proposal_id=a.proposal_id, by=ALICE)
    with open_uow(world.db) as uow:
        proposals.reject_proposal(uow, proposal_id=b.proposal_id, by=ALICE, reason="no")

    def rows() -> list[dict[str, Any]]:
        with open_uow(world.db, readonly=True) as uow:
            found = uow.conn().execute(text("SELECT * FROM cur_proposals ORDER BY seq"))
            return [dict(r) for r in found.mappings().all()]

    live = rows()
    rebuild_projections(world.db, types=["proposals"])
    assert rows() == live
    assert [r["status"] for r in live] == ["accepted", "rejected", "pending"]
    assert c.proposal_id == live[2]["proposal_id"]


def test_proposal_events_do_not_split_or_make_feed_cards(world: World) -> None:
    ids = [world.submit(create_cmd(f"P123-REC-{n:04d}"), "create_record") for n in (1, 2, 3)]
    for view in ids:
        proposals.accept_or_fail(world.factory, proposal_id=view.proposal_id, by=ALICE)
    with open_uow(world.db, readonly=True) as uow:
        cards = (
            uow.conn()
            .execute(
                text("SELECT summary, event_count FROM cur_feed_items WHERE item_type = 'card'")
            )
            .all()
        )
    assert [(c.summary, c.event_count) for c in cards if "alice" in c.summary] == [
        ("alice created 3 records", 3)
    ]


def test_the_proposal_view_uses_the_frozen_contract_fields() -> None:
    assert list(ProposalView.model_fields) == [
        "proposal_id", "scope", "tool", "agent", "command_type", "command", "summary",
        "status", "decided_by", "reason", "result_stream_id", "seq",
    ]  # fmt: skip


def test_propose_itself_enforces_the_budget_inside_its_unit_of_work(world: World) -> None:
    for n in (1, 2):
        with open_uow(world.db) as uow:
            proposals.propose(
                uow,
                tool="create_record",
                agent=AGENT,
                command=create_cmd(f"P123-REC-{n:04d}"),
                summary="s",
                budget=2,
            )
    with open_uow(world.db) as uow, pytest.raises(BudgetExceededError):
        proposals.propose(
            uow, tool="create_record", agent=AGENT, command=create_cmd(), summary="s", budget=2
        )


def test_a_transient_database_failure_is_not_recorded_as_a_failed_proposal(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = world.submit(create_cmd(), "create_record")
    model, _ = proposals.COMMANDS["CreateRecord"]

    def busy(uow: Any, command: Any) -> Any:
        raise LockTimeoutError("database is locked")

    monkeypatch.setitem(proposals.COMMANDS, "CreateRecord", (model, busy))
    with pytest.raises(LockTimeoutError):
        proposals.accept_or_fail(world.factory, proposal_id=proposal.proposal_id, by=ALICE)
    assert world.get(proposal.proposal_id).status == "pending"  # retry later
