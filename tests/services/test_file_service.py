"""The upload service against a real SQLite ledger and an in-memory object store (P0-I4-B)."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections
from tl_core.files import ObjectIntegrityError, ObjectNotFound, object_key
from tl_core.files.queries import FileInfo, get_file, list_files
from tl_core.files.scan import ScanResult
from tl_core.files.service import (
    AttachFile,
    CompleteUpload,
    FileResult,
    FileService,
    RegisterUpload,
    UploadTicket,
)
from tl_core.files.slots import FileSlot, FileSlotRegistry
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import (
    ContentRejectedError,
    FileQuarantinedError,
    FileRejectedError,
    FileTooLargeError,
    FileTypeNotAcceptedError,
    InvalidFileTransitionError,
    ObjectMissingError,
    RecordNotFoundError,
    RecordVoidedError,
    UnknownFileError,
    UnknownSlotError,
    UploadIncompleteError,
    UploadTokenError,
    UploadVerificationError,
)
from tl_core.services.records import handle_create_record

PROJECT = "project:P123"
OTHER_PROJECT = "project:P999"
ALICE = "user:alice"
BOB = "user:bob"
PDF = b"%PDF-1.7 report one"
PDF2 = b"%PDF-1.7 report two"
JPG = b"\xff\xd8\xff photo"


class FakeStore:
    """An in-memory ObjectStore that verifies like the real ones."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        body = data.read()
        if len(body) != size or hashlib.sha256(body).hexdigest() != sha256:
            raise ObjectIntegrityError(f"bytes for {key} differ from the declaration")
        self.puts.append(key)
        self.objects.setdefault(key, body)

    def get(self, key: str) -> BinaryIO:
        try:
            return io.BytesIO(self.objects[key])
        except KeyError:
            raise ObjectNotFound(key) from None

    def exists(self, key: str) -> bool:
        return key in self.objects

    def presign_put(self, key: str, *, expires_s: int) -> str:
        return f"fake://put/{key}?exp={expires_s}"

    def presign_get(self, key: str, *, expires_s: int) -> str:
        return f"fake://get/{key}?exp={expires_s}"

    def client_upload(self, url: str, body: bytes) -> None:
        """What a client does with the presigned URL: write the bytes at the staging key."""
        key = url.removeprefix("fake://put/").split("?")[0]
        self.objects[key] = body


class Rejecting:
    """A scanner that refuses everything."""

    def scan(self, data: BinaryIO, *, filename: str, content_type: str) -> ScanResult:
        return ScanResult(clean=False, reason="signature match", report={"scanner": "test"})


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


SLOTS = FileSlotRegistry(
    {
        "core.Record": [
            FileSlot(
                name="report", cardinality="one", accepted_types=["application/pdf"], max_size=64
            ),
            FileSlot(name="photo", cardinality="many", accepted_types=["image/*"]),
        ]
    }
)


class Env:
    """A ledger, a store and a service, with helpers that open one unit of work per call."""

    def __init__(self, db: DbTarget, **service_args: Any) -> None:
        self.db = db
        self.store = FakeStore()
        self.clock = Clock()
        self.service = FileService(
            self.store, secret=b"test-secret", slots=SLOTS, clock=self.clock, **service_args
        )

    def record(self, key: str = "REC-1", scope: str = PROJECT) -> str:
        with open_uow(self.db) as uow:
            return handle_create_record(
                uow,
                CreateRecord(
                    actor=ALICE,
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title=key,
                    key=key,
                ),
            ).stream_id

    def declared(
        self, record_id: str, body: bytes, slot: str | None, **over: Any
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "actor": ALICE,
            "source": "test",
            "scope": PROJECT,
            "record_id": record_id,
            "slot": slot,
            "filename": "doc.pdf",
            "content_type": "application/pdf",
            "size": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        fields.update(over)
        return fields

    def register(self, record_id: str, body: bytes, slot: str | None, **over: Any) -> UploadTicket:
        with open_uow(self.db) as uow:
            return self.service.register_upload(
                uow, RegisterUpload(**self.declared(record_id, body, slot, **over))
            )

    def complete(
        self,
        ticket: UploadTicket,
        data: bytes | None = None,
        *,
        actor: str = ALICE,
        scope: str = PROJECT,
    ) -> FileResult:
        with open_uow(self.db) as uow:
            return self.service.complete_upload(
                uow,
                CompleteUpload(actor=actor, source="test", scope=scope, upload_id=ticket.upload_id),
                io.BytesIO(data) if data is not None else None,
            )

    def put(self, record_id: str, body: bytes, slot: str | None, **over: Any) -> FileResult:
        """The whole flow with the bytes handed over directly."""
        ticket = self.register(record_id, body, slot, **over)
        return self.complete(
            ticket,
            None if ticket.exists else body,
            actor=over.get("actor", ALICE),
            scope=over.get("scope", PROJECT),
        )

    def attach(self, record_id: str, body: bytes, slot: str | None, **over: Any) -> FileResult:
        with open_uow(self.db) as uow:
            return self.service.attach_file(
                uow, AttachFile(**self.declared(record_id, body, slot, **over))
            )

    def files(self, record_id: str, **kwargs: Any) -> list[FileInfo]:
        with open_uow(self.db, readonly=True) as uow:
            return list_files(uow, PROJECT, record_id, **kwargs)

    def info(self, file_id: str) -> FileInfo:
        with open_uow(self.db, readonly=True) as uow:
            return get_file(uow, PROJECT, file_id)

    def event_types(self) -> list[str]:
        with open_uow(self.db, readonly=True) as uow:
            rows = uow.conn().execute(
                text("SELECT event_type FROM events WHERE event_type LIKE 'File.%' ORDER BY seq")
            )
            return [r.event_type for r in rows]


@pytest.fixture
def env(new_db: Callable[[], DbTarget]) -> Env:
    db = new_db()
    create_schema(db)
    return Env(db)


# --- the happy path ---------------------------------------------------------------------------


def test_upload_with_bytes_verifies_stores_attaches_and_releases(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, PDF, "report")
    assert result.status == "available"
    assert result.deduplicated is False and result.already_attached is False
    assert [e.event_type for e in result.events] == ["File.Uploaded", "File.Processed"]
    assert result.events[0].stream_type == "core.File"
    assert result.events[0].payload["status"] == "quarantined"
    key = object_key(hashlib.sha256(PDF).hexdigest())
    assert env.store.objects[key] == PDF
    (info,) = env.files(rec)
    assert (info.slot, info.revision, info.status, info.current) == ("report", 1, "available", True)
    assert info.size == len(PDF) and info.filename == "doc.pdf" and info.uploaded_by == ALICE
    assert env.event_types() == ["File.Uploaded", "File.Processed"]


def test_presigned_flow_pulls_the_staged_bytes_and_verifies_them(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    assert ticket.exists is False and ticket.upload_url is not None
    assert ticket.key == object_key(hashlib.sha256(PDF).hexdigest())
    env.store.client_upload(ticket.upload_url, PDF)
    result = env.complete(ticket)
    assert result.status == "available"
    assert env.store.objects[ticket.key] == PDF


def test_staged_bytes_that_differ_from_the_declaration_are_refused(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    assert ticket.upload_url is not None
    env.store.client_upload(ticket.upload_url, b"%PDF-1.7 something else")
    with pytest.raises(UploadVerificationError):
        env.complete(ticket)
    assert ticket.key not in env.store.objects
    assert env.files(rec) == [] and env.event_types() == []


def test_complete_without_any_bytes_is_incomplete(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    with pytest.raises(UploadIncompleteError):
        env.complete(ticket)


@pytest.mark.parametrize(
    "body", [b"short", PDF + b"!"], ids=["fewer bytes than declared", "more bytes than declared"]
)
def test_bytes_that_do_not_match_size_or_hash_never_become_visible(env: Env, body: bytes) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    with pytest.raises(UploadVerificationError):
        env.complete(ticket, body)
    assert env.store.objects == {} and env.files(rec) == [] and env.event_types() == []


def test_a_generic_attachment_needs_no_slot(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, b"minutes", None, filename="minutes.txt", content_type="text/plain")
    assert result.slot is None and result.status == "available"
    (info,) = env.files(rec)
    assert info.slot is None and info.current


def test_an_empty_file_is_a_file(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, b"", None, filename="empty.txt", content_type="text/plain")
    assert result.size == 0 and result.status == "available"


# --- declaration checks -----------------------------------------------------------------------


def test_slot_and_record_checks_refuse_before_anything_is_written(env: Env) -> None:
    rec = env.record()
    with pytest.raises(UnknownSlotError):
        env.register(rec, PDF, "nope")
    with pytest.raises(FileTypeNotAcceptedError):
        env.register(rec, PDF, "photo")
    with pytest.raises(FileTooLargeError):
        env.register(rec, b"x" * 65, "report")
    with pytest.raises(RecordNotFoundError):
        env.register("01ARZ3NDEKTSV4RRFFQ69G5FAV", PDF, "report")
    with pytest.raises(RecordNotFoundError):
        env.register(rec, PDF, "report", scope=OTHER_PROJECT)
    assert env.event_types() == []


def test_a_generic_attachment_is_limited_by_the_service_maximum(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    small = Env(db, max_unslotted_size=10)
    rec = small.record()
    with pytest.raises(FileTooLargeError):
        small.register(rec, b"x" * 11, None, content_type="text/plain")
    small.register(rec, b"x" * 10, None, content_type="text/plain")


def test_a_voided_record_takes_no_files(env: Env) -> None:
    from tl_core.services.commands import VoidRecord
    from tl_core.services.records import handle_void_record

    rec = env.record()
    with open_uow(env.db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor=ALICE,
                source="test",
                scope=PROJECT,
                stream_id=rec,
                expected_version=1,
                reason="duplicate",
            ),
        )
    with pytest.raises(RecordVoidedError):
        env.register(rec, PDF, "report")


def test_a_malformed_hash_is_a_validation_error(env: Env) -> None:
    from pydantic import ValidationError

    rec = env.record()
    with pytest.raises(ValidationError):
        env.register(rec, PDF, "report", sha256="not-a-digest")


# --- upload ids -------------------------------------------------------------------------------


def test_an_upload_id_is_bound_to_who_asked_for_it(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    with pytest.raises(UploadTokenError):
        env.complete(ticket, PDF, actor=BOB)
    with pytest.raises(UploadTokenError):
        env.complete(ticket, PDF, scope=OTHER_PROJECT)


def test_a_tampered_or_foreign_upload_id_is_refused(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    body, _, signature = ticket.upload_id.partition(".")
    forged = ticket.model_copy(update={"upload_id": body + "A." + signature})
    unsigned = ticket.model_copy(update={"upload_id": body})
    garbage = ticket.model_copy(update={"upload_id": "garbage"})
    other_server = FileService(env.store, secret=b"another-secret", slots=SLOTS, clock=env.clock)
    for bad in (forged, unsigned, garbage):
        with pytest.raises(UploadTokenError):
            env.complete(bad, PDF)
    with open_uow(env.db) as uow, pytest.raises(UploadTokenError):
        other_server.complete_upload(
            uow,
            CompleteUpload(actor=ALICE, source="test", scope=PROJECT, upload_id=ticket.upload_id),
            io.BytesIO(PDF),
        )


@pytest.mark.parametrize("suffix", ["é" * 64, "\ud800" * 3, ""])
def test_a_non_ascii_signature_is_a_token_error_not_a_crash(env: Env, suffix: str) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    body, _, _ = ticket.upload_id.partition(".")
    for upload_id in (f"{body}.{suffix}", f"{suffix}.{suffix}", f"{suffix}{body}.x"):
        with pytest.raises(UploadTokenError):
            env.complete(ticket.model_copy(update={"upload_id": upload_id}), PDF)


def test_an_upload_id_expires(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    env.clock.now += timedelta(hours=1, seconds=1)
    with pytest.raises(UploadTokenError):
        env.complete(ticket, PDF)


def test_completing_twice_is_a_retry_not_a_second_file(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")
    first = env.complete(ticket, PDF)
    again = env.complete(ticket, PDF)
    assert again.already_attached is True and again.file_id == first.file_id
    assert len(env.files(rec)) == 1
    assert env.event_types() == ["File.Uploaded", "File.Processed"]


# --- dedupe -----------------------------------------------------------------------------------


def test_the_same_bytes_in_the_same_scope_are_stored_once(env: Env) -> None:
    rec_a, rec_b = env.record("REC-1"), env.record("REC-2")
    env.put(rec_a, PDF, "report")
    ticket = env.register(rec_b, PDF, "report")
    assert ticket.exists is True and ticket.upload_url is None
    second = env.complete(ticket)
    assert second.deduplicated is True and second.status == "available"
    assert env.store.puts == [ticket.key]
    assert env.files(rec_b)[0].deduplicated is True


def test_attach_file_reuses_bytes_already_attached_in_the_scope(env: Env) -> None:
    rec_a, rec_b = env.record("REC-1"), env.record("REC-2")
    env.put(rec_a, PDF, "report")
    result = env.attach(rec_b, PDF, "report")
    assert result.deduplicated is True and result.status == "available"
    assert len(env.store.puts) == 1


def test_attach_file_refuses_bytes_this_scope_never_attached(env: Env) -> None:
    rec = env.record()
    with pytest.raises(UploadIncompleteError):
        env.attach(rec, PDF, "report")


def test_a_dedupe_hit_with_a_wrong_declared_size_is_refused(env: Env) -> None:
    rec_a, rec_b = env.record("REC-1"), env.record("REC-2")
    env.put(rec_a, PDF, "report")
    with pytest.raises(UploadVerificationError):
        env.attach(rec_b, PDF, "report", size=len(PDF) + 1)


def test_knowing_a_hash_is_not_enough_to_attach_another_scopes_file(env: Env) -> None:
    secret_rec = env.record("REC-1")
    env.put(secret_rec, PDF, "report")
    intruder_rec = env.record("REC-9", scope=OTHER_PROJECT)
    kwargs: dict[str, Any] = {"scope": OTHER_PROJECT}
    ticket = env.register(intruder_rec, PDF, "report", **kwargs)
    assert ticket.exists is False  # the client must show the bytes
    with pytest.raises(UploadIncompleteError):
        env.complete(ticket, scope=OTHER_PROJECT)
    with pytest.raises(UploadVerificationError):
        env.complete(ticket, b"%PDF-1.7 a guess!!", scope=OTHER_PROJECT)
    result = env.complete(ticket, PDF, scope=OTHER_PROJECT)  # proves possession
    assert result.deduplicated is True
    assert env.store.puts == [ticket.key]  # the object is stored once


def test_a_quarantined_hash_cannot_be_deduped_without_bytes(new_db: Callable[[], DbTarget]) -> None:
    db = new_db()
    create_schema(db)
    env = Env(db, scan_inline=False)
    rec_a, rec_b = env.record("REC-1"), env.record("REC-2")
    first = env.put(rec_a, PDF, "report")  # Alice's file waits in quarantine
    assert first.status == "quarantined"
    ticket = env.register(rec_b, PDF, "report", actor=BOB)
    assert ticket.exists is False  # Bob must show the bytes
    with pytest.raises(UploadIncompleteError):
        env.complete(ticket, actor=BOB)
    with pytest.raises(UploadIncompleteError):
        env.attach(rec_b, PDF, "report", actor=BOB)
    # Without bytes Bob can neither attach nor read Alice's quarantined file.
    with open_uow(db, readonly=True) as uow, pytest.raises(FileQuarantinedError):
        env.service.open_file(uow, PROJECT, first.file_id, actor=BOB)
    # Once Alice's file is released the hash can be deduped without bytes.
    with open_uow(db) as uow:
        env.service.scan_pending(uow)
    ticket = env.register(rec_b, PDF, "report", actor=BOB)
    assert ticket.exists is True
    result = env.complete(ticket, actor=BOB)
    assert result.deduplicated is True and len(env.store.puts) == 1


def test_an_already_attached_answer_does_not_expose_anothers_quarantined_file(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    env = Env(db, scan_inline=False)
    rec = env.record()
    alice = env.put(rec, PDF, "report")
    with pytest.raises(UploadIncompleteError):
        env.attach(rec, PDF, "report", actor=BOB)  # not "already attached": Alice's is hidden
    again = env.put(rec, PDF, "report")  # Alice's own retry is recognised
    assert again.already_attached and again.file_id == alice.file_id


def test_an_object_in_the_store_is_never_replaced(env: Env) -> None:
    rec_a, rec_b = env.record("REC-1"), env.record("REC-2")
    env.put(rec_a, PDF, "report")
    key = object_key(hashlib.sha256(PDF).hexdigest())
    before = env.store.objects[key]
    env.put(rec_b, PDF, "report")
    assert env.store.objects[key] is before


def test_a_missing_object_is_restored_by_the_next_upload_of_the_same_bytes(env: Env) -> None:
    rec_a, rec_b = env.record("REC-1"), env.record("REC-2")
    env.put(rec_a, PDF, "report")
    key = object_key(hashlib.sha256(PDF).hexdigest())
    del env.store.objects[key]  # the store lost it
    ticket = env.register(rec_b, PDF, "report")
    assert ticket.exists is False
    env.complete(ticket, PDF)
    assert env.store.objects[key] == PDF


def test_reuploading_to_the_same_slot_restores_a_lost_object(env: Env) -> None:
    rec = env.record()
    first = env.put(rec, PDF, "report")
    del env.store.objects[object_key(first.sha256)]  # the store lost it; the ledger row stays
    ticket = env.register(rec, PDF, "report")
    assert ticket.exists is False
    with pytest.raises(UploadIncompleteError):
        env.complete(ticket)  # nothing to restore from
    again = env.complete(ticket, PDF)
    assert again.already_attached and again.file_id == first.file_id
    assert env.store.objects[object_key(first.sha256)] == PDF
    assert len(env.files(rec)) == 1 and env.event_types() == ["File.Uploaded", "File.Processed"]


def test_a_restore_still_verifies_the_bytes(env: Env) -> None:
    rec = env.record()
    first = env.put(rec, PDF, "report")
    del env.store.objects[object_key(first.sha256)]
    ticket = env.register(rec, PDF, "report")
    with pytest.raises(UploadVerificationError):
        env.complete(ticket, b"%PDF-1.7 not the same")
    assert object_key(first.sha256) not in env.store.objects


# --- slot cardinality and revisions -----------------------------------------------------------


def test_a_new_file_in_a_one_slot_supersedes_the_previous_current_file(env: Env) -> None:
    rec = env.record()
    first = env.put(rec, PDF, "report")
    second = env.put(rec, PDF2, "report")
    assert (first.revision, second.revision) == (1, 2)
    everything = {f.file_id: f for f in env.files(rec)}
    assert everything[first.file_id].superseded_by == second.file_id
    assert everything[first.file_id].current is False
    assert everything[second.file_id].current is True
    assert [f.file_id for f in env.files(rec, current_only=True)] == [second.file_id]
    assert env.store.objects[object_key(hashlib.sha256(PDF).hexdigest())] == PDF  # old stays


def test_every_file_of_a_many_slot_is_current(env: Env) -> None:
    rec = env.record()
    one = env.put(rec, JPG, "photo", content_type="image/jpeg", filename="a.jpg")
    two = env.put(rec, JPG + b"2", "photo", content_type="image/jpeg", filename="b.jpg")
    current = env.files(rec, current_only=True, slot="photo")
    assert [f.file_id for f in current] == [one.file_id, two.file_id]


def test_revisions_count_per_slot(env: Env) -> None:
    rec = env.record()
    env.put(rec, PDF, "report")
    photo = env.put(rec, JPG, "photo", content_type="image/jpeg")
    plain = env.put(rec, b"note", None, content_type="text/plain")
    assert photo.revision == 1 and plain.revision == 1


def test_uploading_the_same_bytes_again_to_a_slot_attaches_nothing_new(env: Env) -> None:
    rec = env.record()
    first = env.put(rec, PDF, "report")
    again = env.put(rec, PDF, "report")
    assert again.already_attached and again.file_id == first.file_id
    assert len(env.files(rec)) == 1


# --- quarantine -------------------------------------------------------------------------------


def test_a_quarantined_file_is_readable_only_by_its_uploader_until_the_scan_passes(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    env = Env(db, scan_inline=False)
    rec = env.record()
    result = env.put(rec, PDF, "report")
    assert result.status == "quarantined"
    assert [e.event_type for e in result.events] == ["File.Uploaded"]
    with open_uow(db, readonly=True) as uow:
        with pytest.raises(FileQuarantinedError):
            env.service.open_file(uow, PROJECT, result.file_id, actor=BOB)
        with pytest.raises(FileQuarantinedError):
            env.service.presign_download(uow, PROJECT, result.file_id, actor=BOB)
        mine = env.service.open_file(uow, PROJECT, result.file_id, actor=ALICE)
        assert mine.data.read() == PDF
    assert env.files(rec, current_only=True) == []  # not current until released
    with open_uow(db) as uow:
        released = env.service.scan_pending(uow)
    assert [r.status for r in released] == ["available"]
    assert [e.event_type for e in released[0].events] == ["File.Processed"]
    with open_uow(db, readonly=True) as uow:
        assert env.service.open_file(uow, PROJECT, result.file_id, actor=BOB).data.read() == PDF
    assert env.event_types() == ["File.Uploaded", "File.Processed"]


def test_a_quarantined_upload_does_not_replace_the_current_file(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    env = Env(db, scan_inline=False)
    rec = env.record()
    first = env.put(rec, PDF, "report")
    with open_uow(db) as uow:
        env.service.scan_pending(uow)
    second = env.put(rec, PDF2, "report")
    assert [f.file_id for f in env.files(rec, current_only=True)] == [first.file_id]
    with open_uow(db) as uow:
        env.service.scan_pending(uow)
    assert [f.file_id for f in env.files(rec, current_only=True)] == [second.file_id]


def test_a_rejected_file_is_unreadable_and_its_bytes_cannot_come_back(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    env = Env(db)
    env.service = FileService(
        env.store, secret=b"test-secret", slots=SLOTS, clock=env.clock, scanner=Rejecting()
    )
    rec = env.record()
    result = env.put(rec, PDF, "report")
    assert result.status == "rejected"
    assert [e.event_type for e in result.events] == ["File.Uploaded", "File.Rejected"]
    assert result.events[1].payload["reason"] == "signature match"
    with open_uow(db, readonly=True) as uow:
        with pytest.raises(FileRejectedError):
            env.service.open_file(uow, PROJECT, result.file_id, actor=ALICE)
    assert env.info(result.file_id).reason == "signature match"
    with pytest.raises(ContentRejectedError):
        env.register(rec, PDF, "report")


def test_a_rejected_replacement_leaves_the_previous_file_current(
    new_db: Callable[[], DbTarget],
) -> None:
    db = new_db()
    create_schema(db)
    env = Env(db)
    rec = env.record()
    good = env.put(rec, PDF, "report")
    env.service = FileService(
        env.store, secret=b"test-secret", slots=SLOTS, clock=env.clock, scanner=Rejecting()
    )
    bad = env.put(rec, PDF2, "report")
    assert bad.status == "rejected"
    assert [f.file_id for f in env.files(rec, current_only=True)] == [good.file_id]


def test_only_a_quarantined_file_can_be_scanned(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, PDF, "report")
    with open_uow(env.db) as uow, pytest.raises(InvalidFileTransitionError):
        env.service.scan_file(uow, PROJECT, result.file_id)


# --- reading ----------------------------------------------------------------------------------


def test_open_file_returns_the_bytes_and_download_urls_follow_the_same_rules(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, PDF, "report")
    with open_uow(env.db, readonly=True) as uow:
        opened = env.service.open_file(uow, PROJECT, result.file_id, actor=BOB)
        assert opened.data.read() == PDF and opened.info.filename == "doc.pdf"
        url = env.service.presign_download(uow, PROJECT, result.file_id, actor=BOB, expires_s=60)
    assert url == f"fake://get/{object_key(result.sha256)}?exp=60"


def test_open_file_names_the_runbook_when_the_object_is_gone(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, PDF, "report")
    del env.store.objects[object_key(result.sha256)]
    with open_uow(env.db, readonly=True) as uow, pytest.raises(ObjectMissingError, match="runbook"):
        env.service.open_file(uow, PROJECT, result.file_id, actor=ALICE)


def test_an_unknown_file_or_another_scope_is_not_found(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, PDF, "report")
    with open_uow(env.db, readonly=True) as uow:
        with pytest.raises(UnknownFileError):
            env.service.open_file(uow, PROJECT, "01ARZ3NDEKTSV4RRFFQ69G5FAV", actor=ALICE)
        with pytest.raises(UnknownFileError):
            env.service.open_file(uow, OTHER_PROJECT, result.file_id, actor=ALICE)


# --- ledger behaviour -------------------------------------------------------------------------


def test_the_attachment_and_its_events_commit_or_roll_back_together(env: Env) -> None:
    rec = env.record()
    ticket = env.register(rec, PDF, "report")

    class Boom(Exception): ...

    with pytest.raises(Boom), open_uow(env.db) as uow:
        env.service.complete_upload(
            uow,
            CompleteUpload(actor=ALICE, source="test", scope=PROJECT, upload_id=ticket.upload_id),
            io.BytesIO(PDF),
        )
        raise Boom
    assert env.files(rec) == [] and env.event_types() == []
    # The object stays (content-addressed, harmless); a retry attaches without a second put.
    assert ticket.key in env.store.objects
    result = env.complete(ticket, PDF)
    assert result.status == "available"


def test_cur_files_rebuilds_identically_from_the_ledger(env: Env) -> None:
    rec = env.record()
    env.put(rec, PDF, "report")
    env.put(rec, PDF2, "report")
    env.put(rec, JPG, "photo", content_type="image/jpeg")
    env.put(rec, b"note", None, content_type="text/plain")

    def snapshot() -> list[tuple[Any, ...]]:
        with open_uow(env.db, readonly=True) as uow:
            return [
                tuple(r)
                for r in uow.conn().execute(text("SELECT * FROM cur_files ORDER BY file_id"))
            ]

    before = snapshot()
    assert len(before) == 4
    rebuild_projections(env.db)
    assert snapshot() == before


def test_every_file_event_carries_the_same_correlation_id_within_one_upload(env: Env) -> None:
    rec = env.record()
    result = env.put(rec, PDF, "report")
    assert len({e.correlation_id for e in result.events}) == 1
    assert result.events[1].actor == "svc:scanner" and result.events[0].actor == ALICE
