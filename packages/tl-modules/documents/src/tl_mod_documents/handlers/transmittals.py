"""Transmittal commands: create, issue, record the answer, close, void (brief 9 M1; P1-I2).

A transmittal (``documents.Transmittal``) is one formal exchange of issued revisions with other
parties. It is drafted with its items and recipients, issued once, answered, and closed. Its number
is typed in or, when the project has a numbering pattern for transmittals, allocated. Only a draft
can be voided: an issued transmittal is the record of what was sent.

=========  =====================================================  =============
State      Meaning                                                Next
=========  =====================================================  =============
Draft      being composed                                         issue, void
Issued     sent; waiting for an answer                            acknowledge, close
Acknowledged  the recipients answered                             close
Closed     finished                                               none
Void       drafted in error                                       none
=========  =====================================================  =============

Each handler runs inside an entered unit of work, appends through it and never commits. A failed
check raises a ``ServiceError`` before anything is appended. All events of one command share one
correlation id.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import (
    InvalidTransmittalError,
    RevisionNotFoundError,
    TransmittalNotFoundError,
    TransmittalStateError,
)
from tl_mod_documents.handlers.common import (
    append,
    check_date,
    correlated,
    load_revision,
    require_project,
    today,
    transition,
)
from tl_mod_documents.limits import (
    MAX_DESCRIPTION,
    MAX_ITEMS,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_documents.names import (
    TRANSMITTAL,
    TRANSMITTAL_DEFINED,
    TRANSMITTAL_ISSUED,
    TRANSMITTAL_RESPONSE,
)

Direction = Literal["outgoing", "incoming"]
Purpose = Literal[
    "for_review",
    "for_information",
    "for_approval",
    "for_construction",
    "as_built",
    "for_record",
]
ResponseCode = Literal["approved", "approved_with_comments", "rejected", "noted"]
#: Revision states a transmittal may carry: issued, current or since superseded.
CARRIABLE = ("Issued", "Superseded")


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class Recipient(BaseModel):
    """Who receives a transmittal."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_TEXT)
    organisation: str | None = Field(default=None, max_length=MAX_TEXT)
    email: str | None = Field(default=None, max_length=MAX_TEXT)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _non_blank(value)


class CreateTransmittal(Command):
    """Draft a transmittal of issued revisions to named recipients.

    ``number`` is typed in; without it the project's numbering pattern for transmittals allocates
    one (``P123-TRN-0001``). ``subject`` is the title.
    """

    model_config = ConfigDict(extra="forbid")

    number: str | None = Field(default=None, min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    direction: Direction = "outgoing"
    purpose: Purpose
    due_date: str | None = None
    recipients: list[Recipient] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    revision_ids: list[str] = Field(min_length=1, max_length=MAX_ITEMS)
    notes: str | None = Field(default=None, max_length=MAX_DESCRIPTION)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return _non_blank(value)

    @field_validator("due_date")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return check_date(value, "due_date")


class IssueTransmittal(Command):
    """Issue a draft transmittal: it is now the record of what was sent."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    issued_on: str | None = None

    @field_validator("issued_on")
    @classmethod
    def _issued(cls, value: str | None) -> str | None:
        return check_date(value, "issued_on")


class RecordTransmittalResponse(Command):
    """Record the recipients' answer to an issued transmittal."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    response_code: ResponseCode
    response_note: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    responded_on: str | None = None

    @field_validator("responded_on")
    @classmethod
    def _responded(cls, value: str | None) -> str | None:
        return check_date(value, "responded_on")


class CloseTransmittal(Command):
    """Close an issued or answered transmittal."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class VoidTransmittal(Command):
    """Void a draft transmittal drafted in error. An issued one is closed, not voided."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def _load(uow: UnitOfWork, cmd: Command, transmittal_id: str) -> registry.TransmittalRow:
    found = registry.get_transmittal(uow.conn(), transmittal_id)
    if found is None or found.scope != cmd.scope:
        raise TransmittalNotFoundError(f"no transmittal {transmittal_id!r} in scope {cmd.scope!r}")
    return found


def _require_state(row: registry.TransmittalRow, *allowed: str, doing: str) -> None:
    if row.voided or row.state not in allowed:
        raise TransmittalStateError(
            f"transmittal {row.number} is {'Void' if row.voided else row.state}; "
            f"it can only be {doing} while {' or '.join(allowed)}"
        )


def _check_revisions(rows: list[registry.RevisionRow]) -> None:
    bad = [
        f"{r.document_number}@{r.code} is {'Void' if r.voided else r.state}"
        for r in rows
        if r.voided or r.state not in CARRIABLE
    ]
    if bad:
        raise InvalidTransmittalError(
            "a transmittal carries issued revisions only; " + "; ".join(bad)
        )


def handle_create_transmittal(uow: UnitOfWork, cmd: CreateTransmittal) -> CommandResult:
    """Append ``Record.Created`` and ``Transmittal.Defined``: a draft with its items.

    Raises ``ProjectScopeError``, ``RevisionNotFoundError`` (an item is unknown or in another
    scope), ``InvalidTransmittalError`` (a revision is repeated, or is not issued),
    ``NoNumberingPatternError`` (no number given and no pattern) and ``DuplicateKeyError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    if len(set(cmd.revision_ids)) != len(cmd.revision_ids):
        raise InvalidTransmittalError("a revision can be on a transmittal only once")
    revisions = [load_revision(uow, cmd, revision_id) for revision_id in cmd.revision_ids]
    _check_revisions(revisions)
    items = [
        {
            "revision_id": r.id,
            "document_id": r.document_id,
            "document_number": r.document_number,
            "revision_code": r.code,
            "issue_status": r.issue_status,
        }
        for r in revisions
    ]
    # The number is known only after the allocator ran (when none was typed in), so the typed event
    # follows the envelope event in a second append of the same stream.
    made = create_module_record(
        uow, cmd, record_type=TRANSMITTAL, title=cmd.subject, description=cmd.notes, key=cmd.number
    )
    done = append(
        uow,
        cmd,
        made.stream_id,
        TRANSMITTAL,
        [
            NewEvent(
                event_type=TRANSMITTAL_DEFINED,
                payload={
                    "number": made.key,
                    "direction": cmd.direction,
                    "purpose": cmd.purpose,
                    "due_date": cmd.due_date,
                    "recipients": [r.model_dump() for r in cmd.recipients],
                    "items": items,
                },
            )
        ],
    )
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=done.new_version,
        events=[*made.events, *done.events],
    )


def handle_issue_transmittal(uow: UnitOfWork, cmd: IssueTransmittal) -> CommandResult:
    """Append ``Transmittal.Issued`` and move the transmittal to Issued.

    Raises ``TransmittalNotFoundError``, ``TransmittalStateError`` (not a draft) and
    ``InvalidTransmittalError`` (a revision on it has been voided since it was drafted).
    """
    cmd = correlated(cmd)
    row = _load(uow, cmd, cmd.stream_id)
    _require_state(row, "Draft", doing="issued")
    items = registry.transmittal_items(uow.conn(), row.id)
    revisions: list[registry.RevisionRow] = []
    for item in items:
        found = registry.get_revision(uow.conn(), item.revision_id)
        if found is None:
            raise RevisionNotFoundError(f"revision {item.revision_id!r} is gone")
        revisions.append(found)
    _check_revisions(revisions)
    events: list[Event] = []
    done = append(
        uow,
        cmd,
        row.id,
        TRANSMITTAL,
        [NewEvent(event_type=TRANSMITTAL_ISSUED, payload={"issued_on": cmd.issued_on or today()})],
        expected=cmd.expected_version,
    )
    events += done.events
    moved = transition(uow, cmd, row.id, "issue")
    events += moved.events
    return CommandResult(stream_id=row.id, key=row.number, version=moved.version, events=events)


def handle_record_transmittal_response(
    uow: UnitOfWork, cmd: RecordTransmittalResponse
) -> CommandResult:
    """Append ``Transmittal.ResponseRecorded`` and move the transmittal to Acknowledged.

    Raises ``TransmittalNotFoundError`` and ``TransmittalStateError`` (not issued).
    """
    cmd = correlated(cmd)
    row = _load(uow, cmd, cmd.stream_id)
    _require_state(row, "Issued", doing="answered")
    events: list[Event] = []
    done = append(
        uow,
        cmd,
        row.id,
        TRANSMITTAL,
        [
            NewEvent(
                event_type=TRANSMITTAL_RESPONSE,
                payload={
                    "response_code": cmd.response_code,
                    "response_note": cmd.response_note,
                    "responded_on": cmd.responded_on or today(),
                },
            )
        ],
        expected=cmd.expected_version,
    )
    events += done.events
    moved = transition(uow, cmd, row.id, "acknowledge")
    events += moved.events
    return CommandResult(stream_id=row.id, key=row.number, version=moved.version, events=events)


def handle_close_transmittal(uow: UnitOfWork, cmd: CloseTransmittal) -> CommandResult:
    """Move an issued or answered transmittal to Closed (``Workflow.Transitioned``).

    Raises ``TransmittalNotFoundError`` and ``TransmittalStateError``.
    """
    cmd = correlated(cmd)
    row = _load(uow, cmd, cmd.stream_id)
    _require_state(row, "Issued", "Acknowledged", doing="closed")
    return transition(
        uow, cmd, row.id, "close", reason=cmd.reason, expected=cmd.expected_version
    ).model_copy(update={"key": row.number})


def handle_void_transmittal(uow: UnitOfWork, cmd: VoidTransmittal) -> CommandResult:
    """Move a draft transmittal to Void and void its record.

    Emits ``Workflow.Transitioned`` and ``Record.Voided``. Raises ``TransmittalNotFoundError`` and
    ``TransmittalStateError`` (not a draft).
    """
    cmd = correlated(cmd)
    row = _load(uow, cmd, cmd.stream_id)
    _require_state(row, "Draft", doing="voided")
    moved = transition(uow, cmd, row.id, "void", reason=cmd.reason, expected=cmd.expected_version)
    voided = append(
        uow,
        cmd,
        row.id,
        TRANSMITTAL,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=row.id,
        key=row.number,
        version=voided.new_version,
        events=[*moved.events, *voided.events],
    )
