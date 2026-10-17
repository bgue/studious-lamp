"""Who may put which file on a derived document (ADR-0014; `by_module` of the file service)."""

from __future__ import annotations

import hashlib
import io

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.files.service import AttachFile, CompleteUpload, RegisterUpload
from tl_core.services.errors import UnsupportedRecordTypeError
from tl_core.util import new_ulid
from tl_mod_documents.testing import forge

CSV = b"tag,size\n47-FV-1001,4\n"
JSON = b'{"rows": []}'


@pytest.fixture
def derived(world: World) -> str:
    world.register()
    world.create_revision()
    doc, rev = world.document("ISO-1234"), world.revision("ISO-1234", "A")
    schema_id, derived_id = new_ulid(), new_ulid()
    forge(
        world,
        schema_id,
        "documents.DocumentSchema",
        "idx@1.0.0",
        [
            (
                "DocumentSchema.Defined",
                {
                    "code": "idx",
                    "semver": "1.0.0",
                    "ordinal": 1,
                    "json_schema": {"type": "object"},
                    "content_hash": "ab" * 32,
                },
            )
        ],
    )
    forge(
        world,
        derived_id,
        "documents.DerivedDocument",
        "ISO-1234@A/idx",
        [
            (
                "DerivedDocument.Defined",
                {
                    "source_document_id": doc.id,
                    "source_revision_id": rev.id,
                    "source_document_number": "ISO-1234",
                    "source_revision_code": "A",
                    "source_ref": "src.doc.ISO-1234@A",
                    "schema_id": schema_id,
                    "schema_code": "idx",
                    "schema_version": "1.0.0",
                    "method": "manual",
                },
            )
        ],
    )
    return derived_id


def declared(record_id: str, slot: str, data: bytes, content_type: str) -> RegisterUpload:
    return RegisterUpload(
        **BASE,
        record_id=record_id,
        slot=slot,
        filename="f.dat",
        content_type=content_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def test_a_person_may_attach_content_but_not_the_slots_the_module_writes(
    world: World, derived: str
) -> None:
    with open_uow(world.db) as uow:
        ticket = world.files.register_upload(uow, declared(derived, "content", CSV, "text/csv"))
    with open_uow(world.db) as uow:
        done = world.files.complete_upload(
            uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(CSV)
        )
    assert done.status == "available" and done.slot == "content"
    refused = [
        declared(derived, "extracted", JSON, "application/json"),
        declared(derived, "report", JSON, "application/json"),
        declared(derived, "nonsense", JSON, "application/json"),
        declared(derived, "content", CSV, "text/csv").model_copy(update={"slot": None}),
    ]
    for declaration in refused:
        with open_uow(world.db) as uow, pytest.raises(UnsupportedRecordTypeError):
            world.files.register_upload(uow, declaration)


def test_the_module_may_write_the_slots_a_person_may_not(world: World, derived: str) -> None:
    for slot in ("extracted", "report"):
        with open_uow(world.db) as uow:
            ticket = world.files.register_upload(
                uow, declared(derived, slot, JSON, "application/json"), by_module=True
            )
        with open_uow(world.db) as uow:
            done = world.files.complete_upload(
                uow,
                CompleteUpload(**BASE, upload_id=ticket.upload_id),
                io.BytesIO(JSON),
                by_module=True,
            )
        assert done.status == "available" and done.slot == slot


def test_by_module_skips_only_the_allow_list_not_the_slot_rules(world: World, derived: str) -> None:
    from tl_core.services.errors import FileTypeNotAcceptedError, UnknownSlotError

    with open_uow(world.db) as uow, pytest.raises(UnknownSlotError):
        world.files.register_upload(
            uow, declared(derived, "nope", JSON, "application/json"), by_module=True
        )
    with open_uow(world.db) as uow, pytest.raises(FileTypeNotAcceptedError):
        world.files.register_upload(
            uow, declared(derived, "extracted", CSV, "text/csv"), by_module=True
        )


def test_a_person_cannot_attach_to_a_derived_document_that_is_published_or_running(
    world: World, derived: str
) -> None:
    world.move(derived, "start")  # Processing
    with open_uow(world.db) as uow, pytest.raises(UnsupportedRecordTypeError, match="Processing"):
        world.files.register_upload(uow, declared(derived, "content", CSV, "text/csv"))


def test_by_module_is_a_python_argument_not_a_field_of_any_upload_command() -> None:
    for model in (RegisterUpload, CompleteUpload, AttachFile):
        assert "by_module" not in model.model_fields
        assert model.model_config.get("extra") != "allow"
