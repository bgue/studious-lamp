"""Accepting a proposal over HTTP needs the access its command needs (ADR-0014 section 8).

An agent proposes the publication of a derived document; a user who accepts it is refused with 403
`proposal_access` and the proposal stays pending; an admin (tags) or a document controller
(documents) passes the check. The derived document does not exist here, so a passing accept ends
`failed` with the command's own refusal, which is all this file needs: the access check ran first.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.services import proposals
from tl_mod_documents.derivation.publish import PublishDerivedDocuments, PublishDerivedTags

PASSWORD = "correct horse battery"
SCOPE = "project:P123"
AGENT = "agent:triage"
ROLES = {
    "boss": ["admin"],
    "bob": ["user"],
    "dora": ["user", "document_controller"],
}


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


def client_of(harness: Harness, name: str) -> TestClient:
    _, token = sessions.sign_in(harness.backend, username=name, password=PASSWORD)
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def propose(
    harness: Harness, tool: str, model: type[PublishDerivedTags | PublishDerivedDocuments]
) -> str:
    command = model(
        actor=AGENT, source="mcp:triage", scope=SCOPE, derived_id="NOSUCH", expected_content_rev=1
    )
    with harness.backend(readonly=False) as uow:
        return proposals.propose(
            uow, tool=tool, agent=AGENT, command=command, summary="publish"
        ).proposal_id


@pytest.fixture
def cast(harness: Harness) -> dict[str, TestClient]:
    with harness.backend() as uow:
        for name, roles in ROLES.items():
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=roles,
                password=prepare_password(PASSWORD), by="svc:test",
            )  # fmt: skip
    return {name: client_of(harness, name) for name in ROLES}


def status_of(client: TestClient, proposal_id: str) -> str:
    return str(client.get(f"/proposals/{proposal_id}", params={"scope": SCOPE}).json()["status"])


def test_a_user_cannot_accept_an_agents_publication_into_tags_and_an_admin_can(
    harness: Harness, cast: dict[str, TestClient]
) -> None:
    pid = propose(harness, "propose_import_tags", PublishDerivedTags)
    for who in ("bob", "dora"):
        refused = cast[who].post(f"/proposals/{pid}/accept", params={"scope": SCOPE})
        assert refused.status_code == 403, (who, refused.text)
        assert refused.json()["error"] == "proposal_access"
        assert status_of(cast[who], pid) == "pending"
    passed = cast["boss"].post(f"/proposals/{pid}/accept", params={"scope": SCOPE})
    assert passed.status_code == 200, passed.text
    assert passed.json()["status"] in ("accepted", "failed")


def test_a_publication_into_documents_needs_the_controller_or_the_admin(
    harness: Harness, cast: dict[str, TestClient]
) -> None:
    pid = propose(harness, "propose_import_documents", PublishDerivedDocuments)
    refused = cast["bob"].post(f"/proposals/{pid}/accept", params={"scope": SCOPE})
    assert refused.status_code == 403 and refused.json()["error"] == "proposal_access"
    assert status_of(cast["bob"], pid) == "pending"
    passed = cast["dora"].post(f"/proposals/{pid}/accept", params={"scope": SCOPE})
    assert passed.status_code == 200, passed.text
    other = propose(harness, "propose_import_documents", PublishDerivedDocuments)
    assert (
        cast["boss"].post(f"/proposals/{other}/accept", params={"scope": SCOPE}).status_code == 200
    )


def test_rejecting_needs_no_command_access(harness: Harness, cast: dict[str, TestClient]) -> None:
    pid = propose(harness, "propose_import_tags", PublishDerivedTags)
    done = cast["bob"].post(
        f"/proposals/{pid}/reject", params={"scope": SCOPE}, json={"reason": "no"}
    )
    assert done.status_code == 200, done.text
