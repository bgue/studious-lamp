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
    with pytest.raises(NoChangesError, match="already a pdf rendition"):
        attach_file(world, rev.id, uploaded.file_id)


def test_kinds_by_state(world: World) -> None:
    world.register()
    world.create_revision()
    rev = world.revision("ISO-1234", "A")
    world.attach("ISO-1234", "A", slot="markup", data=b"%PDF markup", name="m.pdf")
    world.attach("ISO-1234", "A")
    early = world.upload(rev.id, "pdf", b"%PDF-1.7 early", "early.pdf")  # uploaded in Draft
    world.issue("ISO-1234", "A")
    # Issued: the earlier upload cannot become a rendition now, a markup and a signed copy can
    with pytest.raises(RenditionNotAllowedError, match="Issued; it accepts markup, signed"):
        attach_file(world, rev.id, early.file_id)
    world.attach("ISO-1234", "A", slot="markup", data=b"%PDF markup 2", name="m2.pdf")
    world.attach("ISO-1234", "A", slot="signed", data=b"%PDF signed", name="s.pdf")


def test_markups_are_additive_one_never_replaces_another(world: World) -> None:
    world.register()
    world.create_revision()
    world.attach("ISO-1234", "A", slot="markup", data=b"%PDF ana", name="ana.pdf")
    second = world.attach("ISO-1234", "A", slot="markup", data=b"%PDF bo", name="bo.pdf")
    assert [e.event_type for e in second.events] == ["Record.Created", "Rendition.Defined"]
    rows = renditions(world, "ISO-1234", "A")
    assert [(r.kind, r.is_current, r.superseded_by) for r in rows] == [
        ("markup", True, None),
        ("markup", True, None),
    ]


def test_the_signed_copy_is_registered_and_replaced_by_controller_commands_only(
    world: World,
) -> None:
    from tl_mod_documents.handlers.renditions import (
        RegisterSignedRendition,
        ReplaceSignedRendition,
        handle_register_signed_rendition,
        handle_replace_signed_rendition,
    )

    world.issued_document()
    rev = world.revision("ISO-1234", "A")
    first_file = world.upload(rev.id, "signed", b"%PDF signed 1", "s1.pdf")
    # the ordinary command refuses a signed copy, the first one included
    with pytest.raises(RenditionNotAllowedError, match="registered by a document controller"):
        attach_file(world, rev.id, first_file.file_id)
    assert [r for r in renditions(world, "ISO-1234", "A") if r.kind == "signed"] == []
    with open_uow(world.db) as uow:
        first = handle_register_signed_rendition(
            uow,
            RegisterSignedRendition(**BASE, revision_id=rev.id, file_id=first_file.file_id),
        )
    assert first.events[1].payload["replace_reason"] is None
    again = world.upload(rev.id, "signed", b"%PDF signed 2", "s2.pdf")
    with pytest.raises(RenditionNotAllowedError, match="already has a signed copy.*final"):
        with open_uow(world.db) as uow:
            handle_register_signed_rendition(
                uow, RegisterSignedRendition(**BASE, revision_id=rev.id, file_id=again.file_id)
            )

    def replace(file_id: str, reason: str = "re-signed after a stamp error") -> object:
        with open_uow(world.db) as uow:
            return handle_replace_signed_rendition(
                uow,
                ReplaceSignedRendition(**BASE, revision_id=rev.id, file_id=file_id, reason=reason),
            )

    made = replace(again.file_id)
    old, new = [r for r in renditions(world, "ISO-1234", "A") if r.kind == "signed"]
    assert not old.is_current and old.superseded_by == new.id and new.is_current
    assert old.id == first.stream_id
    events = [e for e in made.events]  # type: ignore[attr-defined]
    assert events[1].payload["replace_reason"] == "re-signed after a stamp error"
    assert [e.event_type for e in events] == [
        "Record.Created",
        "Rendition.Defined",
        "Rendition.Superseded",
    ]
    with pytest.raises(ValidationError):
        ReplaceSignedRendition(**BASE, revision_id=rev.id, file_id="f", reason="  ")


def test_replacing_needs_a_signed_copy_and_only_signed_files_are_registered_so(
    world: World,
) -> None:
    from tl_mod_documents.handlers.renditions import (
        RegisterSignedRendition,
        ReplaceSignedRendition,
        handle_register_signed_rendition,
        handle_replace_signed_rendition,
    )

    world.issued_document()
    rev = world.revision("ISO-1234", "A")
    signed = world.upload(rev.id, "signed", b"%PDF signed", "s.pdf")
    markup = world.upload(rev.id, "markup", b"%PDF markup", "m.pdf")
    for file_id, message in (
        (signed.file_id, "has no signed copy to replace"),
        (markup.file_id, "only a signed copy is registered this way"),
    ):
        with open_uow(world.db) as uow, pytest.raises(RenditionNotAllowedError, match=message):
            handle_replace_signed_rendition(
                uow, ReplaceSignedRendition(**BASE, revision_id=rev.id, file_id=file_id, reason="x")
            )
    with (
        open_uow(world.db) as uow,
        pytest.raises(RenditionNotAllowedError, match="only a signed copy is registered this way"),
    ):
        handle_register_signed_rendition(
            uow, RegisterSignedRendition(**BASE, revision_id=rev.id, file_id=markup.file_id)
        )


def test_a_revision_takes_a_bounded_number_of_markups(world: World) -> None:
    from tl_mod_documents.limits import MAX_MARKUPS

    world.issued_document()
    rev = world.revision("ISO-1234", "A")
    for n in range(MAX_MARKUPS):
        world.attach("ISO-1234", "A", slot="markup", data=f"%PDF m{n}".encode(), name=f"m{n}.pdf")
    extra = world.upload(rev.id, "markup", b"%PDF one too many", "extra.pdf")
    with pytest.raises(RenditionNotAllowedError, match=f"already has {MAX_MARKUPS} markups"):
        attach_file(world, rev.id, extra.file_id)
    assert len([r for r in renditions(world, "ISO-1234", "A") if r.kind == "markup"]) == MAX_MARKUPS


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


def test_a_revision_takes_no_file_without_a_slot(world: World) -> None:
    import hashlib
    import io

    from tl_core.files.service import RegisterUpload
    from tl_core.services.errors import UnsupportedRecordTypeError

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
    with open_uow(world.db) as uow, pytest.raises(UnsupportedRecordTypeError, match="no slot"):
        world.files.register_upload(uow, declared)
    assert io.BytesIO(data).read() == data


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


def test_the_preflight_refuses_what_the_command_would_before_a_file_is_uploaded(
    world: World,
) -> None:
    from tl_mod_documents.handlers.renditions import preflight_rendition

    world.issued_document()
    rev = world.revision("ISO-1234", "A")

    def check(kind: str, mode: str) -> None:
        with open_uow(world.db, readonly=True) as uow:
            preflight_rendition(uow.conn(), "project:P123", rev.id, kind, mode)  # type: ignore[arg-type]

    check("markup", "attach")
    check("signed", "register_signed")
    with pytest.raises(RenditionNotAllowedError, match="registered by a document controller"):
        check("signed", "attach")
    with pytest.raises(RenditionNotAllowedError, match="no signed copy to replace"):
        check("signed", "replace_signed")
    with pytest.raises(RenditionNotAllowedError, match="it accepts markup, signed"):
        check("pdf", "attach")
    with pytest.raises(RenditionNotAllowedError, match="only a signed copy"):
        check("markup", "register_signed")
    with pytest.raises(RevisionNotFoundError):
        with open_uow(world.db, readonly=True) as uow:
            preflight_rendition(uow.conn(), "project:P999", rev.id, "markup", "attach")
    doc = world.document("ISO-1234")
    with open_uow(world.db) as uow:
        handle_void_document(uow, VoidDocument(**BASE, stream_id=doc.id, reason="x"))
    for kind, mode in (("markup", "attach"), ("signed", "register_signed")):
        with pytest.raises(DocumentClosedError, match="takes no more changes"):
            check(kind, mode)
