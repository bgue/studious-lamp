"""The pin and stale resolver (T07): pins, stale links on issue, re-pin, the revision diff."""

from __future__ import annotations

from typing import Any

import pytest
from docworld import BASE, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_documents import registry
from tl_mod_documents.errors import DocumentNotFoundError, InvalidPinError
from tl_mod_documents.handlers.documents import VoidDocument, handle_void_document
from tl_mod_documents.resolver import (
    LinkToDocument,
    RepinDocumentLink,
    handle_link_to_document,
    handle_repin_document_link,
    links_to_documents,
    resolve_pin,
    revision_diff,
)


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


def link_to(world: World, from_id: str, number: str, pin: str | None, **more: Any) -> str:
    doc = world.document(number)
    made = run(
        world,
        handle_link_to_document,
        LinkToDocument(**BASE, from_id=from_id, document_id=doc.id, pin=pin, **more),
    )
    return str(made.stream_id)


def resolution(world: World, number: str, pin: str | None) -> Any:
    doc = world.document(number)
    with open_uow(world.db, readonly=True) as uow:
        return resolve_pin(uow.conn(), doc.id, pin)


def two_revisions(world: World) -> None:
    """A issued for review, B issued for construction; A's PDF and B's differ."""
    world.issued_document(status="IFR")
    world.create_revision(purpose="Re-issued for construction", change_note="Weld map added")
    world.attach(
        "ISO-1234", "B", data=b"%PDF-1.7 version two, longer", name="sheet-b.pdf", page_count=5
    )
    world.attach("ISO-1234", "B", slot="native", data=b"dwg", name="b.dwg")


def test_what_a_pin_means(world: World) -> None:
    world.register()
    assert resolution(world, "ISO-1234", None).state == "no_current"  # nothing issued yet
    world.create_revision()
    world.attach("ISO-1234", "A")
    world.issue("ISO-1234", "A", "IFR")
    assert resolution(world, "ISO-1234", None).state == "floating"
    assert resolution(world, "ISO-1234", None).resolved_code == "A"
    assert resolution(world, "ISO-1234", "A").state == "current"
    assert resolution(world, "ISO-1234", "Z").state == "unknown"
    world.create_revision()
    assert resolution(world, "ISO-1234", "B").state == "unknown"  # a draft cannot be pinned
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")
    stale = resolution(world, "ISO-1234", "A")
    assert stale.state == "stale" and stale.newer_codes == ["B"] and stale.current_code == "B"
    assert resolution(world, "ISO-1234", "B").state == "current"
    assert resolution(world, "ISO-1234", None).resolved_code == "B"


def test_a_new_revision_makes_pinned_links_stale_and_leaves_the_others(world: World) -> None:
    world.issued_document()
    pinned = link_to(world, world.tag("47-FV-1001"), "ISO-1234", "A")
    floating = link_to(world, world.tag("47-FV-1002"), "ISO-1234", None)
    current = link_to(world, world.tag("47-FV-1003"), "ISO-1234", "current")
    world.create_revision()
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    result = world.issue("ISO-1234", "B", "IFC")
    assert world.link_status(pinned) == "stale"
    assert world.link_status(floating) == "active"
    assert world.link_status(current) == "stale"  # `current` pinned A, which B has replaced
    flagged = [e for e in result.events if e.event_type == "Link.Flagged"]
    assert len(flagged) == 2
    assert {e.payload["reason"] for e in flagged} == {"revision B issued"}
    assert {e.correlation_id for e in result.events} == {result.events[0].correlation_id}
    # a link made after the issue and pinned to B is fine
    fresh = link_to(world, world.tag("47-FV-1004"), "ISO-1234", "B")
    assert world.link_status(fresh) == "active"


def test_repin_brings_a_stale_link_back_and_can_float_it(world: World) -> None:
    world.issued_document()
    link = link_to(world, world.tag(), "ISO-1234", "A")
    world.create_revision()
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")
    assert world.link_status(link) == "stale"
    result = run(
        world, handle_repin_document_link, RepinDocumentLink(**BASE, link_id=link)
    )  # the default pin is `current`
    assert [e.event_type for e in result.events] == ["Link.Repinned"]
    assert world.link_status(link) == "active"
    assert world.scalar("SELECT pin FROM cur_links WHERE link_id = :i", i=link) == "B"
    with pytest.raises(NoChangesError):
        run(world, handle_repin_document_link, RepinDocumentLink(**BASE, link_id=link, pin="B"))
    run(world, handle_repin_document_link, RepinDocumentLink(**BASE, link_id=link, pin=None))
    assert world.scalar("SELECT pin FROM cur_links WHERE link_id = :i", i=link) is None


def test_a_pin_must_name_an_issued_revision(world: World) -> None:
    world.issued_document()
    world.create_revision()  # B is a draft
    tag = world.tag()
    doc = world.document("ISO-1234")
    for pin in ("B", "Z", "a"):
        with pytest.raises(InvalidPinError, match="not an issued revision"):
            link_to(world, tag, "ISO-1234", pin)
    link = link_to(world, tag, "ISO-1234", "A")
    with pytest.raises(InvalidPinError):
        run(world, handle_repin_document_link, RepinDocumentLink(**BASE, link_id=link, pin="B"))
    assert doc.id  # the document is untouched by the refusals
    assert world.link_status(link) == "active"


def test_current_needs_a_current_revision_and_a_live_document(world: World) -> None:
    world.register()
    tag = world.tag()
    with pytest.raises(InvalidPinError, match="no current revision"):
        link_to(world, tag, "ISO-1234", "current")
    assert world.link_status(link_to(world, tag, "ISO-1234", None)) == "active"  # floating is fine
    world.issued_document("ISO-9999")
    doc = world.document("ISO-9999")
    run(world, handle_void_document, VoidDocument(**BASE, stream_id=doc.id, reason="x"))
    with pytest.raises(InvalidPinError, match="Void; it cannot be linked to"):
        link_to(world, world.tag("47-FV-2000"), "ISO-9999", None)


def test_only_the_documents_links_can_be_repinned_this_way(world: World) -> None:
    world.issued_document()
    tag_a, tag_b = world.tag("47-FV-1001"), world.tag("47-FV-1002")
    from tl_core.services.links import AddLink, handle_add_link

    with open_uow(world.db) as uow:
        plain = handle_add_link(
            uow, AddLink(**BASE, from_id=tag_a, to_id=tag_b, relation="references")
        )
    with pytest.raises(InvalidPinError, match="does not point to a document"):
        run(world, handle_repin_document_link, RepinDocumentLink(**BASE, link_id=plain.stream_id))
    with pytest.raises(RecordNotFoundError):
        run(world, handle_repin_document_link, RepinDocumentLink(**BASE, link_id="nope"))
    with pytest.raises(DocumentNotFoundError):
        run(
            world,
            handle_link_to_document,
            LinkToDocument(**BASE, from_id=tag_a, document_id="nope"),
        )


def test_the_command_bounds_its_text(world: World) -> None:
    with pytest.raises(ValidationError):
        LinkToDocument(**BASE, from_id="a", document_id="b", pin="X" * 200)
    with pytest.raises(ValidationError):
        LinkToDocument(**BASE, from_id="a", document_id="b", note="n" * 5000)
    with pytest.raises(ValidationError):
        RepinDocumentLink(**BASE, link_id="a", pin="X" * 200)


def test_the_links_of_a_document_are_listed_with_what_each_pin_means(world: World) -> None:
    world.issued_document()
    link_to(world, world.tag("47-FV-1001"), "ISO-1234", "A")
    link_to(world, world.tag("47-FV-1002"), "ISO-1234", None)
    world.create_revision()
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")
    with open_uow(world.db, readonly=True) as uow:
        everything = links_to_documents(uow.conn(), "project:P123")
        stale = links_to_documents(uow.conn(), "project:P123", only_stale=True)
        other_scope = links_to_documents(uow.conn(), "project:P999")
    assert [(x.from_key, x.pin, x.resolution.state) for x in everything] == [
        ("47-FV-1001", "A", "stale"),
        ("47-FV-1002", None, "floating"),
    ]
    assert [x.from_key for x in stale] == ["47-FV-1001"]
    assert stale[0].link_status == "stale" and stale[0].document_number == "ISO-1234"
    assert other_scope == []


def test_the_diff_says_what_changed_between_two_revisions(world: World) -> None:
    two_revisions(world)
    world.issue("ISO-1234", "B", "IFC")
    doc = world.document("ISO-1234")
    with open_uow(world.db, readonly=True) as uow:
        diff = revision_diff(uow.conn(), doc.id, "A", "B")
    assert (diff.from_code, diff.to_code, diff.from_status, diff.to_status) == (
        "A",
        "B",
        "IFR",
        "IFC",
    )
    assert len(diff.steps) == 1 and diff.steps[0].startswith("B (IFC, ")
    assert "Re-issued for construction" in diff.steps[0] and "Weld map added" in diff.steps[0]
    by_kind = {c.kind: c for c in diff.renditions}
    assert by_kind["pdf"].change == "changed" and "5 pages" in (by_kind["pdf"].after or "")
    assert by_kind["native"].change == "added" and by_kind["native"].before is None
    assert diff.changed
    assert diff.summary[0] == "ISO-1234: A (IFR) to B (IFC)"
    assert "status IFR to IFC" in diff.summary
    assert any(line.startswith("native added: b.dwg") for line in diff.summary)


def test_the_diff_of_identical_files_is_unchanged_and_works_backwards(world: World) -> None:
    world.issued_document()
    world.create_revision()
    world.attach("ISO-1234", "B")  # the same bytes as A's PDF
    world.issue("ISO-1234", "B", "IFR")
    doc = world.document("ISO-1234")
    with open_uow(world.db, readonly=True) as uow:
        forward = revision_diff(uow.conn(), doc.id, "A", "B")
        backward = revision_diff(uow.conn(), doc.id, "B", "A")
    assert [c.change for c in forward.renditions] == ["unchanged"]
    assert backward.steps == forward.steps  # the revisions between, whichever way you ask


def test_the_diff_refuses_a_code_that_is_not_an_issued_revision(world: World) -> None:
    two_revisions(world)  # B is still a draft
    doc = world.document("ISO-1234")
    with open_uow(world.db, readonly=True) as uow:
        for pair in (("A", "B"), ("A", "Z"), ("Q", "A")):
            with pytest.raises(InvalidPinError):
                revision_diff(uow.conn(), doc.id, *pair)
        with pytest.raises(DocumentNotFoundError):
            revision_diff(uow.conn(), "nope", "A", "B")
        assert registry.get_document(uow.conn(), doc.id) is not None
