"""An agent proposal keeps its intent in the Created event's column, and accepting runs with it."""

from __future__ import annotations

import json
from typing import Any

import pytest
from harness import ALICE, SCOPE, Harness
from sqlalchemy import text
from tl_core.intent import Intent, IntentInvalid, IntentReferenceUnknown
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord

AGENT = "agent:triage"


def propose(h: Harness, key: str, intent: dict[str, Any] | None) -> ProposalView:
    command = CreateRecord(
        actor=AGENT,
        source="mcp:triage",
        scope=SCOPE,
        record_type="core.Record",
        title="Weld NCR",
        key=key,
        intent=Intent.model_validate(intent) if intent is not None else None,
    )
    return proposals.submit(
        h.backend, tool="create_record", agent=AGENT, command=command, summary="Create NCR"
    )


def events_of(h: Harness, stream_id: str) -> list[dict[str, Any]]:
    with h.backend(True) as uow:
        rows = (
            uow.conn()
            .execute(
                text(
                    "SELECT event_type, payload, intent, actor, source FROM events "
                    "WHERE stream_id = :s ORDER BY stream_version"
                ),
                {"s": stream_id},
            )
            .mappings()
            .all()
        )
    return [{**r, "payload": json.loads(r["payload"])} for r in rows]


INTENT = {
    "why": "The weld failed inspection",
    "next": [{"command": "UpdateRecord", "target": "R-1"}],
    "toward": {"target": "R-1", "condition": "re-inspected"},
}


def test_the_intent_is_in_the_column_and_not_in_the_payload(harness: Harness) -> None:
    rid = harness.create_record("R-1").stream_id
    proposal = propose(harness, "NCR-1", INTENT)
    (created,) = events_of(harness, proposal.proposal_id)
    assert created["event_type"] == "Proposal.Created"
    assert "intent" not in created["payload"]["command"]
    stored = json.loads(created["intent"])
    assert stored["why"] == INTENT["why"]
    assert stored["next"] == [{"command": "UpdateRecord", "target": rid}]  # a key became an id
    assert stored["toward"] == {"target": rid, "condition": "re-inspected"}


def test_no_intent_leaves_the_column_null_and_the_payload_without_the_key(
    harness: Harness,
) -> None:
    proposal = propose(harness, "NCR-1", None)
    (created,) = events_of(harness, proposal.proposal_id)
    assert created["intent"] is None and "intent" not in created["payload"]["command"]


def test_an_invalid_or_unknown_intent_refuses_the_proposal(harness: Harness) -> None:
    with pytest.raises(IntentInvalid):
        propose(harness, "NCR-1", {"why": "x" * 501})
    with pytest.raises(IntentReferenceUnknown):
        propose(harness, "NCR-1", {"toward": {"target": "NOPE", "condition": "x"}})
    assert harness.client.get("/proposals", params={"scope": SCOPE}).json() == []


def test_a_listed_proposal_shows_the_intent(harness: Harness) -> None:
    rid = harness.create_record("R-1").stream_id
    propose(harness, "NCR-1", INTENT)
    listed = harness.client.get("/proposals", params={"scope": SCOPE}).json()
    assert listed[0]["intent"]["why"] == INTENT["why"]
    assert listed[0]["intent"]["toward"]["target"] == rid
    assert "intent" not in listed[0]["command"]


def test_accepting_runs_the_command_with_the_intent_as_the_person_naming_the_agent(
    harness: Harness,
) -> None:
    rid = harness.create_record("R-1").stream_id
    proposal = propose(harness, "NCR-1", INTENT)
    (created,) = events_of(harness, proposal.proposal_id)
    done = harness.client.post(f"/proposals/{proposal.proposal_id}/accept")
    assert done.status_code == 200, done.text
    made = events_of(harness, done.json()["result_stream_id"])
    assert len(made) == 1
    assert made[0]["intent"] == created["intent"]  # the same stored text
    assert (made[0]["actor"], made[0]["source"]) == (ALICE, "mcp:triage")
    assert json.loads(made[0]["intent"])["toward"]["target"] == rid
    decided = events_of(harness, proposal.proposal_id)
    assert [e["event_type"] for e in decided] == ["Proposal.Created", "Proposal.Accepted"]
    assert decided[1]["intent"] is None  # the decision itself carries no intent


def test_a_proposal_without_intent_accepts_without_one(harness: Harness) -> None:
    proposal = propose(harness, "NCR-1", None)
    done = harness.client.post(f"/proposals/{proposal.proposal_id}/accept")
    assert events_of(harness, done.json()["result_stream_id"])[0]["intent"] is None
