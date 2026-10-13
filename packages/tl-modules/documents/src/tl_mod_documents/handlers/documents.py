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

from pydantic import ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import Connection
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import RESERVED_KEY_CHARS, create_module_record
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
    CONFIDENTIALITY_NOTE,
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
    confidentiality: str | None = Field(
        default=None, max_length=MAX_NUMBER, description=CONFIDENTIALITY_NOTE
    )
    revision_scheme: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _non_blank(value)

    @field_validator("number")
    @classmethod
    def _number(cls, value: str) -> str:
        if has_control_character(value):
            raise ValueError("must not hold a line break or another control character")
        return value


class UpdateDocument(Command):
    """Change a document's title, description or register fields (not its number, its scheme or
    its confidentiality, which a document controller sets with ``SetDocumentConfidentiality``)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    doc_type: str | None = Field(default=None, max_length=MAX_NUMBER)
    discipline: str | None = Field(default=None, max_length=MAX_NUMBER)
    originator: str | None = Field(default=None, max_length=MAX_TEXT)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _non_blank(value)


class SetDocumentConfidentiality(Command):
    """Set or clear a document's confidentiality class (controller). The reason is kept.

    In Phase 1 confidentiality is recorded but not enforced: every signed-in person and every
    agent can read all documents and transmittals of a project, including recipient emails.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    confidentiality: str | None = Field(
        default=None, max_length=MAX_NUMBER, description=CONFIDENTIALITY_NOTE
    )
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class SupersedeDocument(Command):
    """Replace a document by another one: the old is Superseded and its links go stale (controller).

    The replacement must be a live document that has a current issued revision; a reason is
    required. Its document type may differ (an isometric can be replaced by a general arrangement),
    so the type is not compared.
    """

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
    """Void a document that was registered in error. Its links go stale. Controller only."""

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


def has_control_character(text: str) -> bool:
    """Whether ``text`` holds a character below space or DEL (a tab and a line break included)."""
    return any(ord(c) < 32 or ord(c) == 127 for c in text)


def field_problems(**fields: str | None) -> list[str]:
    """Why ``RegisterDocument`` would refuse these field values on their own (else empty).

    It builds the command with them, so the limits and validators are the model's, not copies.
    A field given as ``None`` is left out. Each problem is ``<field>: <message>``.
    """
    given = {name: value for name, value in fields.items() if value is not None}
    try:
        RegisterDocument.model_validate(
            {"actor": "user:plan", "source": "plan", "scope": "project:plan", **given}
        )
    except ValidationError as exc:
        return [
            f"{error['loc'][0]}: {error['msg']}"
            for error in exc.errors()
            if error["loc"] and error["loc"][0] in given
        ]
    return []


def register_problems(
    conn: Connection,
    scope: str,
    number: str,
    doc_type: str | None,
    discipline: str | None,
    *,
    title: str | None = None,
    description: str | None = None,
    originator: str | None = None,
) -> list[str]:
    """Why ``RegisterDocument`` would refuse these values (else empty).

    The same checks as the command makes before it writes: the field limits and validators of the
    model (``field_problems``), the reserved characters, the registry pattern and the two code
    lists, so a plan can say it ahead. It reads only.
    """
    problems = field_problems(
        number=number,
        title=title,
        description=description,
        doc_type=doc_type,
        discipline=discipline,
        originator=originator,
    )
    if problems:
        return problems
    if RESERVED_KEY_CHARS & set(number):
        problems.append(f"number {number!r} holds '@', which the register uses in its own keys")
    for list_name, value, what in (
        (DOCUMENT_TYPE_LIST, doc_type, "document type"),
        (DISCIPLINE_LIST, discipline, "discipline"),
    ):
        try:
            _check_code(conn, scope, list_name, value, what)
        except InvalidDocumentTypeError as exc:
            problems.append(str(exc))
    pattern = patterns.pattern_for(conn, DOCUMENT)
    if pattern is not None and not problems:
        parsed = patterns.parse_number(conn, scope, pattern, number)
        problems.extend(
            f"number {number!r}: {issue.message}"
            for issue in parsed.issues
            if issue.level == "error"
        )
    return problems


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
    if new.current_revision_id is None:
        raise NoChangesError(
            f"document {new.number} has no issued revision yet, so it cannot replace {old.number}"
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
        by_module=True,
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


def handle_set_document_confidentiality(
    uow: UnitOfWork, cmd: SetDocumentConfidentiality
) -> CommandResult:
    """Append ``Document.Updated`` with the new confidentiality class and the reason (controller).

    Raises ``DocumentNotFoundError``, ``DocumentClosedError`` and ``NoChangesError``.
    """
    cmd = correlated(cmd)
    doc = open_document(uow, cmd, cmd.stream_id)
    changes = changes_of(
        {"confidentiality": doc.confidentiality}, {"confidentiality": cmd.confidentiality or None}
    )
    if not changes:
        raise NoChangesError(f"document {doc.number} already has that confidentiality")
    done = append(
        uow,
        cmd,
        doc.id,
        DOCUMENT,
        [NewEvent(event_type=DOCUMENT_UPDATED, payload={"changes": changes, "reason": cmd.reason})],
        expected=cmd.expected_version or doc.version,
    )
    return CommandResult(
        stream_id=doc.id, key=doc.number, version=done.new_version, events=list(done.events)
    )
