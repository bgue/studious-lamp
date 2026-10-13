"""The read models that screens, the API and the MCP tools share."""

from __future__ import annotations

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_mod_documents import views
from tl_mod_documents.errors import DocumentNotFoundError, InvalidPinError, TransmittalNotFoundError
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    Recipient,
    handle_create_transmittal,
)

SCOPE = "project:P123"


@pytest.fixture
def busy(world: World) -> World:
    """ISO-1234 with A (IFR) and B (IFC) issued and a link pinned to A; ISO-2000 registered."""
    world.issued_document("ISO-1234", "IFR")
    world.link(world.tag(), "ISO-1234", "A")
    world.create_revision("ISO-1234", purpose="For construction")
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")
    world.register("ISO-2000")
    return world


def test_a_listing_has_no_revisions_or_links(busy: World) -> None:
    with open_uow(busy.db, readonly=True) as uow:
        found = views.document_views(uow.conn(), SCOPE)
    assert [d.number for d in found] == ["ISO-1234", "ISO-2000"]
    first = found[0]
    assert (first.state, first.current_revision_code, first.current_revision_status) == (
        "Issued",
        "B",
        "IFC",
    )
    assert first.revisions == [] and first.links == []
    with open_uow(busy.db, readonly=True) as uow:
        only = views.document_views(uow.conn(), SCOPE, state="Registered")
    assert [d.number for d in only] == ["ISO-2000"]


def test_one_document_carries_its_revisions_renditions_and_links(busy: World) -> None:
    with open_uow(busy.db, readonly=True) as uow:
        doc = views.document_view(uow.conn(), SCOPE, "ISO-1234")
    assert [r.code for r in doc.revisions] == ["A", "B"]
    a, b = doc.revisions
    assert (a.issue_status, a.is_current, b.status_class) == ("IFR", True, "construction")
    assert [x.kind for x in b.renditions] == ["pdf"] and b.renditions[0].filename == "b.pdf"
    (link,) = doc.links
    assert (link.pin, link.pin_state, link.link_status) == ("A", "stale", "stale")
    assert (link.current_code, link.newer_codes, link.from_key) == ("B", ["B"], "47-FV-1001")


def test_an_unknown_document_or_transmittal_is_the_modules_error(busy: World) -> None:
    with open_uow(busy.db, readonly=True) as uow:
        with pytest.raises(DocumentNotFoundError):
            views.document_view(uow.conn(), SCOPE, "NOPE-1")
        with pytest.raises(DocumentNotFoundError):
            views.document_view(uow.conn(), "project:P999", "ISO-1234")
        with pytest.raises(TransmittalNotFoundError):
            views.transmittal_view(uow.conn(), SCOPE, "NOPE-1")


def test_the_diff_view_says_what_changed(busy: World) -> None:
    with open_uow(busy.db, readonly=True) as uow:
        diff = views.revision_diff_view(uow.conn(), SCOPE, "ISO-1234", "A", "B")
        assert diff.summary[0] == "ISO-1234: A (IFR) to B (IFC)"
        assert "status IFR to IFC" in diff.summary
        with pytest.raises(InvalidPinError):
            views.revision_diff_view(uow.conn(), SCOPE, "ISO-1234", "A", "Z")


def test_a_transmittal_view_lists_its_items(busy: World) -> None:
    with open_uow(busy.db) as uow:
        made = handle_create_transmittal(
            uow,
            CreateTransmittal(
                **BASE,
                subject="To site",
                purpose="for_construction",
                recipients=[Recipient(name="Site", organisation="Acme")],
                revision_ids=[busy.revision("ISO-1234", "B").id],
            ),
        )
    with open_uow(busy.db, readonly=True) as uow:
        listing = views.transmittal_views(uow.conn(), SCOPE)
        one = views.transmittal_view(uow.conn(), SCOPE, made.key or "")
    assert [t.number for t in listing] == [made.key] and listing[0].items == []
    assert (one.state, one.direction, one.recipients[0]["name"]) == ("Draft", "outgoing", "Site")
    assert [(i.document_number, i.revision_code, i.issue_status) for i in one.items] == [
        ("ISO-1234", "B", "IFC")
    ]


def test_stale_links_and_overdue_reviews_are_the_report_rows(busy: World) -> None:
    with open_uow(busy.db, readonly=True) as uow:
        stale = views.stale_links(uow.conn(), SCOPE)
        late = views.overdue_reviews(uow.conn(), SCOPE)
    assert [(s.document_number, s.pinned_code, s.current_code) for s in stale] == [
        ("ISO-1234", "A", "B")
    ]
    assert late == []
