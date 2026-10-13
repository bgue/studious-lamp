"""Document commands against a real ledger on every adapter (T04): register to void."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from docworld import BASE, PROJECT, World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.services.errors import DuplicateKeyError, NoChangesError, RecordNotFoundError
from tl_mod_documents.errors import (
    DocumentClosedError,
    DocumentNotFoundError,
    InvalidDocumentNumberError,
    InvalidDocumentTypeError,
    ProjectScopeError,
    UnknownSchemeError,
)
from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    SupersedeDocument,
    UpdateDocument,
    VoidDocument,
    handle_register_document,
    handle_supersede_document,
    handle_update_document,
    handle_void_document,
)
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

STANDARDS = Path(__file__).resolve().parents[4] / "schema" / "fixtures" / "standards"


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


def load_registry(world: World) -> None:
    """The acme standards and the acme document pattern, as `tl standards load` does."""
    for name in ("co.acme.standards@1.0.0.yaml", "co.acme.documents@1.0.0.yaml"):
        with open_uow(world.db) as uow:
            load_standards(
                uow, load_standards_file(STANDARDS / name), actor="user:admin", source="test"
            )


def test_registering_a_document_makes_it_registered_with_the_scheme_of_its_type(
    world: World,
) -> None:
    made = world.register("SPC-0001", doc_type="SPC", title="Piping specification")
    assert made.key == "SPC-0001"
    doc = world.document("SPC-0001")
    assert doc.state == "Registered" and not doc.voided
    assert doc.revision_scheme == "numeric"  # the company rule for specifications
    assert doc.current_revision_id is None
    assert doc.title == "Piping specification"
    types = [e.event_type for e in made.events]
    assert types == ["Record.Created", "Document.Defined", "Workflow.Transitioned"]


def test_a_document_can_name_its_scheme(world: World) -> None:
    world.register("ISO-1001", revision_scheme="staged")
    assert world.document("ISO-1001").revision_scheme == "staged"
    with pytest.raises(UnknownSchemeError):
        world.register("ISO-1002", revision_scheme="roman")


def test_the_same_number_cannot_be_registered_twice(world: World) -> None:
    world.register()
    with pytest.raises(DuplicateKeyError):
        world.register()


def test_documents_belong_to_a_project(world: World) -> None:
    with pytest.raises(ProjectScopeError):
        run(
            world,
            handle_register_document,
            RegisterDocument(**{**BASE, "scope": "company"}, number="X-1", title="t"),
        )


def test_the_command_refuses_fields_it_does_not_have(world: World) -> None:
    with pytest.raises(ValidationError):
        RegisterDocument(**BASE, number="X-1", title="t", origin="import")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        RegisterDocument(**BASE, number="X-1", title="   ")
    with pytest.raises(ValidationError):
        RegisterDocument(**BASE, number="N" * 129, title="t")


def test_the_registry_pattern_checks_the_number_and_lists_every_problem(world: World) -> None:
    load_registry(world)
    world.register("ISO-1234")
    assert world.document("ISO-1234").pattern_code == "document"
    with pytest.raises(InvalidDocumentNumberError) as short:
        world.register("ISO-12", doc_type=None)
    assert any(i["rule"] == "sequence" for i in short.value.issues)
    with pytest.raises(InvalidDocumentNumberError) as unknown:
        world.register("XXX-1234", doc_type=None)
    assert any(i["rule"] == "unknown_code" for i in unknown.value.issues)
    with pytest.raises(InvalidDocumentNumberError):
        world.register("1234", doc_type=None)


def test_type_and_discipline_must_be_usable_values_when_the_lists_are_registered(
    world: World,
) -> None:
    world.register("ISO-0001", doc_type="NOPE")  # no registry yet: any text is accepted
    load_registry(world)
    with pytest.raises(InvalidDocumentTypeError, match="document type 'NOPE'"):
        world.register("ISO-0002", doc_type="NOPE")
    with pytest.raises(InvalidDocumentTypeError, match="discipline 'XXX'"):
        world.register("ISO-0003", doc_type="ISO", discipline="XXX")
    world.register("ISO-0004", doc_type="ISO", discipline="PIP")


def test_update_changes_title_and_register_fields_in_one_append(world: World) -> None:
    made = world.register(originator="Acme")
    doc = world.document("ISO-1234")
    result = run(
        world,
        handle_update_document,
        UpdateDocument(
            **BASE,
            stream_id=doc.id,
            expected_version=doc.version,
            title="Isometric, line 47-P-102",
            discipline="MEC",
            originator=None,
            reason="re-assigned",
        ),
    )
    assert [e.event_type for e in result.events] == ["Record.Updated", "Document.Updated"]
    changed = world.document("ISO-1234")
    assert changed.title == "Isometric, line 47-P-102"
    assert changed.discipline == "MEC" and changed.originator is None
    assert changed.doc_type == "ISO"  # untouched
    assert made.stream_id == changed.id


def test_update_with_nothing_different_is_refused(world: World) -> None:
    world.register()
    doc = world.document("ISO-1234")
    with pytest.raises(NoChangesError):
        run(
            world,
            handle_update_document,
            UpdateDocument(**BASE, stream_id=doc.id, title=doc.title, doc_type="ISO"),
        )


def test_update_refuses_a_stale_version_and_a_foreign_scope(world: World) -> None:
    from tl_core.ledger import ConcurrencyError

    world.register()
    doc = world.document("ISO-1234")
    with pytest.raises(ConcurrencyError):
        run(
            world,
            handle_update_document,
            UpdateDocument(**BASE, stream_id=doc.id, expected_version=1, title="x"),
        )
    with pytest.raises(DocumentNotFoundError):
        run(
            world,
            handle_update_document,
            UpdateDocument(**{**BASE, "scope": "project:P999"}, stream_id=doc.id, title="x"),
        )


def test_void_ends_the_document_and_flags_every_link_to_it(world: World) -> None:
    world.issued_document()
    tag = world.tag()
    pinned = world.link(tag, "ISO-1234", "A")
    floating = world.link(world.tag("47-FV-1002"), "ISO-1234", None)
    doc = world.document("ISO-1234")
    result = run(
        world,
        handle_void_document,
        VoidDocument(**BASE, stream_id=doc.id, reason="registered in error"),
    )
    assert [e.event_type for e in result.events] == [
        "Workflow.Transitioned",
        "Record.Voided",
        "Link.Flagged",
        "Link.Flagged",
    ]
    voided = world.document("ISO-1234")
    assert voided.state == "Void" and voided.voided and voided.closed
    assert world.link_status(pinned) == "stale"
    assert world.link_status(floating) == "stale"  # a floating link has nothing to float to
    with pytest.raises(DocumentClosedError):
        run(world, handle_void_document, VoidDocument(**BASE, stream_id=doc.id, reason="again"))
    with pytest.raises(DocumentClosedError):
        world.create_revision()


def test_supersede_links_the_new_document_and_flags_the_old_ones_links(world: World) -> None:
    world.issued_document("ISO-1234")
    world.register("ISO-2000", title="Replacement isometric")
    old, new = world.document("ISO-1234"), world.document("ISO-2000")
    tag = world.tag()
    link = world.link(tag, "ISO-1234", "A")
    run(
        world,
        handle_supersede_document,
        SupersedeDocument(**BASE, stream_id=old.id, superseded_by_id=new.id, reason="re-drawn"),
    )
    after = world.document("ISO-1234")
    assert after.state == "Superseded" and after.superseded_by == new.id and not after.voided
    assert world.link_status(link) == "stale"
    supersedes = world.rows(
        "SELECT status FROM cur_links "
        "WHERE from_id = :f AND to_id = :t AND relation = 'supersedes'",
        f=new.id,
        t=old.id,
    )
    assert supersedes == [{"status": "active"}]
    with pytest.raises(DocumentClosedError):
        world.create_revision("ISO-1234")


def test_a_document_cannot_supersede_itself_or_be_replaced_by_a_closed_one(world: World) -> None:
    world.register("ISO-1")
    world.register("ISO-2")
    a, b = world.document("ISO-1"), world.document("ISO-2")
    with pytest.raises(NoChangesError):
        run(
            world,
            handle_supersede_document,
            SupersedeDocument(**BASE, stream_id=a.id, superseded_by_id=a.id, reason="x"),
        )
    run(world, handle_void_document, VoidDocument(**BASE, stream_id=b.id, reason="oops"))
    with pytest.raises(DocumentClosedError):
        run(
            world,
            handle_supersede_document,
            SupersedeDocument(**BASE, stream_id=a.id, superseded_by_id=b.id, reason="x"),
        )
    with pytest.raises(DocumentNotFoundError):
        run(
            world,
            handle_supersede_document,
            SupersedeDocument(**BASE, stream_id=a.id, superseded_by_id="nope", reason="x"),
        )


def test_a_record_of_another_scope_is_not_found(world: World) -> None:
    world.register()
    doc = world.document("ISO-1234")
    with pytest.raises(DocumentNotFoundError):
        run(
            world,
            handle_void_document,
            VoidDocument(**{**BASE, "scope": "project:P999"}, stream_id=doc.id, reason="x"),
        )
    assert RecordNotFoundError  # the generic error type stays importable for callers
    assert PROJECT == "project:P123"
