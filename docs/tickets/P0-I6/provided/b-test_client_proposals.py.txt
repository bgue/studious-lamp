"""ApiClient review-queue methods against a real app (P0-I6-T21). Provided; do not edit."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import ALICE, SCOPE, Harness
from tl_api.client import ApiClient
from tl_api.tokens import add_token
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import (
    ProposalDeciderError,
    ProposalNotFoundError,
    ProposalNotPendingError,
)
from tl_core.services.psets import SetPsetValues

AGENT = "agent:triage"


def propose_create(h: Harness, key: str = "P123-REC-0042", scope: str = SCOPE) -> ProposalView:
    command = CreateRecord(
        actor=AGENT,
        source="mcp:triage",
        scope=scope,
        record_type="core.Record",
        title="Weld NCR",
        key=key,
    )
    return proposals.submit(
        h.backend, tool="create_record", agent=AGENT, command=command, summary="Create NCR"
    )


def test_list_returns_the_pending_queue_oldest_first_as_proposal_views(harness: Harness) -> None:
    first, second = propose_create(harness), propose_create(harness, "P123-REC-0043")
    propose_create(harness, "P999-REC-0001", scope="project:P999")
    listed = harness.api().list_proposals(SCOPE)
    assert [p.proposal_id for p in listed] == [first.proposal_id, second.proposal_id]
    assert all(isinstance(p, ProposalView) for p in listed)
    assert listed[0] == first  # the whole view survives the round trip
    assert listed[0].command["title"] == "Weld NCR"


def test_list_filters_by_status_agent_and_limit(harness: Harness) -> None:
    api = harness.api()
    first, second = propose_create(harness), propose_create(harness, "P123-REC-0043")
    api.reject_proposal(first.proposal_id, "no")
    assert [p.proposal_id for p in api.list_proposals(SCOPE)] == [second.proposal_id]
    assert [p.status for p in api.list_proposals(SCOPE, status="rejected")] == ["rejected"]
    assert [p.status for p in api.list_proposals(SCOPE, status=None)] == ["rejected", "pending"]
    assert api.list_proposals(SCOPE, status=None, agent="agent:other") == []
    assert len(api.list_proposals(SCOPE, status=None, limit=1)) == 1


def test_get_returns_one_and_raises_the_embedded_error_for_an_unknown_one(
    harness: Harness,
) -> None:
    api = harness.api()
    made = propose_create(harness)
    assert api.get_proposal(made.proposal_id, SCOPE) == made
    with pytest.raises(ProposalNotFoundError):
        api.get_proposal(made.proposal_id, "company")
    with pytest.raises(ProposalNotFoundError):
        api.get_proposal("01NOSUCHPROPOSAL", SCOPE)


def test_accept_runs_the_command_as_the_token_actor(harness: Harness) -> None:
    made = propose_create(harness)
    done = harness.api().accept_proposal(made.proposal_id)
    assert (done.status, done.decided_by) == ("accepted", ALICE)
    record = harness.api().get_record(SCOPE, "P123-REC-0042")
    assert record is not None and record["id"] == done.result_stream_id
    history = harness.api().history(done.result_stream_id or "")
    assert [(e.actor, e.source) for e in history] == [(ALICE, "mcp:triage")]
    with pytest.raises(ProposalNotPendingError):
        harness.api().accept_proposal(made.proposal_id)


def test_a_command_that_cannot_be_applied_comes_back_failed_not_raised(harness: Harness) -> None:
    api = harness.api()
    rid = harness.create_record("P123-REC-0001").stream_id
    command = SetPsetValues(
        actor=AGENT,
        source="mcp:triage",
        scope=SCOPE,
        stream_id=rid,
        expected_version=1,
        pset="valve_data",
        layer="standard",
        values={"manufacturer": "Acme"},
    )
    made = proposals.submit(
        harness.backend, tool="update_psets", agent=AGENT, command=command, summary="Set maker"
    )
    harness.client.post(
        "/commands/UpdateRecord",
        json={"scope": SCOPE, "stream_id": rid, "expected_version": 1, "changes": {"title": "X"}},
    )
    done = api.accept_proposal(made.proposal_id)
    assert done.status == "failed" and (done.reason or "").startswith("ConcurrencyError")
    assert done.decided_by == ALICE and done.result_stream_id is None


def test_accept_sends_the_roles(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    real = proposals.accept_or_fail

    def spy(factory: Any, **kwargs: Any) -> ProposalView:
        seen.append(list(kwargs["roles"]))
        return real(factory, **kwargs)

    monkeypatch.setattr(proposals, "accept_or_fail", spy)
    api = harness.api()
    first, second = propose_create(harness), propose_create(harness, "P123-REC-0043")
    assert api.accept_proposal(first.proposal_id, roles=["manager", "admin"]).status == "accepted"
    assert api.accept_proposal(second.proposal_id).status == "accepted"
    assert seen == [["manager", "admin"], []]


def test_reject_records_the_reason(harness: Harness) -> None:
    api = harness.api()
    made = propose_create(harness)
    done = api.reject_proposal(made.proposal_id, "Duplicate of NCR-0040")
    assert done.status == "rejected" and done.decided_by == ALICE
    assert done.reason == "Duplicate of NCR-0040"
    with pytest.raises(ProposalNotPendingError):
        api.reject_proposal(made.proposal_id, "again")
    with pytest.raises(ProposalNotFoundError):
        api.reject_proposal("01NOSUCH", "x")


def test_an_agent_token_cannot_decide(harness: Harness) -> None:
    made = propose_create(harness)
    token = add_token(harness.settings.tokens_path, AGENT)
    agent = ApiClient("http://testserver", token, http=TestClient(harness.app))
    with pytest.raises(ProposalDeciderError):
        agent.accept_proposal(made.proposal_id)
    with pytest.raises(ProposalDeciderError):
        agent.reject_proposal(made.proposal_id, "mine")
    assert [p.status for p in agent.list_proposals(SCOPE)] == ["pending"]  # reading is open


def test_ids_cannot_change_the_path(harness: Harness) -> None:
    api = harness.api()
    for bad in (".", ".."):
        with pytest.raises(ValueError):
            api.get_proposal(bad, SCOPE)
        with pytest.raises(ValueError):
            api.accept_proposal(bad)
