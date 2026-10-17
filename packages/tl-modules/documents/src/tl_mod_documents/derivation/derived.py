"""Derived documents: open one, start an extraction, validate again, cancel a job, void (ADR-0014).

``OpenDerivedDocument`` makes the record for a source revision and a document schema (the person
needs it to attach a CSV). ``StartExtraction`` queues a processing job that reads one file;
``ValidateDerived`` queues a job that checks stored rows against a schema version; ``CancelJob``
stops a queued job. Each command only *queues* work: the job runner (``jobs.py``) does it. The
record moves Pending, Invalid or Valid to Processing when a job is queued and back when it ends.
Everything is open to any signed-in person; publishing is a separate, gated command.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_adapters.queue import job_queue_for
from tl_core.derivation.registry import (
    AmbiguousExtractorError,
    NoExtractorError,
    choose,
    load_extractors,
)
from tl_core.derivation.types import SourceFile
from tl_core.files.queries import FileInfo, get_file, list_files
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import UnknownFileError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_documents import registry
from tl_mod_documents.derivation import rows
from tl_mod_documents.errors import (
    DerivedNotFoundError,
    DerivedStateError,
    InvalidDocumentSchemaError,
    InvalidSourceError,
    JobNotFoundError,
    JobStateError,
    RevisionNotFoundError,
    SchemaNotFoundError,
)
from tl_mod_documents.handlers.common import (
    append,
    correlated,
    open_document,
    require_project,
    transition,
)
from tl_mod_documents.limits import MAX_REASON, MAX_TEXT
from tl_mod_documents.names import (
    DD_INVALID,
    DD_PENDING,
    DD_PROCESSING,
    DD_VALID,
    DERIVED_DEFINED,
    DERIVED_DOCUMENT,
    JOB_CANCELLED,
    JOB_DEFINED,
    JOB_KIND_EXTRACT,
    JOB_KIND_VALIDATE,
    PROCESSING_JOB,
    SLOT_CONTENT,
)

MAX_OPTIONS_CHARS = 16_000
DEFAULT_MAX_ATTEMPTS = 3
#: States of a derived document in which a job may be queued.
QUEUEABLE = (DD_PENDING, DD_INVALID, DD_VALID)


class OpenDerivedDocument(Command):
    """Open the derived document of a revision for a document schema (idempotent)."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    schema_code: str = Field(min_length=1, max_length=MAX_TEXT)
    schema_semver: str | None = Field(default=None, max_length=32)


class StartExtraction(Command):
    """Queue a job that reads a file and checks what it read against a document schema.

    Name the derived document (``derived_id``) or the revision and schema code that open it.
    The file is a rendition of the revision (``rendition_id``) or a file of the derived document's
    ``content`` slot (``file_id``); without either, the newest content file, else the revision's
    current PDF, else its current native file. ``extractor`` picks a plugin by name; without it the
    one that accepts the file is used. ``options`` go to the extractor.
    """

    model_config = ConfigDict(extra="forbid")

    derived_id: str | None = None
    revision_id: str | None = None
    schema_code: str | None = Field(default=None, max_length=MAX_TEXT)
    schema_semver: str | None = Field(default=None, max_length=32)
    rendition_id: str | None = None
    file_id: str | None = None
    extractor: str | None = Field(default=None, max_length=MAX_TEXT)
    options: dict[str, Any] = Field(default_factory=dict[str, Any])

    @model_validator(mode="after")
    def _one_way_to_name_the_target(self) -> StartExtraction:
        by_revision = self.revision_id is not None and self.schema_code is not None
        if (self.derived_id is None) == (not by_revision):
            raise ValueError("give derived_id, or revision_id with schema_code, and not both")
        if self.rendition_id is not None and self.file_id is not None:
            raise ValueError("give rendition_id or file_id, not both")
        return self

    @field_validator("options")
    @classmethod
    def _options(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False, default=str)) > MAX_OPTIONS_CHARS:
            raise ValueError(f"options are longer than {MAX_OPTIONS_CHARS} characters")
        return value


class ValidateDerived(Command):
    """Queue a job that checks stored rows against a schema version again.

    ``schema_semver`` names another version of the derived document's schema (default: the one it
    names now); ``content_rev`` the pass to check (default: the latest).
    """

    model_config = ConfigDict(extra="forbid")

    derived_id: str
    content_rev: int | None = Field(default=None, ge=1)
    schema_semver: str | None = Field(default=None, max_length=32)


class CancelJob(Command):
    """Cancel a job that no worker has taken yet."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    reason: str = Field(default="cancelled", max_length=MAX_REASON)


class VoidDerivedDocument(Command):
    """Void a derived document that was opened in error (no running job, not published)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def finish_transition(derived: rows.DerivedRow) -> str:
    """The workflow move that ends a job: back to the state the latest validation names."""
    return {"valid": "finish_valid", "invalid": "finish_invalid"}.get(
        derived.validation_status, "finish_pending"
    )


def load_derived(uow: UnitOfWork, cmd: Command, derived_id: str) -> rows.DerivedRow:
    found = rows.get_derived(uow.conn(), derived_id)
    if found is None or found.scope != cmd.scope:
        raise DerivedNotFoundError(f"no derived document {derived_id!r} in scope {cmd.scope!r}")
    return found


def _schema_for(uow: UnitOfWork, cmd: Command, code: str, semver: str | None) -> rows.SchemaRow:
    found = rows.resolve_schema(uow.conn(), cmd.scope, code, semver)
    if found is None:
        which = f"{code}@{semver}" if semver else code
        raise SchemaNotFoundError(f"no active document schema {which!r} for {cmd.scope}")
    if not found.is_active:
        raise InvalidDocumentSchemaError(f"{found.key} is retired; use a newer version")
    return found


def open_derived(
    uow: UnitOfWork,
    cmd: Command,
    revision_id: str,
    schema_code: str,
    semver: str | None,
    method: str,
) -> rows.DerivedRow:
    """The derived document of the revision for the schema code; made if it is not there yet."""
    require_project(cmd)
    conn = uow.conn()
    revision = registry.get_revision(conn, revision_id)
    if revision is None or revision.scope != cmd.scope or revision.voided:
        raise RevisionNotFoundError(f"no revision {revision_id!r} in scope {cmd.scope!r}")
    document = open_document(uow, cmd, revision.document_id)
    existing = rows.find_derived(conn, cmd.scope, revision.id, schema_code)
    if existing is not None:
        return existing
    schema = _schema_for(uow, cmd, schema_code, semver)
    if schema.doc_types and (document.doc_type not in schema.doc_types):
        raise InvalidDocumentSchemaError(
            f"{schema.key} applies to document types {', '.join(schema.doc_types)}, "
            f"not {document.doc_type or 'none'}"
        )
    previous = rows.previous_derived(
        conn, cmd.scope, document.id, schema.code, before_ordinal=revision.ordinal
    )
    key = f"{document.number}@{revision.code}/{schema.code}"
    made = create_module_record(
        uow,
        cmd,
        record_type=DERIVED_DOCUMENT,
        title=f"{document.number} rev {revision.code}: {schema.title}",
        key=key,
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=DERIVED_DEFINED,
                payload={
                    "source_document_id": document.id,
                    "source_revision_id": revision.id,
                    "source_document_number": document.number,
                    "source_revision_code": revision.code,
                    "source_ref": f"src.doc.{document.number}@{revision.code}",
                    "schema_id": schema.id,
                    "schema_code": schema.code,
                    "schema_version": schema.semver,
                    "method": method,
                    "previous_derived_id": None if previous is None else previous.id,
                },
            )
        ],
    )
    opened = rows.get_derived(conn, made.stream_id)
    assert opened is not None
    return opened


def handle_open_derived_document(uow: UnitOfWork, cmd: OpenDerivedDocument) -> CommandResult:
    """Open (or find) the derived document; the result's ``stream_id`` is its id.

    Raises ``RevisionNotFoundError``, ``DocumentClosedError``, ``SchemaNotFoundError`` and
    ``InvalidDocumentSchemaError`` (retired, or not for this document type).
    """
    cmd = correlated(cmd)
    derived = open_derived(
        uow, cmd, cmd.revision_id, cmd.schema_code, cmd.schema_semver, method="manual"
    )
    return CommandResult(stream_id=derived.id, key=derived.key, version=derived.version, events=[])


def _source_file(
    uow: UnitOfWork, cmd: StartExtraction, derived: rows.DerivedRow
) -> tuple[FileInfo, str]:
    """The file to read and how it got there (``rendition`` or ``upload``)."""
    conn = uow.conn()
    if cmd.rendition_id is not None:
        rendition = registry.get_rendition(conn, cmd.rendition_id)
        if rendition is None or rendition.revision_id != derived.source_revision_id:
            raise InvalidSourceError(
                f"rendition {cmd.rendition_id!r} is not a rendition of {derived.source_ref}"
            )
        return _file_info(uow, derived.scope, rendition.file_id), "rendition"
    if cmd.file_id is not None:
        info = _file_info(uow, derived.scope, cmd.file_id)
        if info.record_id != derived.id or info.slot != SLOT_CONTENT:
            raise InvalidSourceError(
                f"file {cmd.file_id!r} is not in the {SLOT_CONTENT} slot of {derived.key}"
            )
        return info, "upload"
    attached = [f for f in list_files(uow, derived.scope, derived.id, slot=SLOT_CONTENT)]
    usable = [f for f in attached if f.status != "rejected"]
    if usable:
        return max(usable, key=lambda f: (f.revision, f.file_id)), "upload"
    for kind in ("pdf", "native"):
        found = registry.renditions_of(
            conn, derived.source_revision_id, current_only=True, kind=kind
        )
        if found:
            return _file_info(uow, derived.scope, found[-1].file_id), "rendition"
    raise InvalidSourceError(
        f"{derived.source_ref} has no file to read: attach a rendition to the revision or a "
        f"CSV or XLSX to {derived.key}"
    )


def _file_info(uow: UnitOfWork, scope: str, file_id: str) -> FileInfo:
    try:
        info = get_file(uow, scope, file_id)
    except UnknownFileError as exc:
        raise InvalidSourceError(f"file {file_id!r} is not in scope {scope!r}") from exc
    if info.status == "rejected":
        raise InvalidSourceError(f"file {file_id!r} was rejected by the scan")
    return info


def source_file_of(info: FileInfo, source_ref: str) -> SourceFile:
    return SourceFile(
        file_id=info.file_id,
        filename=info.filename,
        content_type=info.content_type,
        size=info.size,
        sha256=info.sha256,
        source_ref=source_ref,
    )


def _queue_job(
    uow: UnitOfWork,
    cmd: Command,
    derived: rows.DerivedRow,
    *,
    kind: str,
    schema: rows.SchemaRow,
    source_file_id: str | None,
    extractor: str | None,
    options: dict[str, Any],
) -> CommandResult:
    """Create the job record, put it in the queue and move the derived document to Processing."""
    made = create_module_record(
        uow,
        cmd,
        record_type=PROCESSING_JOB,
        title=f"{kind} {derived.key}",
        key=f"JOB-{new_ulid()}",
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=JOB_DEFINED,
                payload={
                    "kind": kind,
                    "derived_id": derived.id,
                    "derived_key": derived.key,
                    "source_ref": derived.source_ref,
                    "source_file_id": source_file_id,
                    "extractor": extractor,
                    "options": options,
                    "schema_id": schema.id,
                    "requested_by": cmd.actor,
                    "max_attempts": DEFAULT_MAX_ATTEMPTS,
                },
            )
        ],
    )
    job_queue_for(uow.conn()).enqueue(
        uow.conn(),
        job_id=made.stream_id,
        kind=kind,
        scope=cmd.scope,
        now=utcnow(),
        max_attempts=DEFAULT_MAX_ATTEMPTS,
    )
    moved = transition(uow, cmd, derived.id, "start", expected=None)
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=made.version,
        events=[*made.events, *moved.events],
    )


def _require_queueable(uow: UnitOfWork, derived: rows.DerivedRow) -> None:
    if derived.voided or derived.state not in QUEUEABLE:
        raise DerivedStateError(
            f"{derived.key} is {derived.state}; a job can be queued while it is "
            f"{', '.join(QUEUEABLE)}"
        )
    active = rows.active_job(uow.conn(), derived.id)
    if active is not None:
        raise DerivedStateError(f"{derived.key} already has a job ({active.key}, {active.state})")


def handle_start_extraction(uow: UnitOfWork, cmd: StartExtraction) -> CommandResult:
    """Queue an extraction job; the result's ``stream_id`` is the job.

    Raises what ``open_derived`` raises, ``DerivedNotFoundError``, ``DerivedStateError`` (running,
    published, void, or a job already queued), ``InvalidSourceError`` (the file is not usable, no
    file, or no extractor accepts it or the name is unknown).
    """
    cmd = correlated(cmd)
    require_project(cmd)
    if cmd.derived_id is not None:
        derived = load_derived(uow, cmd, cmd.derived_id)
    else:
        assert cmd.revision_id is not None and cmd.schema_code is not None
        method = "manual" if cmd.file_id is not None else "automated"
        derived = open_derived(
            uow, cmd, cmd.revision_id, cmd.schema_code, cmd.schema_semver, method
        )
    open_document(uow, cmd, derived.source_document_id)
    _require_queueable(uow, derived)
    info, _ = _source_file(uow, cmd, derived)
    try:
        choose(load_extractors(), source_file_of(info, derived.source_ref), cmd.extractor)
    except (NoExtractorError, AmbiguousExtractorError) as exc:
        raise InvalidSourceError(str(exc)) from exc
    schema = rows.get_schema(uow.conn(), derived.schema_id)
    assert schema is not None
    return _queue_job(
        uow,
        cmd,
        derived,
        kind=JOB_KIND_EXTRACT,
        schema=schema,
        source_file_id=info.file_id,
        extractor=cmd.extractor,
        options=cmd.options,
    )


def handle_validate_derived(uow: UnitOfWork, cmd: ValidateDerived) -> CommandResult:
    """Queue a validation job over stored rows; the result's ``stream_id`` is the job.

    Raises ``DerivedNotFoundError``, ``DerivedStateError`` and ``InvalidSourceError`` (the pass has
    no rows to check).
    """
    cmd = correlated(cmd)
    derived = load_derived(uow, cmd, cmd.derived_id)
    _require_queueable(uow, derived)
    rev = cmd.content_rev or derived.content_rev
    content = rows.get_content(uow.conn(), derived.id, rev) if rev else None
    if content is None or content.result_file_id is None or content.row_count == 0:
        raise InvalidSourceError(
            f"{derived.key} has no stored rows to check (pass {rev or 'none'})"
        )
    schema = _schema_for(uow, cmd, derived.schema_code, cmd.schema_semver or None)
    return _queue_job(
        uow,
        cmd,
        derived,
        kind=JOB_KIND_VALIDATE,
        schema=schema,
        source_file_id=content.result_file_id,
        extractor=None,
        options={"content_rev": rev},
    )


def handle_cancel_job(uow: UnitOfWork, cmd: CancelJob) -> CommandResult:
    """Cancel a queued job and return its derived document to where it was.

    Raises ``JobNotFoundError`` and ``JobStateError`` (a worker already took it, or it ended).
    """
    cmd = correlated(cmd)
    job = rows.get_job(uow.conn(), cmd.job_id)
    if job is None or job.scope != cmd.scope:
        raise JobNotFoundError(f"no processing job {cmd.job_id!r} in scope {cmd.scope!r}")
    if not job_queue_for(uow.conn()).cancel(uow.conn(), job.id, now=utcnow()):
        raise JobStateError(f"{job.key} is {job.state}; only a queued job can be cancelled")
    made = append(
        uow,
        cmd,
        job.id,
        PROCESSING_JOB,
        [NewEvent(event_type=JOB_CANCELLED, payload={"reason": cmd.reason})],
    )
    derived = rows.get_derived(uow.conn(), job.derived_id)
    events = list(made.events)
    if derived is not None and derived.state == DD_PROCESSING:
        events.extend(transition(uow, cmd, derived.id, finish_transition(derived)).events)
    return CommandResult(stream_id=job.id, key=job.key, version=made.new_version, events=events)


def handle_void_derived_document(uow: UnitOfWork, cmd: VoidDerivedDocument) -> CommandResult:
    """Void a derived document: ``Workflow.Transitioned`` and ``Record.Voided``.

    Raises ``DerivedNotFoundError`` and ``DerivedStateError`` (running, published or void).
    """
    cmd = correlated(cmd)
    derived = load_derived(uow, cmd, cmd.stream_id)
    _require_queueable(uow, derived)
    moved = transition(
        uow, cmd, derived.id, "void", reason=cmd.reason, expected=cmd.expected_version
    )
    voided = append(
        uow,
        cmd,
        derived.id,
        DERIVED_DOCUMENT,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=derived.id,
        key=derived.key,
        version=voided.new_version,
        events=[*moved.events, *voided.events],
    )
