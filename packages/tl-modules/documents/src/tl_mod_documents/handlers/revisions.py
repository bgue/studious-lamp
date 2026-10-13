"""Revision commands: create, issue, supersede, void (brief 9 M1; P1-I2).

A revision is a project record (``documents.Revision``) of one document, keyed ``<number>@<code>``.
Its code comes from the document's revision scheme (``schemes.py``). The rules that keep a
document's revisions sound live here:

* a document has at most one revision being prepared or reviewed (Draft or In Review);
* codes only go forward: a new code is after the last one, void revisions included;
* revisions are issued in order: a revision cannot be issued once a later one is;
* a revision needs a PDF or native rendition to be issued;
* **one current revision per status class**: issuing makes the revision current for its class and
  supersedes the one that was; the document row mirrors the newest current revision;
* issuing flags every active link pinned to another revision of the document stale.

Each handler runs inside an entered unit of work, appends through it and never commits. All the
events of one command share one correlation id.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import (
    InvalidRevisionCodeError,
    NoRenditionError,
    OpenRevisionError,
    RevisionSequenceError,
    RevisionStateError,
)
from tl_mod_documents.handlers.common import (
    append,
    check_date,
    correlated,
    load_revision,
    open_document,
    require_project,
    today,
    transition,
    version_of,
)
from tl_mod_documents.limits import MAX_DESCRIPTION, MAX_NUMBER, MAX_REASON, MAX_TEXT
from tl_mod_documents.names import (
    DOC_ISSUED,
    DOCUMENT,
    DOCUMENT_CURRENT_CHANGED,
    ISSUE_KINDS,
    REVISION,
    REVISION_DEFINED,
    REVISION_ISSUED,
    REVISION_SUPERSEDED,
)
from tl_mod_documents.resolver import flag_stale_on_issue
from tl_mod_documents.schemes import load_scheme_file, scheme_by_code, status_class


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class CreateRevision(Command):
    """Start a new revision of a document, as a draft.

    ``code`` defaults to the next code of the document's scheme; ``stage`` starts a new stage of a
    staged scheme (``C`` after ``P3``). The revision date defaults to today.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    code: str | None = Field(default=None, min_length=1, max_length=MAX_NUMBER)
    stage: str | None = Field(default=None, max_length=MAX_NUMBER)
    purpose: str | None = Field(default=None, max_length=MAX_TEXT)
    change_note: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    revision_date: str | None = None
    intended_status: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("revision_date")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        return check_date(value, "revision_date")


class IssueRevision(Command):
    """Issue a draft revision with an issue status (IFR, IFC, AFC, ASB)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    issue_status: str = Field(min_length=1, max_length=MAX_NUMBER)
    issued_on: str | None = None

    @field_validator("issued_on")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        return check_date(value, "issued_on")


class SupersedeRevision(Command):
    """Mark an issued, current revision superseded by a later issued revision of the document."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    superseded_by_id: str
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class VoidRevision(Command):
    """Void a draft revision created in error. An issued revision is superseded, not voided."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def sync_current_revision(
    uow: UnitOfWork, cmd: Command, document_id: str, *, reason: str
) -> list[Event]:
    """Make the document row mirror its newest current revision; return the events appended.

    The newest current revision is the one with the highest ordinal among those current in their
    status class (none when no revision is current). Appends ``Document.CurrentRevisionChanged``
    only when the document row differs.
    """
    doc = registry.get_document(uow.conn(), document_id)
    assert doc is not None
    currents = registry.current_revisions(uow.conn(), document_id)
    top = currents[0] if currents else None
    same = (top is None and doc.current_revision_id is None) or (
        top is not None and top.id == doc.current_revision_id
    )
    if same:
        return []
    done = append(
        uow,
        cmd,
        document_id,
        DOCUMENT,
        [
            NewEvent(
                event_type=DOCUMENT_CURRENT_CHANGED,
                payload={
                    "current_revision_id": None if top is None else top.id,
                    "current_revision_code": None if top is None else top.code,
                    "current_revision_status": None if top is None else top.issue_status,
                    "current_revision_class": None if top is None else top.status_class,
                    "current_revision_issued_on": None if top is None else top.issued_on,
                    "previous_revision_id": doc.current_revision_id,
                    "reason": reason,
                },
            )
        ],
    )
    return list(done.events)


def handle_create_revision(uow: UnitOfWork, cmd: CreateRevision) -> CommandResult:
    """Append ``Record.Created`` and ``Revision.Defined`` for the next revision of a document.

    Raises ``ProjectScopeError``, ``DocumentNotFoundError``, ``DocumentClosedError``,
    ``OpenRevisionError`` (a draft or a review is already open), ``InvalidRevisionCodeError``,
    ``InvalidIssueStatusError``, ``UnknownSchemeError`` and ``DuplicateKeyError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    doc = open_document(uow, cmd, cmd.document_id)
    conn = uow.conn()
    pending = registry.open_revision(conn, doc.id)
    if pending is not None:
        raise OpenRevisionError(
            f"revision {pending.code} of {doc.number} is still {pending.state}; "
            "issue or void it before starting another"
        )
    config = load_scheme_file()
    scheme = scheme_by_code(config, doc.revision_scheme)
    last = registry.last_revision(conn, doc.id)
    if cmd.code is not None and cmd.stage is not None:
        raise InvalidRevisionCodeError("give a code or a stage, not both")
    if cmd.code is not None:
        scheme.validate_after(cmd.code, None if last is None else last.code)
        code = cmd.code
    else:
        code = scheme.next_code(None if last is None else last.code, stage=cmd.stage)
    if cmd.intended_status is not None:
        status_class(config, cmd.intended_status)  # raises InvalidIssueStatusError
    made = create_module_record(
        uow,
        cmd,
        record_type=REVISION,
        title=f"{doc.number} rev {code}",
        key=f"{doc.number}@{code}",
        extra_events=[
            NewEvent(
                event_type=REVISION_DEFINED,
                payload={
                    "document_id": doc.id,
                    "document_number": doc.number,
                    "code": code,
                    "ordinal": 1 if last is None else last.ordinal + 1,
                    "previous_revision_id": None if last is None else last.id,
                    "purpose": cmd.purpose,
                    "change_note": cmd.change_note,
                    "revision_date": cmd.revision_date or today(),
                    "intended_status": cmd.intended_status,
                },
            )
        ],
    )
    return made


def handle_issue_revision(uow: UnitOfWork, cmd: IssueRevision) -> CommandResult:
    """Issue a draft revision: it becomes current for its status class and the document follows.

    In one unit of work and one correlation: ``Revision.Issued`` and the revision's ``issue``
    transition; ``Revision.Superseded`` and ``supersede`` for the revision that was current in the
    class; ``Document.CurrentRevisionChanged``; the document's ``issue`` transition when it was
    Registered or In Review; and a ``Link.Flagged`` (stale) for every active link pinned to
    another revision. Raises ``RevisionNotFoundError``, ``RevisionStateError`` (not a draft),
    ``InvalidIssueStatusError``, ``RevisionSequenceError`` (a later revision is issued),
    ``NoRenditionError`` (no PDF or native rendition), ``DocumentClosedError``.
    """
    cmd = correlated(cmd)
    rev = load_revision(uow, cmd, cmd.stream_id)
    doc = open_document(uow, cmd, rev.document_id)
    conn = uow.conn()
    if rev.voided or rev.state != "Draft":
        raise RevisionStateError(
            f"revision {rev.code} of {doc.number} is {rev.state}; only a draft can be issued"
            + ("; close its review first" if rev.state == "In Review" else "")
        )
    config = load_scheme_file()
    cls = status_class(config, cmd.issue_status)
    highest = registry.highest_issued_ordinal(conn, doc.id)
    if rev.ordinal < highest:
        raise RevisionSequenceError(
            f"a later revision of {doc.number} is already issued; {rev.code} cannot be issued now"
        )
    copies = [
        r for r in registry.renditions_of(conn, rev.id, current_only=True) if r.kind in ISSUE_KINDS
    ]
    if not copies:
        raise NoRenditionError(
            f"revision {rev.code} of {doc.number} has no PDF or native rendition; attach one first"
        )
    issued_on = cmd.issued_on or today()
    replaced = [r for r in registry.current_revisions(conn, doc.id) if r.status_class == cls]
    events: list[Event] = []

    done = append(
        uow,
        cmd,
        rev.id,
        REVISION,
        [
            NewEvent(
                event_type=REVISION_ISSUED,
                payload={
                    "issue_status": cmd.issue_status,
                    "status_class": cls,
                    "issued_on": issued_on,
                    "superseded_revision_ids": [r.id for r in replaced],
                },
            )
        ],
        expected=cmd.expected_version or rev.version,
    )
    events += done.events
    events += transition(uow, cmd, rev.id, "issue").events
    for old in replaced:
        events += append(
            uow,
            cmd,
            old.id,
            REVISION,
            [
                NewEvent(
                    event_type=REVISION_SUPERSEDED,
                    payload={
                        "superseded_by": rev.id,
                        "status_class": cls,
                        "reason": f"revision {rev.code} issued",
                    },
                )
            ],
        ).events
        events += transition(uow, cmd, old.id, "supersede").events
    events += sync_current_revision(uow, cmd, doc.id, reason="issued")
    if doc.state != DOC_ISSUED:
        events += transition(uow, cmd, doc.id, "issue").events
    events += flag_stale_on_issue(uow, cmd, doc.id, rev.code)
    return CommandResult(stream_id=rev.id, key=rev.key, version=done.new_version, events=events)


def handle_supersede_revision(uow: UnitOfWork, cmd: SupersedeRevision) -> CommandResult:
    """Mark an issued, current revision superseded by a later issued revision of the same document.

    Emits ``Revision.Superseded``, the revision's ``supersede`` transition and, if it was the
    document's current revision, ``Document.CurrentRevisionChanged``. Raises
    ``RevisionNotFoundError``, ``RevisionStateError`` (not issued and current, or the replacement
    is not a later issued revision of the same document) and ``DocumentClosedError``.
    """
    cmd = correlated(cmd)
    rev = load_revision(uow, cmd, cmd.stream_id)
    doc = open_document(uow, cmd, rev.document_id)
    by = load_revision(uow, cmd, cmd.superseded_by_id)
    if rev.state != "Issued" or not rev.is_current:
        raise RevisionStateError(
            f"revision {rev.code} of {doc.number} is {rev.state}; only an issued, current "
            "revision can be superseded"
        )
    if by.document_id != doc.id or not by.issued or by.voided or by.ordinal <= rev.ordinal:
        raise RevisionStateError(
            f"revision {by.code} is not a later issued revision of {doc.number}"
        )
    events: list[Event] = []
    done = append(
        uow,
        cmd,
        rev.id,
        REVISION,
        [
            NewEvent(
                event_type=REVISION_SUPERSEDED,
                payload={
                    "superseded_by": by.id,
                    "status_class": rev.status_class,
                    "reason": cmd.reason,
                },
            )
        ],
        expected=cmd.expected_version or rev.version,
    )
    events += done.events
    events += transition(uow, cmd, rev.id, "supersede", reason=cmd.reason).events
    events += sync_current_revision(uow, cmd, doc.id, reason="superseded")
    return CommandResult(
        stream_id=rev.id, key=rev.key, version=version_of(uow, rev.id), events=events
    )


def handle_void_revision(uow: UnitOfWork, cmd: VoidRevision) -> CommandResult:
    """Void a draft revision (never issued): ``Workflow.Transitioned`` and ``Record.Voided``.

    The revision keeps its code, so a code is never used twice. Raises ``RevisionNotFoundError``,
    ``RevisionStateError`` (issued, in review or already void) and ``DocumentClosedError``.
    """
    cmd = correlated(cmd)
    rev = load_revision(uow, cmd, cmd.stream_id)
    open_document(uow, cmd, rev.document_id)
    if rev.voided or rev.state != "Draft":
        raise RevisionStateError(
            f"revision {rev.code} of {rev.document_number} is {rev.state}; "
            "only a draft can be voided"
            + ("; close its review first" if rev.state == "In Review" else "")
            + ("; an issued revision is superseded instead" if rev.issued else "")
        )
    moved = transition(uow, cmd, rev.id, "void", reason=cmd.reason, expected=cmd.expected_version)
    voided = append(
        uow,
        cmd,
        rev.id,
        REVISION,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=rev.id,
        key=rev.key,
        version=voided.new_version,
        events=[*moved.events, *voided.events],
    )
