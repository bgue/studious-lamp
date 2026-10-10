"""The upload service: register, complete, attach, scan, open (brief 20.2, 5.2).

Flow (brief 20.2): the client computes SHA-256 and size and calls ``register_upload``; the server
answers with a dedupe hit or a presigned URL; the bytes arrive (through the URL into a staging
key, or handed to ``complete_upload`` directly); ``complete_upload`` verifies hash and size on the
server, stores the object under its content key, appends ``File.Uploaded`` (quarantined) on a new
``core.File`` stream, and, when ``scan_inline`` is on, runs the scanner and appends
``File.Processed`` or ``File.Rejected`` in the same unit of work. Either way the attachment to the
record's slot (the ``cur_files`` row) is written by the projector inside that unit of work, so the
object-store write is the only effect outside the transaction.

Rules this module owns:

* Client-declared size and hash are never trusted. Bytes are verified before an object becomes
  visible (the store's ``put``), and a dedupe hit is checked against the size the ledger holds.
* Objects are never replaced; a new revision is a new object and a new file row.
* Dedupe without bytes is allowed only for a hash already *available* (scan passed) in the same
  scope, so knowing a hash is not enough to read someone else's file, quarantined or not.
  Otherwise the bytes must be shown once.
* Bytes whose hash was rejected by a scan are refused (``ContentRejectedError``). The check is
  deliberately global: known-bad content is bad in every scope, at the price of letting a caller
  learn that some scope had these bytes rejected.
* A quarantined file is readable only by its uploader; a rejected one by nobody.
* Completing the same upload twice (a retry) attaches nothing new and reports ``already_attached``.

An object written before a unit of work that then rolls back stays in the store unreferenced; the
reconciliation job lists such orphans. Presigned-upload staging objects are not deleted here (the
``ObjectStore`` Protocol has no delete); expire the ``staging/`` prefix with a bucket lifecycle
rule.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, BinaryIO

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from tl_core.files.errors import ObjectIntegrityError
from tl_core.files.lifecycle import FILE_STREAM_TYPE, next_file_status
from tl_core.files.queries import FileInfo, get_file
from tl_core.files.scan import PassScanner, Scanner, ScanResult
from tl_core.files.slots import FileSlotRegistry, default_file_slots
from tl_core.files.types import ObjectNotFound, ObjectStore, object_key
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command
from tl_core.services.errors import (
    ContentRejectedError,
    FileQuarantinedError,
    FileRejectedError,
    FileTooLargeError,
    FileTypeNotAcceptedError,
    ObjectMissingError,
    RecordNotFoundError,
    RecordVoidedError,
    UnknownSlotError,
    UploadIncompleteError,
    UploadTokenError,
    UploadVerificationError,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

#: Limit for a generic (unslotted) attachment: 5 GiB.
DEFAULT_MAX_UNSLOTTED_SIZE = 5 * 1024**3
SCANNER_ACTOR = "svc:scanner"
_TOKEN_VERSION = 1
_CHUNK = 1024 * 1024


class _Declared(Command):
    """What a client declares about the bytes: validated here, verified on the server."""

    record_id: str
    slot: str | None = None  # None: a generic, unslotted attachment
    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha256: str  # hex digest of the bytes

    @field_validator("sha256")
    @classmethod
    def _check_digest(cls, value: str) -> str:
        object_key(value)  # raises ValueError for anything but 64 hex digits
        return value.lower()


class RegisterUpload(_Declared):
    """``POST /uploads``: announce a file for a record slot."""


class AttachFile(_Declared):
    """Attach bytes that are already attached in this scope (dedupe), without an upload."""


class CompleteUpload(Command):
    """``POST /uploads/{id}/complete``."""

    upload_id: str


class UploadTicket(BaseModel):
    upload_id: str  # signed, expiring; bound to the actor, scope, record, slot, hash and size
    key: str  # the content-addressed object key
    exists: bool  # True: no bytes needed, call ``complete_upload`` without data
    upload_url: str | None  # presigned PUT to a staging key; None when ``exists``
    expires_at: datetime


class FileResult(BaseModel):
    file_id: str
    record_id: str
    slot: str | None
    revision: int
    sha256: str
    size: int
    status: str  # quarantined | available | rejected
    deduplicated: bool  # the object was already in the store
    already_attached: bool = False  # a retry: the same bytes were already attached here
    events: list[Event] = []


@dataclass
class OpenedFile:
    """A file's metadata and an open stream. The caller closes ``data``."""

    info: FileInfo
    data: BinaryIO


@dataclass(frozen=True)
class _Record:
    id: str
    type: str


_RECORD_SQL = text("SELECT id, type, scope, voided FROM cur_core_record WHERE id = :id")
_KNOWN_SQL = text(
    "SELECT size FROM cur_files WHERE sha256 = :sha256 AND scope = :scope "
    "AND status = 'available' ORDER BY uploaded_at LIMIT 1"
)
_REJECTED_SQL = text("SELECT 1 FROM cur_files WHERE sha256 = :sha256 AND status = 'rejected'")
_SAME_SQL = (
    "SELECT file_id FROM cur_files WHERE record_id = :record_id AND sha256 = :sha256 "
    "AND status <> 'rejected' AND superseded_by IS NULL "
    "AND (status = 'available' OR uploaded_by = :actor)"
)
_MAX_REVISION_SQL = "SELECT COALESCE(MAX(revision), 0) FROM cur_files WHERE record_id = :record_id"
_FILE_SQL = text(
    "SELECT file_id, scope, record_id, slot, status, version, sha256, filename, content_type "
    "FROM cur_files WHERE file_id = :file_id"
)
_CURRENT_IN_SLOT_SQL = text(
    "SELECT file_id FROM cur_files WHERE record_id = :record_id AND slot = :slot "
    "AND status = 'available' AND superseded_by IS NULL AND file_id <> :file_id "
    "ORDER BY revision, file_id"
)
_PENDING_SQL = (
    "SELECT file_id, scope FROM cur_files WHERE status = 'quarantined'{scope} "
    "ORDER BY uploaded_at, file_id LIMIT :limit"
)


def _wire(text_value: str) -> bytes:
    """Client-supplied token text as bytes, never raising on odd characters."""
    return text_value.encode("utf-8", errors="replace")


def hash_stream(data: BinaryIO) -> tuple[str, int]:
    """SHA-256 hex digest and byte count of a stream, read to its end in chunks."""
    digest = hashlib.sha256()
    count = 0
    while chunk := data.read(_CHUNK):
        digest.update(chunk)
        count += len(chunk)
    return digest.hexdigest(), count


class FileService:
    """Upload and file operations for one object store. Methods take an entered unit of work.

    ``secret`` signs upload ids (keep it out of the repository; ``TL_OBJECT_SECRET`` in the CLI).
    With ``scan_inline`` (the default) ``complete_upload`` scans before returning; turn it off when
    a real scanner is slow and run ``scan_pending`` from a worker, so files wait in quarantine.
    """

    def __init__(
        self,
        store: ObjectStore,
        *,
        secret: bytes,
        scanner: Scanner | None = None,
        slots: FileSlotRegistry | None = None,
        scan_inline: bool = True,
        upload_ttl_s: int = 3600,
        max_unslotted_size: int = DEFAULT_MAX_UNSLOTTED_SIZE,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        if not secret:
            raise ValueError("secret must not be empty")
        self._store = store
        self._secret = secret
        self._scanner: Scanner = scanner if scanner is not None else PassScanner()
        self._slots = slots
        self._scan_inline = scan_inline
        self._ttl = upload_ttl_s
        self._max_unslotted = max_unslotted_size
        self._clock = clock

    # --- upload flow ------------------------------------------------------------------------

    def register_upload(self, uow: UnitOfWork, cmd: RegisterUpload) -> UploadTicket:
        """Check the declaration and answer with a dedupe hit or a presigned staging URL."""
        record = self._load_record(uow, cmd.scope, cmd.record_id)
        self._check_declared(uow, record, cmd)
        key = object_key(cmd.sha256)
        exists = (
            self._store.exists(key) and self._known_size(uow, cmd.scope, cmd.sha256) is not None
        )
        staging = None if exists else f"staging/{new_ulid()}"
        expires_at = self._clock() + timedelta(seconds=self._ttl)
        claims = {
            "v": _TOKEN_VERSION,
            "actor": cmd.actor,
            "scope": cmd.scope,
            "record_id": cmd.record_id,
            "slot": cmd.slot,
            "filename": cmd.filename,
            "content_type": cmd.content_type,
            "size": cmd.size,
            "sha256": cmd.sha256,
            "staging": staging,
            "exp": int(expires_at.timestamp()),
        }
        url = None if staging is None else self._store.presign_put(staging, expires_s=self._ttl)
        return UploadTicket(
            upload_id=self._sign(claims),
            key=key,
            exists=exists,
            upload_url=url,
            expires_at=expires_at,
        )

    def complete_upload(
        self, uow: UnitOfWork, cmd: CompleteUpload, data: BinaryIO | None = None
    ) -> FileResult:
        """Verify, store, attach. ``data`` is the bytes when they did not arrive by presigned URL.

        Raises ``UploadTokenError`` (bad, expired or foreign ``upload_id``),
        ``UploadIncompleteError``
        (no bytes yet), ``UploadVerificationError`` (size or hash differs from the declaration),
        and the slot, record and rejected-content errors of ``register_upload``.
        """
        claims = self._verify(cmd.upload_id)
        if claims["actor"] != cmd.actor or claims["scope"] != cmd.scope:
            raise UploadTokenError("this upload id was issued to someone else")
        declared = AttachFile(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            record_id=claims["record_id"],
            slot=claims["slot"],
            filename=claims["filename"],
            content_type=claims["content_type"],
            size=claims["size"],
            sha256=claims["sha256"],
        )
        return self._attach(uow, declared, data=data, staging=claims["staging"])

    def attach_file(self, uow: UnitOfWork, cmd: AttachFile) -> FileResult:
        """Attach bytes already attached in this scope to a (possibly different) record slot.

        Raises ``UploadIncompleteError`` when this scope has never attached that hash: use the
        upload flow so the bytes are shown once.
        """
        return self._attach(uow, cmd, data=None, staging=None)

    # --- quarantine and scan ----------------------------------------------------------------

    def scan_file(
        self, uow: UnitOfWork, scope: str, file_id: str, *, source: str = "svc:scanner"
    ) -> FileResult:
        """Scan one quarantined file; append ``File.Processed`` or ``File.Rejected``."""
        return self._scan(uow, scope, file_id, source=source, correlation_id=None)

    def scan_pending(
        self, uow: UnitOfWork, *, scope: str | None = None, limit: int = 100
    ) -> list[FileResult]:
        """Scan up to ``limit`` quarantined files, oldest first (a worker calls this)."""
        sql = _PENDING_SQL.format(scope=" AND scope = :scope" if scope is not None else "")
        params: dict[str, Any] = {"limit": limit}
        if scope is not None:
            params["scope"] = scope
        rows = uow.conn().execute(text(sql), params).all()
        return [
            self._scan(uow, r.scope, r.file_id, source="svc:scanner", correlation_id=None)
            for r in rows
        ]

    # --- reading ----------------------------------------------------------------------------

    def open_file(self, uow: UnitOfWork, scope: str, file_id: str, *, actor: str) -> OpenedFile:
        """Open the bytes. Quarantined: uploader only. Rejected: nobody."""
        info = self._readable(uow, scope, file_id, actor)
        try:
            data = self._store.get(object_key(info.sha256))
        except ObjectNotFound as exc:
            raise ObjectMissingError(
                f"file {file_id!r} is in the ledger but its object is missing; see the "
                "object-store reconciliation runbook"
            ) from exc
        return OpenedFile(info=info, data=data)

    def presign_download(
        self, uow: UnitOfWork, scope: str, file_id: str, *, actor: str, expires_s: int = 300
    ) -> str:
        """A time-limited download URL, under the same rules as ``open_file``."""
        info = self._readable(uow, scope, file_id, actor)
        return self._store.presign_get(object_key(info.sha256), expires_s=expires_s)

    # --- internals --------------------------------------------------------------------------

    def _readable(self, uow: UnitOfWork, scope: str, file_id: str, actor: str) -> FileInfo:
        info = get_file(uow, scope, file_id)
        if info.status == "rejected":
            raise FileRejectedError(f"file {file_id!r} was rejected: {info.reason or 'no reason'}")
        if info.status == "quarantined" and info.uploaded_by != actor:
            raise FileQuarantinedError(f"file {file_id!r} is in quarantine until its scan passes")
        return info

    def _slot_registry(self) -> FileSlotRegistry:
        if self._slots is None:
            self._slots = default_file_slots()
        return self._slots

    @staticmethod
    def _load_record(uow: UnitOfWork, scope: str, record_id: str) -> _Record:
        row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
        if row is None or row.scope != scope:
            raise RecordNotFoundError(f"no record {record_id!r} in scope {scope!r}")
        if row.voided:
            raise RecordVoidedError(f"record {record_id!r} is voided; files cannot be attached")
        return _Record(id=row.id, type=row.type)

    def _check_declared(self, uow: UnitOfWork, record: _Record, cmd: _Declared) -> None:
        """Slot rules (brief 20.1) and the refusal of bytes a scan rejected before."""
        if cmd.slot is None:
            if cmd.size > self._max_unslotted:
                raise FileTooLargeError(
                    f"{cmd.size} bytes is above the {self._max_unslotted} byte limit for "
                    "attachments without a slot"
                )
        else:
            slot = self._slot_registry().get(record.type, cmd.slot)
            if slot is None:
                raise UnknownSlotError(f"record type {record.type!r} has no file slot {cmd.slot!r}")
            if not slot.accepts(cmd.content_type):
                accepted = ", ".join(slot.accepted_types)
                raise FileTypeNotAcceptedError(
                    f"slot {slot.name!r} accepts {accepted}, not {cmd.content_type!r}"
                )
            if slot.max_size is not None and cmd.size > slot.max_size:
                raise FileTooLargeError(
                    f"{cmd.size} bytes is above the {slot.max_size} byte limit of slot "
                    f"{slot.name!r}"
                )
        if uow.conn().execute(_REJECTED_SQL, {"sha256": cmd.sha256}).first() is not None:
            raise ContentRejectedError("these bytes were rejected by a scan and cannot be attached")

    @staticmethod
    def _known_size(uow: UnitOfWork, scope: str, sha256: str) -> int | None:
        """The verified size of bytes this scope has already attached, else ``None``."""
        row = uow.conn().execute(_KNOWN_SQL, {"sha256": sha256, "scope": scope}).first()
        return None if row is None else int(row.size)

    def _put(self, key: str, data: BinaryIO, cmd: _Declared) -> None:
        try:
            self._store.put(
                key, data, size=cmd.size, sha256=cmd.sha256, content_type=cmd.content_type
            )
        except ObjectIntegrityError as exc:
            raise UploadVerificationError(str(exc)) from exc

    def _source_stream(self, data: BinaryIO | None, staging: str | None) -> BinaryIO | None:
        """The stream that carries the bytes: the caller's, else the staging object, else none."""
        if data is not None:
            return data
        if staging is not None and self._store.exists(staging):
            return self._store.get(staging)
        return None

    def _ensure_object(
        self, uow: UnitOfWork, cmd: _Declared, data: BinaryIO | None, staging: str | None
    ) -> bool:
        """Make the object exist under its content key, verified. True when it already did."""
        key = object_key(cmd.sha256)
        known = self._known_size(uow, cmd.scope, cmd.sha256)
        exists = self._store.exists(key)
        if exists and known is not None:
            if known != cmd.size:
                raise UploadVerificationError(
                    f"declared size {cmd.size} differs from the {known} bytes stored for this hash"
                )
            return True
        source = self._source_stream(data, staging)
        if source is None:
            raise UploadIncompleteError(
                "no bytes received for this upload"
                if not exists
                else "this scope has not attached these bytes before; send them once to prove it"
            )
        try:
            if exists:
                # Present in the store but never attached here: the sender must show the bytes.
                digest, count = hash_stream(source)
                if digest != cmd.sha256 or count != cmd.size:
                    raise UploadVerificationError(
                        f"received bytes (sha256 {digest}, {count} bytes) differ from the "
                        f"declaration (sha256 {cmd.sha256}, {cmd.size} bytes)"
                    )
                return True
            self._put(key, source, cmd)
            return False
        finally:
            if source is not data:
                source.close()

    def _attach(
        self, uow: UnitOfWork, cmd: AttachFile, *, data: BinaryIO | None, staging: str | None
    ) -> FileResult:
        record = self._load_record(uow, cmd.scope, cmd.record_id)
        self._check_declared(uow, record, cmd)
        same = self._same_attachment(uow, cmd)
        if same is not None:
            if not self._store.exists(object_key(cmd.sha256)):
                # The row survives but the object is gone: re-sending the bytes restores it.
                self._ensure_object(uow, cmd, data, staging)
            info = get_file(uow, cmd.scope, same)
            return self._result(info, deduplicated=info.deduplicated, already_attached=True)
        deduplicated = self._ensure_object(uow, cmd, data, staging)
        file_id = new_ulid()
        correlation_id = cmd.correlation_id or new_ulid()
        revision = self._next_revision(uow, cmd)
        uploaded = uow.append(
            stream_id=file_id,
            stream_type=FILE_STREAM_TYPE,
            scope=cmd.scope,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="File.Uploaded",
                    payload={
                        "file_id": file_id,
                        "record_id": cmd.record_id,
                        "slot": cmd.slot,
                        "revision": revision,
                        "sha256": cmd.sha256,
                        "size": cmd.size,
                        "content_type": cmd.content_type,
                        "filename": cmd.filename,
                        "status": next_file_status(None, "File.Uploaded"),
                        "deduplicated": deduplicated,
                    },
                )
            ],
            actor=cmd.actor,
            source=cmd.source,
            correlation_id=correlation_id,
            causation_id=cmd.causation_id,
        )
        events = list(uploaded.events)
        status = "quarantined"
        if self._scan_inline:
            scanned = self._scan(
                uow, cmd.scope, file_id, source=cmd.source, correlation_id=correlation_id
            )
            events.extend(scanned.events)
            status = scanned.status
        return FileResult(
            file_id=file_id,
            record_id=cmd.record_id,
            slot=cmd.slot,
            revision=revision,
            sha256=cmd.sha256,
            size=cmd.size,
            status=status,
            deduplicated=deduplicated,
            events=events,
        )

    @staticmethod
    def _result(info: FileInfo, *, deduplicated: bool, already_attached: bool) -> FileResult:
        return FileResult(
            file_id=info.file_id,
            record_id=info.record_id,
            slot=info.slot,
            revision=info.revision,
            sha256=info.sha256,
            size=info.size,
            status=info.status,
            deduplicated=deduplicated,
            already_attached=already_attached,
        )

    @staticmethod
    def _same_attachment(uow: UnitOfWork, cmd: _Declared) -> str | None:
        """The live file of this record and slot with the same bytes (a retry), else ``None``."""
        sql = _SAME_SQL + (" AND slot = :slot" if cmd.slot is not None else " AND slot IS NULL")
        params: dict[str, Any] = {
            "record_id": cmd.record_id,
            "sha256": cmd.sha256,
            "actor": cmd.actor,
        }
        if cmd.slot is not None:
            params["slot"] = cmd.slot
        row = uow.conn().execute(text(sql), params).first()
        return None if row is None else str(row.file_id)

    @staticmethod
    def _next_revision(uow: UnitOfWork, cmd: _Declared) -> int:
        sql = _MAX_REVISION_SQL + (
            " AND slot = :slot" if cmd.slot is not None else " AND slot IS NULL"
        )
        params: dict[str, Any] = {"record_id": cmd.record_id}
        if cmd.slot is not None:
            params["slot"] = cmd.slot
        return int(uow.conn().execute(text(sql), params).scalar_one()) + 1

    def _scan(
        self,
        uow: UnitOfWork,
        scope: str,
        file_id: str,
        *,
        source: str,
        correlation_id: str | None,
    ) -> FileResult:
        row = uow.conn().execute(_FILE_SQL, {"file_id": file_id}).first()
        if row is None or row.scope != scope:
            raise RecordNotFoundError(f"no file {file_id!r} in scope {scope!r}")
        # Refuse early (and clearly) when the file already left quarantine.
        next_file_status(row.status, "File.Processed")
        key = object_key(row.sha256)
        try:
            stream = self._store.get(key)
        except ObjectNotFound as exc:
            raise ObjectMissingError(
                f"object for file {file_id!r} is missing from the store"
            ) from exc
        try:
            verdict: ScanResult = self._scanner.scan(
                stream, filename=row.filename, content_type=row.content_type
            )
        finally:
            stream.close()
        if verdict.clean:
            event = NewEvent(
                event_type="File.Processed",
                payload={
                    "file_id": file_id,
                    "status": next_file_status(row.status, "File.Processed"),
                    "report": verdict.report,
                    "supersedes": self._superseded_by_release(uow, row),
                },
            )
        else:
            event = NewEvent(
                event_type="File.Rejected",
                payload={
                    "file_id": file_id,
                    "status": next_file_status(row.status, "File.Rejected"),
                    "reason": verdict.reason or "rejected by the scanner",
                    "report": verdict.report,
                },
            )
        appended = uow.append(
            stream_id=file_id,
            stream_type=FILE_STREAM_TYPE,
            scope=scope,
            expected_version=row.version,
            events=[event],
            actor=SCANNER_ACTOR,
            source=source,
            correlation_id=correlation_id or new_ulid(),
        )
        info = get_file(uow, scope, file_id)
        result = self._result(info, deduplicated=info.deduplicated, already_attached=False)
        result.events = list(appended.events)
        return result

    def _superseded_by_release(self, uow: UnitOfWork, row: Any) -> list[str]:
        """Files this one replaces once available: the current files of a ``one`` slot."""
        if row.slot is None:
            return []
        record = uow.conn().execute(_RECORD_SQL, {"id": row.record_id}).first()
        if record is None:
            return []
        slot = self._slot_registry().get(record.type, row.slot)
        if slot is None or slot.cardinality != "one":
            return []
        found = uow.conn().execute(
            _CURRENT_IN_SLOT_SQL,
            {"record_id": row.record_id, "slot": row.slot, "file_id": row.file_id},
        )
        return [str(r.file_id) for r in found]

    # --- upload ids -------------------------------------------------------------------------

    def _sign(self, claims: dict[str, Any]) -> str:
        body = base64.urlsafe_b64encode(
            json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
        ).decode()
        signature = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def _verify(self, token: str) -> dict[str, Any]:
        body, dot, signature = token.partition(".")
        # Bytes, not str: compare_digest raises TypeError on a non-ASCII str, and a client controls
        # this text. ``replace`` keeps lone surrogates from raising; such a token cannot verify.
        expected = hmac.new(self._secret, _wire(body), hashlib.sha256).hexdigest().encode()
        if not dot or not hmac.compare_digest(_wire(signature), expected):
            raise UploadTokenError("upload id is malformed or was not issued by this server")
        try:
            claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(body.encode()))
        except (binascii.Error, ValueError) as exc:
            raise UploadTokenError("upload id is malformed") from exc
        if claims.get("v") != _TOKEN_VERSION:
            raise UploadTokenError("upload id has an unknown version")
        if int(claims["exp"]) < int(self._clock().timestamp()):
            raise UploadTokenError("upload id has expired; register the upload again")
        return claims
