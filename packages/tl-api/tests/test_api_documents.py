"""The documents commands over HTTP: who may run them, and the generic routes that must stay shut.

Access is pinned here (ADR-0011): the controlling acts are the admin's, preparing work is open to
any signed-in person, and an agent runs none of them.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.tokens import add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_documents.commands import API_COMMANDS
from tl_mod_documents.testing import DocumentsWorld

PASSWORD = "correct horse battery"
SCOPE = "project:P123"

#: Command to the access it needs. A change here is a decision (ADR-0011), not a refactor.
EXPECTED_ACCESS = {
    "RegisterDocument": "user",
    "UpdateDocument": "user",
    "SetDocumentConfidentiality": "admin",
    "SupersedeDocument": "admin",
    "VoidDocument": "admin",
    "CreateRevision": "user",
    "IssueRevision": "admin",
    "SupersedeRevision": "admin",
    "VoidRevision": "user",
    "AttachRendition": "user",
    "ReplaceSignedRendition": "admin",
    "LinkToDocument": "user",
    "RepinDocumentLink": "user",
    "CreateTransmittal": "user",
    "IssueTransmittal": "admin",
    "RecordTransmittalResponse": "user",
    "CloseTransmittal": "user",
    "VoidTransmittal": "user",
    "OpenReviewCycle": "user",
    "RecordReviewOutcome": "user",
    "CloseReviewCycle": "user",
    "RecordReviewOutcomeOnBehalf": "admin",
    "OverrideReviewOutcome": "admin",
}


class People:
    """An admin (`boss`) and an ordinary person (`bob`), each with a session on the harness."""

    def __init__(self, harness: Harness) -> None:
        with harness.backend() as uow:
            for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
                accounts.create_account(
                    uow, username=name, display_name=name, kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
        self.boss = self._client(harness, "boss")
        self.bob = self._client(harness, "bob")
        self.agent = TestClient(harness.app, raise_server_exceptions=False)
        token = add_token(harness.settings.tokens_path, "agent:triage")
        self.agent.headers.update({"Authorization": f"Bearer {token}"})

    @staticmethod
    def _client(harness: Harness, name: str) -> TestClient:
        _, token = sessions.sign_in(harness.backend, username=name, password=PASSWORD)
        client = harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client


@pytest.fixture
def people(harness: Harness) -> People:
    return People(harness)


@pytest.fixture
def world(harness: Harness) -> DocumentsWorld:
    return DocumentsWorld(harness.db, harness.root / "objects")


def run(client: TestClient, name: str, **body: Any) -> Any:
    return client.post(f"/commands/{name}", json={"scope": SCOPE, **body})


def test_every_documents_command_has_the_access_pinned_here() -> None:
    assert {c.model.__name__: c.access for c in API_COMMANDS} == EXPECTED_ACCESS


def test_an_admin_command_is_refused_to_a_person_and_a_user_command_is_not(
    people: People,
) -> None:
    for name, access in EXPECTED_ACCESS.items():
        refused = run(people.bob, name)  # an empty body: never the access check that fails first
        if access == "admin":
            assert refused.status_code == 403, name
            assert refused.json()["error"] == "forbidden", name
            assert f"admin.command.{name}" in refused.json()["message"], name
        else:
            assert refused.status_code != 403, (name, refused.text)
        assert run(people.boss, name).status_code != 403, name


def test_an_agent_runs_none_of_them(people: People) -> None:
    for name in EXPECTED_ACCESS:
        refused = run(people.agent, name)
        assert refused.status_code == 403, name
        assert refused.json()["error"] == "agent_must_propose", name


def test_a_person_prepares_and_an_admin_controls_over_http(
    people: People, world: DocumentsWorld
) -> None:
    made = run(people.bob, "RegisterDocument", number="ISO-1234", title="Isometric", doc_type="ISO")
    assert made.status_code == 200, made.text
    doc_id = made.json()["stream_id"]
    revision = run(people.bob, "CreateRevision", document_id=doc_id)
    assert revision.status_code == 200 and revision.json()["key"] == "ISO-1234@A"
    rev_id = revision.json()["stream_id"]
    world.attach("ISO-1234", "A")
    refused = run(people.bob, "IssueRevision", stream_id=rev_id, issue_status="IFR")
    assert refused.status_code == 403 and "admin.command.IssueRevision" in refused.json()["message"]
    issued = run(people.boss, "IssueRevision", stream_id=rev_id, issue_status="IFR")
    assert issued.status_code == 200, issued.text
    # the same person may not void or supersede, nor set the confidentiality
    for name, body in (
        ("VoidDocument", {"stream_id": doc_id, "reason": "x"}),
        (
            "SetDocumentConfidentiality",
            {"stream_id": doc_id, "confidentiality": "x", "reason": "x"},
        ),
    ):
        assert run(people.bob, name, **body).status_code == 403, name
    assert (
        run(
            people.boss,
            "SetDocumentConfidentiality",
            stream_id=doc_id,
            confidentiality="internal",
            reason="client request",
        ).status_code
        == 200
    )


def test_a_future_issue_date_is_a_422_with_its_own_code(
    people: People, world: DocumentsWorld
) -> None:
    world.register("ISO-1234")
    world.create_revision("ISO-1234")
    world.attach("ISO-1234", "A")
    rev = world.revision("ISO-1234", "A")
    late = run(
        people.boss, "IssueRevision", stream_id=rev.id, issue_status="IFR", issued_on="2999-01-01"
    )
    assert late.status_code == 422 and late.json()["error"] == "backdated"


def test_a_pinned_link_goes_stale_and_a_person_re_pins_it(
    people: People, world: DocumentsWorld
) -> None:
    world.issued_document("ISO-1234")
    tag = run(
        people.bob, "CreateRecord", record_type="core.Record", title="Valve", key="47-FV-1001"
    ).json()["stream_id"]
    doc = world.document("ISO-1234")
    link = run(people.bob, "LinkToDocument", from_id=tag, document_id=doc.id, pin="A")
    assert link.status_code == 200, link.text
    world.create_revision("ISO-1234")
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    rev_b = world.revision("ISO-1234", "B")
    assert (
        run(people.bob, "IssueRevision", stream_id=rev_b.id, issue_status="IFC").status_code == 403
    )
    assert (
        run(people.boss, "IssueRevision", stream_id=rev_b.id, issue_status="IFC").status_code == 200
    )
    assert world.link_status(link.json()["stream_id"]) == "stale"
    repinned = run(people.bob, "RepinDocumentLink", link_id=link.json()["stream_id"])
    assert repinned.status_code == 200, repinned.text
    assert world.link_status(link.json()["stream_id"]) == "active"


def test_by_module_in_a_body_changes_nothing(people: People, world: DocumentsWorld) -> None:
    """The generic workflow command stays shut to a document whatever the body says."""
    world.register("ISO-1234")
    doc = world.document("ISO-1234")
    response = run(
        people.boss,
        "TransitionWorkflow",
        stream_id=doc.id,
        expected_version=doc.version,
        transition="void",
        by_module=True,
    )
    assert response.status_code == 422, response.text
    assert world.document("ISO-1234").state == "Registered"


def test_the_generic_commands_stay_shut_over_http(people: People, world: DocumentsWorld) -> None:
    world.register("ISO-1234")
    doc = world.document("ISO-1234")
    for name, body in (
        (
            "TransitionWorkflow",
            {"stream_id": doc.id, "expected_version": doc.version, "transition": "void"},
        ),
        (
            "SetPsetValues",
            {
                "stream_id": doc.id,
                "expected_version": doc.version,
                "pset": "documents.Document",
                "values": {"title": "x"},
            },
        ),
    ):
        refused = run(people.boss, name, **body)
        assert refused.status_code == 422, (name, refused.text)
    assert world.document("ISO-1234").title == "Isometric, line 47-P-101"


def declare(record_id: str, slot: str | None, body: bytes) -> dict[str, Any]:
    return {
        "scope": SCOPE,
        "record_id": record_id,
        "slot": slot,
        "filename": "a.pdf",
        "content_type": "application/pdf",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def test_an_upload_into_a_revision_follows_its_state_over_http(
    people: People, world: DocumentsWorld
) -> None:
    world.issued_document("ISO-1234")
    rev = world.revision("ISO-1234", "A")
    body = b"%PDF-1.7 upload"
    for slot, status in (
        ("markup", 200),
        ("signed", 200),
        ("pdf", 422),
        ("native", 422),
        (None, 422),
    ):
        response = people.bob.post("/uploads", json=declare(rev.id, slot, body))
        assert response.status_code == status, (slot, response.text)
        if status == 422:
            assert response.json()["error"] == "unsupported_record_type", slot


def test_a_key_with_an_at_sign_or_a_slash_cannot_be_taken_by_a_generic_record(
    people: People,
) -> None:
    for key in ("ISO-1234@A", "ISO-1234@A/pdf-1"):
        refused = run(people.bob, "CreateRecord", record_type="core.Record", title="t", key=key)
        assert refused.status_code == 422 and refused.json()["error"] == "reserved_key"
