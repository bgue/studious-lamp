"""`FakeClient` document reads answer like the embedded client (P1-I2): numbers, filters, errors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.db import open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
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
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"


@pytest.fixture
def both(tmp_path: Path) -> Iterator[tuple[ClientInterface, ClientInterface]]:
    """An embedded client over a ledger with three documents, and a fake holding the same ones."""
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        path = tmp_path / "tl.db"
        create_schema(path)
        made = DocumentsWorld(path, tmp_path / "objects")
        made.issued_document("ISO-1234", "IFR")
        made.link(made.tag(), "ISO-1234", "A")
        made.create_revision("ISO-1234", purpose="For construction")
        made.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
        made.issue("ISO-1234", "B", "IFC")
        made.register("ISO-2000", discipline="ELE")
        made.register("ISO-3000")
        made.move(made.document("ISO-3000").id, "void")
        with open_uow(path) as uow:
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
        factory = SqliteUowFactory(path)
        embedded = EmbeddedClient(factory, actor="user:kim")
        fake = FakeClient()
        for number in ("ISO-1234", "ISO-2000", "ISO-3000"):
            fake.add_document("P123", embedded.get_document("P123", number))
        for item in embedded.list_transmittals("P123"):
            fake.add_transmittal("P123", embedded.get_transmittal("P123", item.number))
        for line in embedded.list_stale_links("P123"):
            fake.add_stale_link("P123", line)
        fake.add_diff("P123", "ISO-1234", embedded.document_diff("P123", "ISO-1234", "A", "B"))
        try:
            yield embedded, fake
        finally:
            factory.dispose()


READS = [
    ("all", lambda c: c.list_documents("P123")),
    ("with the void ones", lambda c: c.list_documents("P123", include_void=True)),
    ("by discipline", lambda c: c.list_documents("P123", discipline="ELE")),
    ("by state", lambda c: c.list_documents("P123", state="Issued")),
    ("a limit", lambda c: c.list_documents("P123", limit=1)),
    ("another project", lambda c: c.list_documents("OTHER")),
    ("transmittals", lambda c: c.list_transmittals("P123")),
    ("transmittals by state", lambda c: c.list_transmittals("P123", state="Issued")),
    ("transmittals the other way", lambda c: c.list_transmittals("P123", direction="incoming")),
    ("stale links", lambda c: c.list_stale_links("P123")),
]


@pytest.mark.parametrize(("name", "read"), READS, ids=[n for n, _ in READS])
def test_a_listing_is_the_same_on_both(
    both: tuple[ClientInterface, ClientInterface], name: str, read: Any
) -> None:
    embedded, fake = both
    assert read(fake) == read(embedded), name


def test_documents_come_by_number_and_the_void_one_only_on_request(
    both: tuple[ClientInterface, ClientInterface],
) -> None:
    embedded, _ = both
    assert [d.number for d in embedded.list_documents("P123")] == ["ISO-1234", "ISO-2000"]
    assert "ISO-3000" in [d.number for d in embedded.list_documents("P123", include_void=True)]


def test_one_document_comes_with_revisions_and_links_and_unknowns_are_the_modules_errors(
    both: tuple[ClientInterface, ClientInterface],
) -> None:
    embedded, fake = both
    doc = embedded.get_document("P123", "ISO-1234")
    assert [r.code for r in doc.revisions] == ["A", "B"] and doc.links[0].pin_state == "stale"
    assert fake.get_document("P123", "ISO-1234") == doc
    for client in (embedded, fake):
        with pytest.raises(DocumentNotFoundError, match="NOPE-1"):
            client.get_document("P123", "NOPE-1")
        with pytest.raises(TransmittalNotFoundError, match="NOPE-1"):
            client.get_transmittal("P123", "NOPE-1")
    with pytest.raises(InvalidPinError):
        embedded.document_diff("P123", "ISO-1234", "A", "Z")
    assert embedded.document_diff("P123", "ISO-1234", "A", "B") == fake.document_diff(
        "P123", "ISO-1234", "A", "B"
    )
