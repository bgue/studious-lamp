"""AttachRendition against a real ledger and file service (T04): kinds by state, supersession."""

from __future__ import annotations

import pytest
from docworld import BASE, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.services.errors import NoChangesError
from tl_mod_documents import registry
from tl_mod_documents.errors import (
    DocumentClosedError,
    FileNotAvailableError,
    RenditionNotAllowedError,
    RevisionNotFoundError,
)
from tl_mod_documents.handlers.documents import VoidDocument, handle_void_document
from tl_mod_documents.handlers.renditions import AttachRendition, handle_attach_rendition


def attach_file(world: World, revision_id: str, file_id: str, **more: object) -> object:
    with open_uow(world.db) as uow:
        return handle_attach_rendition(
            uow, AttachRendition(**{**BASE, "revision_id": revision_id, "file_id": file_id, **more})
        )


def renditions(world: World, number: str, code: str) -> list[registry.RenditionRow]:
    rev = world.revision(number, code)
    with open_uow(world.db, readonly=True) as uow:
        return registry.renditions_of(uow.conn(), rev.id)


def test_an_uploaded_file_becomes_the_rendition_of_its_slot(world: World) -> None:
    world.register()
    world.create_revision()
    made = world.attach("ISO-1234", "A", page_count=3)
    assert made.key == "ISO-1234@A/pdf-1"
    assert [e.event_type for e in made.events] == ["Record.Created", "Rendition.Defined"]
    (row,) = renditions(world, "ISO-1234", "A")
    assert row.kind == "pdf" and row.is_current and row.page_count == 3
    assert row.filename == "sheet.pdf" and row.content_type == "application/pdf"
    assert row.size == len(b"%PDF-1.7 isometric drawing sheet") and len(row.sha256) == 64


def test_a_newer_rendition_of_the_same_kind_supersedes_the_older(world: World) -> None:
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A")
    second = world.attach("ISO-1234", "A", data=b"%PDF-1.7 second", name="sheet-2.pdf")
    assert second.key == "ISO-1234@A/pdf-2"
    older, newer = renditions(world, "ISO-1234", "A")
    assert not older.is_current and older.superseded_by == newer.id and newer.is_current
    types = [e.event_type for e in second.events]
    assert types == ["Record.Created", "Rendition.Defined", "Rendition.Superseded"]
    other_kind = world.attach("ISO-1234", "A", slot="native", data=b"dwg", name="a.dwg")
    assert other_kind.key == "ISO-1234@A/native-1"
    assert sum(r.is_current for r in renditions(world, "ISO-1234", "A")) == 2  # pdf and native


def test_the_same_file_is_not_registered_twice(world: World) -> None:
    world.register()
    world.create_revision()
    rev = world.revision("ISO-1234", "A")
    uploaded = world.upload(rev.id)
    attach_file(world, rev.id, uploaded.file_id)
    with pytest.raises(NoChangesError, match="already the pdf rendition"):
        attach_file(world, rev.id, uploaded.file_id)


def test_kinds_by_state(world: World) -> None:
    world.register()
    world.create_revision()
    rev = world.revision("ISO-1234", "A")
    world.attach(
        "ISO-1234", "A", slot="markup", data=b"%PDF markup", name="m.pdf"
    )  # draft: all but signed
    # Draft refuses `signed` as a rendition even though the slot takes the upload
    uploaded = world.upload(rev.id, "signed", b"%PDF signed", "s.pdf")
    with pytest.raises(RenditionNotAllowedError, match="Draft; it accepts native, pdf, markup"):
        attach_file(world, rev.id, uploaded.file_id)
    world.attach("ISO-1234", "A")
    world.issue("ISO-1234", "A")
    # Issued: a signed copy and a markup are accepted, a new pdf is not
    attach_file(world, rev.id, uploaded.file_id)
    world.attach("ISO-1234", "A", slot="markup", data=b"%PDF markup 2", name="m2.pdf")
    late = world.upload(rev.id, "pdf", b"%PDF-1.7 late", "late.pdf")
    with pytest.raises(RenditionNotAllowedError, match="Issued; it accepts markup, signed"):
        attach_file(world, rev.id, late.file_id)


def test_a_superseded_revision_still_takes_markups_and_signed_copies(world: World) -> None:
    world.issued_document()
    world.create_revision()
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFR")  # supersedes A in the review class
    assert world.revision("ISO-1234", "A").state == "Superseded"
    made = world.attach("ISO-1234", "A", slot="signed", data=b"%PDF signed A", name="sA.pdf")
    assert made.key == "ISO-1234@A/signed-1"


def test_a_file_must_belong_to_the_revision_and_a_rendition_slot_and_be_available(
    world: World,
) -> None:
    world.register()
    world.create_revision()
    a = world.revision("ISO-1234", "A")
    with pytest.raises(FileNotAvailableError, match="no file"):
        attach_file(world, a.id, "nope")
    world.register("ISO-5678")
    world.create_revision("ISO-5678")
    other = world.revision("ISO-5678", "A")
    elsewhere = world.upload(other.id)
    with pytest.raises(FileNotAvailableError, match="not attached to revision ISO-1234@A"):
        attach_file(world, a.id, elsewhere.file_id)


def test_a_file_with_no_slot_is_not_a_rendition(world: World) -> None:
    import hashlib
    import io

    from tl_core.files.service import CompleteUpload, RegisterUpload

    world.register()
    world.create_revision()
    a = world.revision("ISO-1234", "A")
    data = b"a loose attachment"
    declared = RegisterUpload(
        **BASE,
        record_id=a.id,
        slot=None,
        filename="note.txt",
        content_type="text/plain",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    with open_uow(world.db) as uow:
        ticket = world.files.register_upload(uow, declared)
    with open_uow(world.db) as uow:
        done = world.files.complete_upload(
            uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(data)
        )
    with pytest.raises(FileNotAvailableError, match="not in a rendition slot"):
        attach_file(world, a.id, done.file_id)


def test_a_void_revision_and_a_closed_document_take_no_renditions(world: World) -> None:
    world.register()
    world.create_revision()
    a = world.revision("ISO-1234", "A")
    uploaded = world.upload(a.id)
    doc = world.document("ISO-1234")
    with open_uow(world.db) as uow:
        handle_void_document(uow, VoidDocument(**BASE, stream_id=doc.id, reason="x"))
    with pytest.raises(DocumentClosedError):
        attach_file(world, a.id, uploaded.file_id)


def test_the_revision_must_exist_in_the_scope(world: World) -> None:
    with pytest.raises(RevisionNotFoundError):
        attach_file(world, "nope", "f")


def test_page_count_is_bounded(world: World) -> None:
    with pytest.raises(ValidationError):
        AttachRendition(**BASE, revision_id="r", file_id="f", page_count=-1)
    with pytest.raises(ValidationError):
        AttachRendition(**BASE, revision_id="r", file_id="f", page_count=10**9)
