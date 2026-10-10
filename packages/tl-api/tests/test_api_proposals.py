"""Review-queue routes: list, show, accept (also when it fails), reject, and who may decide."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from harness import ALICE, BOB, SCOPE, Harness
from tl_api.tokens import add_token
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
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


def as_agent(h: Harness) -> TestClient:
    token = add_token(h.settings.tokens_path, AGENT)
    client = TestClient(h.app, raise_server_exceptions=False)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_the_queue_lists_pending_proposals_oldest_first_with_their_command(
    harness: Harness,
) -> None:
    first, second = propose_create(harness), propose_create(harness, "P123-REC-0043")
    propose_create(harness, "P999-REC-0001", scope="project:P999")
    listed = harness.client.get("/proposals", params={"scope": SCOPE})
    assert listed.status_code == 200
    rows = listed.json()
    assert [r["proposal_id"] for r in rows] == [first.proposal_id, second.proposal_id]
    assert rows[0]["status"] == "pending" and rows[0]["agent"] == AGENT
    assert rows[0]["command"]["title"] == "Weld NCR" and rows[0]["summary"] == "Create NCR"
    one = harness.client.get(f"/proposals/{first.proposal_id}")
    assert one.status_code == 200 and one.json()["command_type"] == "CreateRecord"
    foreign = harness.client.get(f"/proposals/{first.proposal_id}", params={"scope": "company"})
    assert foreign.status_code == 404 and foreign.json()["error"] == "proposal_not_found"
    assert harness.client.get("/proposals/01NOSUCH").status_code == 404


def test_accepting_creates_the_record_as_the_caller_from_the_agent(harness: Harness) -> None:
    proposal = propose_create(harness)
    done = harness.client.post(f"/proposals/{proposal.proposal_id}/accept")
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["status"], body["decided_by"]) == ("accepted", ALICE)
    record = harness.client.get("/records/lookup", params={"scope": SCOPE, "key": "P123-REC-0042"})
    assert record.json()["id"] == body["result_stream_id"]
    history = harness.client.get(f"/records/{body['result_stream_id']}/history").json()
    assert [(e["actor"], e["source"]) for e in history] == [(ALICE, "mcp:triage")]
    again = harness.client.post(f"/proposals/{proposal.proposal_id}/accept")
    assert again.status_code == 409 and again.json()["error"] == "proposal_not_pending"
    assert harness.client.get("/proposals", params={"scope": SCOPE}).json() == []
    everything = harness.client.get("/proposals", params={"scope": SCOPE, "all": True})
    assert [r["status"] for r in everything.json()] == ["accepted"]
    only = harness.client.get("/proposals", params={"scope": SCOPE, "status": "accepted"})
    assert len(only.json()) == 1


def test_a_proposal_the_command_can_no_longer_satisfy_is_answered_failed(
    harness: Harness,
) -> None:
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
    proposal = proposals.submit(
        harness.backend, tool="update_psets", agent=AGENT, command=command, summary="Set maker"
    )
    changed = harness.client.post(
        "/commands/UpdateRecord",
        json={"scope": SCOPE, "stream_id": rid, "expected_version": 1, "changes": {"title": "X"}},
    )
    assert changed.status_code == 200
    done = harness.client.post(f"/proposals/{proposal.proposal_id}/accept")
    assert done.status_code == 200
    assert done.json()["status"] == "failed" and done.json()["reason"].startswith(
        "ConcurrencyError"
    )
    history = harness.client.get(f"/records/{rid}/history").json()
    assert [e["event_type"] for e in history] == ["Record.Created", "Record.Updated"]


def test_rejecting_needs_a_reason_and_runs_nothing(harness: Harness) -> None:
    proposal = propose_create(harness)
    path = f"/proposals/{proposal.proposal_id}/reject"
    assert harness.client.post(path, json={}).status_code == 422
    assert harness.client.post(path, json={"reason": ""}).status_code == 422
    assert harness.client.post(path, json={"reason": "x" * 1001}).status_code == 422
    assert harness.client.post(path, json={"reason": "no", "by": "user:x"}).status_code == 422
    done = harness.client.post(path, json={"reason": "Duplicate of NCR-0040"})
    assert done.status_code == 200
    assert (done.json()["status"], done.json()["reason"]) == ("rejected", "Duplicate of NCR-0040")
    lookup = harness.client.get("/records/lookup", params={"scope": SCOPE, "key": "P123-REC-0042"})
    assert lookup.status_code == 404
    late = harness.client.post(path, json={"reason": "again"})
    assert late.status_code == 409


def test_an_agent_token_cannot_accept_or_reject(harness: Harness) -> None:
    proposal = propose_create(harness)
    agent = as_agent(harness)
    accept = agent.post(f"/proposals/{proposal.proposal_id}/accept")
    assert accept.status_code == 403 and accept.json()["error"] == "proposal_decider"
    reject = agent.post(f"/proposals/{proposal.proposal_id}/reject", json={"reason": "mine"})
    assert reject.status_code == 403 and reject.json()["error"] == "proposal_decider"
    assert agent.get("/proposals", params={"scope": SCOPE}).status_code == 200  # reading is open
    assert harness.client.get(f"/proposals/{proposal.proposal_id}").json()["status"] == "pending"


def test_roles_travel_in_the_accept_body_and_are_bounded(harness: Harness) -> None:
    proposal = propose_create(harness)
    path = f"/proposals/{proposal.proposal_id}/accept"
    assert harness.client.post(path, json={"roles": ["a"] * 21}).status_code == 422
    assert harness.client.post(path, json={"roles": ["x" * 65]}).status_code == 422
    assert harness.client.post(path, json={"actor": BOB}).status_code == 422
    assert harness.client.post(path, json={"roles": ["manager"]}).json()["status"] == "accepted"


def test_the_queue_needs_a_token(harness: Harness) -> None:
    anon = harness.client_for(None)
    proposal = propose_create(harness)
    assert anon.get("/proposals", params={"scope": SCOPE}).status_code == 401
    assert anon.get(f"/proposals/{proposal.proposal_id}").status_code == 401
    assert anon.post(f"/proposals/{proposal.proposal_id}/accept").status_code == 401
    bad: dict[str, Any] = {"scope": SCOPE, "limit": 0}
    assert harness.client.get("/proposals", params=bad).status_code == 422
    assert (
        harness.client.get("/proposals", params={"scope": SCOPE, "status": "x"}).status_code == 422
    )
