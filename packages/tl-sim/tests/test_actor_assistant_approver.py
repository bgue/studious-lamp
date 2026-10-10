"""The assistant (an agent that proposes) and the approver (a person who decides), on FakeWorld."""

from __future__ import annotations

from typing import Any

import pytest
from tl_sim import groundtruth as gt
from tl_sim.actors.approver import Approver
from tl_sim.actors.assistant import Assistant
from tl_sim.actors.base import Recorder
from tl_sim.client import ProposeUnavailableError
from tl_sim.scenario import ApproverParams, AssistantParams, CountRange
from tl_sim.testing import FakeWorld, make_context, seed_lines
from tl_sim.types import GroundTruth

ASSISTANT = "agent:sim-assistant"
APPROVER = "user:sim-approver"


def world_with_valves_and_docs(valves: int = 2, docs: int = 2) -> FakeWorld:
    world = FakeWorld("r1", "project:sim-r1")
    seed_lines(world, 1)
    maker = Recorder(make_context(world, "user:sim-crew"), "user:sim-crew")
    for n in range(1, valves + 1):
        maker.create(f"Valve V{n:03d} 4in on 6-CS-1001")
    for n in range(1, docs + 1):
        maker.create(f"Doc {n:03d} Piping isometric Rev A")
    return world


def assist(world: FakeWorld, *, seed: int = 1, **params: Any) -> list[GroundTruth]:
    actor = Assistant(AssistantParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, propose=True))


def approve(world: FakeWorld, *, seed: int = 1, **params: Any) -> list[GroundTruth]:
    actor = Approver(ApproverParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, propose=True))


def test_identities_follow_the_decision_agent_proposes_person_decides() -> None:
    assert Assistant(AssistantParams()).identity == ASSISTANT
    assert Assistant(AssistantParams()).name == "assistant"
    assert Approver(ApproverParams()).identity == APPROVER


def test_the_assistant_proposes_a_valve_to_document_link_and_changes_nothing() -> None:
    world = world_with_valves_and_docs()
    before = world.records()
    truth = assist(world, proposals_per_day=1)
    assert [(t.intent, t.actor, t.expect) for t in truth] == [
        (gt.PROPOSAL_CREATED, ASSISTANT, {"tool": "link_records", "agent": ASSISTANT})
    ]
    assert world.records() == before and world.link_rows == []
    (proposal,) = world.proposal_rows
    command = proposal["command"]
    titles = {r["id"]: r["title"] for r in world.records()}
    assert titles[command["from_id"]].startswith("Valve ")
    assert titles[command["to_id"]].startswith("Doc ")
    assert command["relation"] == "references"
    assert proposal["status"] == "pending"


def test_with_no_count_no_valve_or_no_document_it_proposes_nothing() -> None:
    assert assist(world_with_valves_and_docs(), proposals_per_day=0) == []
    assert assist(world_with_valves_and_docs(valves=0), proposals_per_day=1) == []
    assert assist(world_with_valves_and_docs(docs=0), proposals_per_day=1) == []


def test_a_proposal_the_server_refuses_leaves_no_ground_truth() -> None:
    world = world_with_valves_and_docs(valves=1, docs=1)
    first = assist(world, proposals_per_day=1)
    person = Recorder(make_context(world, APPROVER, propose=True), APPROVER)
    person.decide(person.pending()[0], accept=True)  # the link now exists
    again = assist(world, proposals_per_day=1)  # the only pair: refused as a duplicate
    assert len(first) == 1 and again == []
    assert len(world.proposal_rows) == 1


def test_without_an_mcp_caller_the_assistant_cannot_propose() -> None:
    world = world_with_valves_and_docs()
    actor = Assistant(AssistantParams(proposals_per_day=1))
    with pytest.raises(ProposeUnavailableError):
        actor.step(make_context(world, actor.identity))


def test_the_assistant_is_deterministic_per_seed() -> None:
    first, second = world_with_valves_and_docs(4, 4), world_with_valves_and_docs(4, 4)
    params = {"proposals_per_day": CountRange(min=2, max=2)}
    a, b = assist(first, seed=5, **params), assist(second, seed=5, **params)
    assert [gt.to_line(t) for t in a] == [gt.to_line(t) for t in b]
    assert first.proposal_rows == second.proposal_rows


def test_the_approver_accepts_everything_at_a_rate_of_one_and_the_links_exist() -> None:
    world = world_with_valves_and_docs(3, 3)
    assist(world, proposals_per_day=CountRange(min=2, max=2))
    truth = approve(world, accept_rate=1.0)
    assert [t.intent for t in truth] == [gt.PROPOSAL_ACCEPTED] * 2
    assert all(t.actor == APPROVER for t in truth)
    for t in truth:
        assert set(t.expect) == {"tool", "agent", "from", "to", "relation"}
        assert t.expect["relation"] == "references"
    assert len(world.link_rows) == 2
    assert {p["status"] for p in world.proposal_rows} == {"accepted"}
    assert {p["decided_by"] for p in world.proposal_rows} == {APPROVER}
    assert approve(world) == []  # the queue is empty now


def test_the_approver_rejects_everything_at_a_rate_of_zero_with_a_reason() -> None:
    world = world_with_valves_and_docs(3, 3)
    assist(world, proposals_per_day=CountRange(min=2, max=2))
    truth = approve(world, accept_rate=0.0)
    assert [t.intent for t in truth] == [gt.PROPOSAL_REJECTED] * 2
    assert all(t.expect["reason"] == "Not needed" for t in truth)
    assert world.link_rows == []
    assert {p["status"] for p in world.proposal_rows} == {"rejected"}


def test_the_approver_works_the_queue_oldest_first_and_draws_once_per_proposal() -> None:
    world = world_with_valves_and_docs(4, 4)
    assist(world, proposals_per_day=CountRange(min=4, max=4))
    first = [p["proposal_id"] for p in world.proposal_rows]
    approve(world, accept_rate=0.5, seed=3)
    decided = [p["status"] for p in world.proposal_rows]
    assert decided.count("accepted") + decided.count("rejected") == len(first)
    again = world_with_valves_and_docs(4, 4)
    assist(again, proposals_per_day=CountRange(min=4, max=4))
    approve(again, accept_rate=0.5, seed=3)
    assert [p["status"] for p in again.proposal_rows] == decided  # same seed, same decisions


def test_a_scenario_turns_them_on_and_the_default_leaves_them_off() -> None:
    from tl_sim.scenario import ActorsConfig

    assert ActorsConfig().enabled() == ["document_controller", "planner", "crew"]
    on = ActorsConfig(assistant=AssistantParams(), approver=ApproverParams())
    assert on.enabled() == ["document_controller", "planner", "crew", "assistant", "approver"]
