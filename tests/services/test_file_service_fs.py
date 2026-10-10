"""The upload service on the real fs store, with the repository's default file slots (P0-I4-B)."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.required import missing_required_files
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import FileTypeNotAcceptedError
from tl_core.services.records import handle_create_record

SCOPE = "project:P123"
PDF = b"%PDF-1.7 integration"


@pytest.fixture
def setup(
    tmp_path: Path, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> tuple[DbTarget, FileService, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository fixture slots
    db = new_db()
    create_schema(db)
    store = FsObjectStore(tmp_path / "objects", secret=b"k")
    service = FileService(store, secret=b"s")  # slots=None: default_file_slots()
    with open_uow(db) as uow:
        record = handle_create_record(
            uow,
            CreateRecord(
                actor="user:a",
                source="test",
                scope=SCOPE,
                record_type="core.Record",
                title="R",
                key="REC-1",
            ),
        ).stream_id
    return db, service, record


def declared(record: str, body: bytes, slot: str, content_type: str) -> RegisterUpload:
    return RegisterUpload(
        actor="user:a",
        source="test",
        scope=SCOPE,
        record_id=record,
        slot=slot,
        filename="f",
        content_type=content_type,
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
    )


def test_presigned_upload_into_a_default_slot_satisfies_the_requirement(
    setup: tuple[DbTarget, FileService, str],
) -> None:
    db, service, record = setup
    with open_uow(db) as uow:
        assert [m.slot.name for m in missing_required_files(uow, record)] == ["report"]
        ticket = service.register_upload(uow, declared(record, PDF, "report", "application/pdf"))
    assert ticket.upload_url is not None
    store = service._store  # pyright: ignore[reportPrivateUsage]
    assert isinstance(store, FsObjectStore)
    store.put_via_url(ticket.upload_url, io.BytesIO(PDF))  # the client's side of the URL
    with open_uow(db) as uow:
        result = service.complete_upload(
            uow,
            CompleteUpload(actor="user:a", source="test", scope=SCOPE, upload_id=ticket.upload_id),
        )
    assert result.status == "available"
    with open_uow(db, readonly=True) as uow:
        assert missing_required_files(uow, record) == []
        opened = service.open_file(uow, SCOPE, result.file_id, actor="user:b")
        assert opened.data.read() == PDF
    assert len([k for k in store.iter_keys() if k.startswith("sha256/")]) == 1


def test_the_default_slots_refuse_a_wrong_type(setup: tuple[DbTarget, FileService, str]) -> None:
    db, service, record = setup
    with open_uow(db) as uow, pytest.raises(FileTypeNotAcceptedError):
        service.register_upload(uow, declared(record, PDF, "photo", "application/pdf"))
