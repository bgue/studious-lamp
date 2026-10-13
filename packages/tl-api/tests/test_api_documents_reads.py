"""The documents reads over HTTP and through the client: who may read, what comes back (P1-I2)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_adapters.db import open_uow
from tl_api.client import ApiClient
from tl_api.tokens import add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_documents.errors import (
    DocumentNotFoundError,
    InvalidPinError,
    TransmittalNotFoundError,
)
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    Recipient,
    handle_create_transmittal,
)
from tl_mod_documents.testing import BASE, DocumentsWorld

PASSWORD = "correct horse battery"
P = "/projects/P123"


class Readers:
    """A person (`bob`) and an agent, each with a client on the harness."""

    def __init__(self, harness: Harness) -> None:
        with harness.backend() as uow:
            accounts.create_account(
                uow, username="bob", display_name="bob", kind="person", roles=["user"],
                password=prepare_password(PASSWORD), by="svc:test",
            )  # fmt: skip
        _, token = sessions.sign_in(harness.backend, username="bob", password=PASSWORD)
        self.bob = harness.client_for(None)
        self.bob.headers.update({"Authorization": f"Bearer {token}"})
        self.bob_token = token
        self.agent = TestClient(harness.app, raise_server_exceptions=False)
        self.agent_token = add_token(harness.settings.tokens_path, "agent:triage")
        self.agent.headers.update({"Authorization": f"Bearer {self.agent_token}"})
        self.anonymous = harness.client_for(None)


@pytest.fixture
def readers(harness: Harness) -> Readers:
    return Readers(harness)


@pytest.fixture
def world(harness: Harness) -> DocumentsWorld:
    made = DocumentsWorld(harness.db, harness.root / "objects")
    made.issued_document("ISO-1234", "IFR")
    made.link(made.tag(), "ISO-1234", "A")
    made.create_revision("ISO-1234", purpose="For construction")
    made.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    made.issue("ISO-1234", "B", "IFC")
    made.register("ISO-2000")
    with open_uow(harness.db) as uow:
        handle_create_transmittal(
            uow,
            CreateTransmittal(
                **BASE,
                subject="To site",
                purpose="for_construction",
                recipients=[Recipient(name="Site")],
                revision_ids=[made.revision("ISO-1234", "B").id],
            ),
        )
    return made


READS = (
    f"{P}/documents",
    f"{P}/documents/ISO-1234",
    f"{P}/documents/ISO-1234/diff?from=A&to=B",
    f"{P}/stale-links",
    f"{P}/overdue-reviews",
    f"{P}/transmittals",
)


def test_a_person_and_an_agent_can_read_and_nobody_unsigned_can(
    readers: Readers, world: DocumentsWorld
) -> None:
    for path in READS:
        assert readers.bob.get(path).status_code == 200, path
        assert readers.agent.get(path).status_code == 200, path
        assert readers.anonymous.get(path).status_code == 401, path


def test_the_listing_and_the_detail(readers: Readers, world: DocumentsWorld) -> None:
    listing = readers.bob.get(f"{P}/documents").json()
    assert [d["number"] for d in listing] == ["ISO-1234", "ISO-2000"]
    assert listing[0]["revisions"] == [] and listing[0]["current_revision_code"] == "B"
    only = readers.bob.get(f"{P}/documents", params={"state": "Registered"}).json()
    assert [d["number"] for d in only] == ["ISO-2000"]
    detail = readers.bob.get(f"{P}/documents/ISO-1234").json()
    assert [r["code"] for r in detail["revisions"]] == ["A", "B"]
    assert detail["links"][0]["pin_state"] == "stale" and detail["links"][0]["pin"] == "A"
    assert detail["revisions"][1]["renditions"][0]["filename"] == "b.pdf"


def test_the_diff_stale_links_overdue_reviews_and_transmittals(
    readers: Readers, world: DocumentsWorld
) -> None:
    diff = readers.bob.get(f"{P}/documents/ISO-1234/diff", params={"from": "A", "to": "B"}).json()
    assert diff["summary"][0] == "ISO-1234: A (IFR) to B (IFC)"
    stale = readers.bob.get(f"{P}/stale-links").json()
    assert [(s["document_number"], s["pinned_code"], s["current_code"]) for s in stale] == [
        ("ISO-1234", "A", "B")
    ]
    assert readers.bob.get(f"{P}/overdue-reviews", params={"on": "2026-10-13"}).json() == []
    transmittals = readers.bob.get(f"{P}/transmittals").json()
    assert [t["state"] for t in transmittals] == ["Draft"] and transmittals[0]["items"] == []
    one = readers.bob.get(f"{P}/transmittals/{transmittals[0]['number']}").json()
    assert [(i["document_number"], i["revision_code"]) for i in one["items"]] == [("ISO-1234", "B")]


def test_unknown_things_are_the_modules_404_and_422(
    readers: Readers, world: DocumentsWorld
) -> None:
    missing = readers.bob.get(f"{P}/documents/NOPE-1")
    assert (missing.status_code, missing.json()["error"]) == (404, "document_not_found")
    other = readers.bob.get("/projects/P999/documents/ISO-1234")
    assert other.status_code == 404
    gone = readers.bob.get(f"{P}/transmittals/NOPE-1")
    assert (gone.status_code, gone.json()["error"]) == (404, "transmittal_not_found")
    bad = readers.bob.get(f"{P}/documents/ISO-1234/diff", params={"from": "A", "to": "Z"})
    assert (bad.status_code, bad.json()["error"]) == (422, "invalid_pin")
    assert readers.bob.get(f"{P}/documents/ISO-1234/diff").status_code == 422  # no from/to


def test_the_client_returns_the_models_and_rebuilds_the_errors(
    harness: Harness, readers: Readers, world: DocumentsWorld
) -> None:
    client = ApiClient("http://testserver", readers.bob_token, http=readers.bob)
    assert [d.number for d in client.list_documents("P123")] == ["ISO-1234", "ISO-2000"]
    doc = client.get_document("P123", "ISO-1234")
    assert [r.code for r in doc.revisions] == ["A", "B"] and doc.links[0].newer_codes == ["B"]
    assert client.document_diff("P123", "ISO-1234", "A", "B").to_status == "IFC"
    assert [s.pinned_code for s in client.list_stale_links("P123")] == ["A"]
    assert client.list_overdue_reviews("P123", on=date(2026, 10, 13)) == []
    (sent,) = client.list_transmittals("P123")
    assert client.get_transmittal("P123", sent.number).items[0].revision_code == "B"
    with pytest.raises(DocumentNotFoundError):
        client.get_document("P123", "NOPE-1")
    with pytest.raises(TransmittalNotFoundError):
        client.get_transmittal("P123", "NOPE-1")
    with pytest.raises(InvalidPinError):
        client.document_diff("P123", "ISO-1234", "A", "Z")
