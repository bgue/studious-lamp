"""Document commands: register, update, supersede, void (brief 9 M1; P1-I2).

A document is a project record (``documents.Document``) whose number is its key. The number is
checked against the registry numbering pattern for documents when the company has one, the type
and discipline against their code lists when those are registered, and the revision scheme is
chosen from the scheme file unless the command names one. Each handler runs inside an entered unit
of work, appends through it and never commits. A failed check raises a ``ServiceError`` before
anything is appended. All the events of one command share one correlation id.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import Connection
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_mod_engineering import codelists, patterns
from tl_mod_engineering.errors import UnknownCodeError, UnknownCodeListError

from tl_mod_documents.errors import (
    DocumentClosedError,
    InvalidDocumentNumberError,
    InvalidDocumentTypeError,
)
from tl_mod_documents.handlers.common import (
    append,
    changes_of,
    correlated,
    load_document,
    open_document,
    require_project,
    transition,
)
from tl_mod_documents.limits import (
    MAX_DESCRIPTION,
    MAX_NUMBER,
    MAX_REASON,
    MAX_TEXT,
)
from tl_mod_documents.names import (
    DISCIPLINE_LIST,
    DOCUMENT,
    DOCUMENT_DEFINED,
    DOCUMENT_SUPERSEDED,
    DOCUMENT_TYPE_LIST,
    DOCUMENT_UPDATED,
)
from tl_mod_documents.resolver import flag_links_to_document
from tl_mod_documents.schemes import load_scheme_file, scheme_by_code, scheme_code_for


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class RegisterDocument(Command):
    """Register a document in a project under its number. The number becomes the record key.

    The number must fit the registry numbering pattern for documents when there is one. The type
    and the discipline must be usable values of the code lists ``DocumentType`` and ``Discipline``
    when the company has registered them. The revision scheme defaults from the scheme file.
    """

    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=1, max_length=MAX_NUMBER)
    title: str = Field(min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    doc_type: str | None = Field(default=None, max_length=MAX_NUMBER)
    discipline: str | None = Field(default=None, max_length=MAX_NUMBER)
    originator: str | None = Field(default=None, max_length=MAX_TEXT)
    confidentiality: str | None = Field(default=None, max_length=MAX_NUMBER)
    revision_scheme: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _non_blank(value)


class UpdateDocument(Command):
    """Change a document's title, description or register fields (not its number or scheme)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    doc_type: str | None = Field(default=None, max_length=MAX_NUMBER)
    discipline: str | None = Field(default=None, max_length=MAX_NUMBER)
    originator: str | None = Field(default=None, max_length=MAX_TEXT)
    confidentiality: str | None = Field(default=None, max_length=MAX_NUMBER)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _non_blank(value)


class SupersedeDocument(Command):
    """Replace a document by another one: the old is Superseded and its links go stale."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    superseded_by_id: str
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class VoidDocument(Command):
    """Void a document that was registered in error. Its links go stale. Admin only."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def _check_code(conn: Connection, scope: str, list_name: str, value: str | None, what: str) -> None:
    """``value`` must be a usable value of its code list; a list nobody registered is open."""
    if value is None:
        return
    try:
        found = codelists.resolve(conn, scope, list_name, value, on=date.today())
    except UnknownCodeListError:
        return
    except UnknownCodeError as exc:
        raise InvalidDocumentTypeError(f"{what} {value!r} is not a value of {list_name}") from exc
    if not found.usable:
        raise InvalidDocumentTypeError(f"{what} {value!r} of {list_name} is no longer in use")


def handle_register_document(uow: UnitOfWork, cmd: RegisterDocument) -> CommandResult:
    """Append ``Record.Created`` and ``Document.Defined``, then move the document to Registered.

    Raises ``ProjectScopeError`` (not a project scope), ``InvalidDocumentNumberError`` (the number
    breaks the registry pattern: ``issues`` lists every problem), ``InvalidDocumentTypeError``,
    ``UnknownSchemeError`` and ``DuplicateKeyError``. With no registry pattern for documents the
    number is accepted as written.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    _check_code(conn, cmd.scope, DOCUMENT_TYPE_LIST, cmd.doc_type, "document type")
    _check_code(conn, cmd.scope, DISCIPLINE_LIST, cmd.discipline, "discipline")
    pattern_code: str | None = None
    pattern = patterns.pattern_for(conn, DOCUMENT)
    if pattern is not None:
        parsed = patterns.parse_number(conn, cmd.scope, pattern, cmd.number)
        errors = [i for i in parsed.issues if i.level == "error"]
        if errors:
            raise InvalidDocumentNumberError(
                f"document number {cmd.number!r}: " + "; ".join(i.message for i in errors),
                [i.as_dict() for i in parsed.issues],
            )
        pattern_code = pattern.code
    config = load_scheme_file()
    scheme = scheme_by_code(
        config, cmd.revision_scheme or scheme_code_for(config, cmd.scope, cmd.doc_type)
    )
    made = create_module_record(
        uow,
        cmd,
        record_type=DOCUMENT,
        title=cmd.title,
        description=cmd.description,
        key=cmd.number,
        extra_events=[
            NewEvent(
                event_type=DOCUMENT_DEFINED,
                payload={
                    "number": cmd.number,
                    "doc_type": cmd.doc_type,
                    "discipline": cmd.discipline,
                    "originator": cmd.originator,
                    "confidentiality": cmd.confidentiality,
                    "revision_scheme": scheme.code,
                    "pattern_code": pattern_code,
                },
            )
        ],
    )
    moved = transition(uow, cmd, made.stream_id, "register")
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=moved.version,
        events=[*made.events, *moved.events],
    )


def handle_update_document(uow: UnitOfWork, cmd: UpdateDocument) -> CommandResult:
    """Append ``Record.Updated`` (title, description) and ``Document.Updated`` (register fields).

    Raises ``DocumentNotFoundError``, ``DocumentClosedError``, ``InvalidDocumentTypeError`` and
    ``NoChangesError`` (nothing differs).
    """
    cmd = correlated(cmd)
    doc = open_document(uow, cmd, cmd.stream_id)
    conn = uow.conn()
    given = cmd.model_fields_set
    envelope_new: dict[str, Any] = {}
    if cmd.title is not None:
        envelope_new["title"] = cmd.title
    if "description" in given:
        envelope_new["description"] = cmd.description
    register_old: dict[str, Any] = {
        "doc_type": doc.doc_type,
        "discipline": doc.discipline,
        "originator": doc.originator,
        "confidentiality": doc.confidentiality,
    }
    register_new = {k: getattr(cmd, k) for k in register_old if k in given}
    if register_new.get("doc_type", doc.doc_type) != doc.doc_type:
        _check_code(conn, cmd.scope, DOCUMENT_TYPE_LIST, register_new["doc_type"], "document type")
    if register_new.get("discipline", doc.discipline) != doc.discipline:
        _check_code(conn, cmd.scope, DISCIPLINE_LIST, register_new["discipline"], "discipline")
    envelope = changes_of({"title": doc.title, "description": doc.description}, envelope_new)
    register = changes_of(register_old, register_new)
    if not envelope and not register:
        raise NoChangesError(f"no field of document {doc.number} differs from the request")
    events: list[NewEvent] = []
    if envelope:
        events.append(NewEvent(event_type="Record.Updated", payload={"changes": envelope}))
    if register:
        events.append(
            NewEvent(
                event_type=DOCUMENT_UPDATED, payload={"changes": register, "reason": cmd.reason}
            )
        )
    done = append(uow, cmd, doc.id, DOCUMENT, events, expected=cmd.expected_version or doc.version)
    return CommandResult(
        stream_id=doc.id, key=doc.number, version=done.new_version, events=done.events
    )


def handle_supersede_document(uow: UnitOfWork, cmd: SupersedeDocument) -> CommandResult:
    """Mark a document Superseded by another; add a ``supersedes`` link; flag the old one's links.

    The replacing document must be a live document of the same scope. Emits ``Document.Superseded``,
    ``Workflow.Transitioned``, ``Link.Added`` (new supersedes old) and a ``Link.Flagged`` for each
    active link to the old document. Raises ``DocumentNotFoundError``, ``DocumentClosedError`` and
    ``NoChangesError`` (a document cannot supersede itself).
    """
    cmd = correlated(cmd)
    old = open_document(uow, cmd, cmd.stream_id)
    new = load_document(uow, cmd, cmd.superseded_by_id)
    if new.id == old.id:
        raise NoChangesError("a document cannot supersede itself")
    if new.closed:
        raise DocumentClosedError(
            f"document {new.number} is {new.state} and cannot replace another"
        )
    events: list[Event] = []
    done = append(
        uow,
        cmd,
        old.id,
        DOCUMENT,
        [
            NewEvent(
                event_type=DOCUMENT_SUPERSEDED,
                payload={"superseded_by": new.id, "reason": cmd.reason},
            )
        ],
        expected=cmd.expected_version or old.version,
    )
    events += done.events
    moved = transition(uow, cmd, old.id, "supersede", reason=cmd.reason)
    events += moved.events
    # Flag the links that exist now; the `supersedes` link added next is the record of this move.
    events += flag_links_to_document(uow, cmd, old.id, f"document superseded by {new.number}")
    linked = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=new.id,
            to_id=old.id,
            relation="supersedes",
            link_source="rule",
            note=cmd.reason,
        ),
    )
    events += linked.events
    return CommandResult(stream_id=old.id, key=old.number, version=moved.version, events=events)


def handle_void_document(uow: UnitOfWork, cmd: VoidDocument) -> CommandResult:
    """Move the document to Void, void its record, flag every active link to it stale.

    Emits ``Workflow.Transitioned``, ``Record.Voided`` and a ``Link.Flagged`` for each link. Raises
    ``DocumentNotFoundError`` and ``DocumentClosedError`` (already void or superseded).
    """
    cmd = correlated(cmd)
    doc = open_document(uow, cmd, cmd.stream_id)
    moved = transition(uow, cmd, doc.id, "void", reason=cmd.reason, expected=cmd.expected_version)
    voided = append(
        uow,
        cmd,
        doc.id,
        DOCUMENT,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    flagged = flag_links_to_document(uow, cmd, doc.id, "document voided")
    return CommandResult(
        stream_id=doc.id,
        key=doc.number,
        version=voided.new_version,
        events=[*moved.events, *voided.events, *flagged],
    )
