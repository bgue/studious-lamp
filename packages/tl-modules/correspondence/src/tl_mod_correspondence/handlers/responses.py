"""Draft a letter, record that an answer exists, close and void an item.

* ``DraftCorrespondence``: a letter we write, optionally an answer to an item. It starts a Draft,
  never lower in class than the item it answers (a reply to a privileged item names the same
  accounts, and its author).
* ``RecordResponse``: an item has an answer (another item). The item moves to Responded and the
  clocks that waited for the answer are met on the answer's day.
* ``CloseCorrespondence``: the item needs no more work. An item that wanted an answer and has none
  needs a reason; its open clocks are cancelled.
* ``VoidDraft`` (any person) and ``VoidCorrespondence`` (a document controller): an item made in
  error. A void item keeps its number and its history; its clocks are cancelled.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError
from tl_mod_correspondence.handlers.clocks import close_clocks_of_item
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    load_item,
    open_item,
    require_project,
    require_state,
    resolve_date,
    today,
    transition,
)
from tl_mod_correspondence.handlers.confidentiality import inherited_class
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Medium, Recipient, non_blank
from tl_mod_correspondence.limits import MAX_BODY, MAX_NUMBER, MAX_REASON, MAX_RECIPIENTS, MAX_TEXT
from tl_mod_correspondence.names import (
    CORR_RESPONDED,
    CORRESPONDENCE,
    ST_DRAFT,
    ST_ISSUED,
    ST_RECEIVED,
    ST_RESPONDED,
    ST_TRIAGED,
)
from tl_mod_correspondence.textcheck import clean_text

ANSWER_CLOCKS = ("response_from_them", "response_from_us")


class DraftCorrespondence(Command):
    """Start a letter we write: a Draft, with its text and recipients, to be issued later.

    ``responds_to_id`` names the item it answers: the letter then takes that item's class (never
    lower) and, unless given, its domain and subtype. A letter needs a domain and subtype before
    it can be issued; ``ReclassifyCorrespondence`` sets them.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    medium: Medium = "letter"
    to: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    responds_to_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    domain: str | None = Field(default=None, max_length=MAX_NUMBER)
    subtype: str | None = Field(default=None, max_length=MAX_NUMBER)
    response_required: bool = False
    response_due: str | None = Field(default=None, max_length=10)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_text(non_blank(value))


class RecordResponse(Command):
    """Record that an item has been answered by another item of the register.

    The item moves to Responded; its clocks that waited for an answer are met on ``responded_on``
    (today by default; an earlier day needs ``reason``).
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    response_id: str = Field(max_length=MAX_NUMBER)
    responded_on: str | None = Field(default=None, max_length=10)
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class CloseCorrespondence(Command):
    """Close an item that needs no more work. Open clocks are cancelled.

    An item that wanted an answer and has none needs a ``reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class VoidDraft(Command):
    """Void a draft made in error (any person who can read it)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


class VoidCorrespondence(Command):
    """Void a draft or a received item filed in error (a document controller's act)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


def handle_draft_correspondence(uow: UnitOfWork, cmd: DraftCorrespondence) -> CommandResult:
    """Create a Draft outgoing item (``create_item``).

    Raises ``CorrespondenceScopeError``, ``RecordNotFoundError`` (the item answered is unknown,
    in another scope or hidden from the viewer), ``ItemStateError`` (that item is void),
    ``InvalidItemError`` and ``UnknownDomainError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    domain, subtype = cmd.domain, cmd.subtype
    confidentiality, clearances = "internal", []
    if cmd.responds_to_id is not None:
        parent = load_item(uow, cmd, cmd.responds_to_id)
        if parent.voided or parent.state == "Void":
            raise ItemStateError(f"item {parent.number} is void and cannot be answered")
        confidentiality, clearances = inherited_class(uow, parent, cmd.actor)
        if domain is None and subtype is None:
            domain, subtype = parent.domain, parent.subtype
    return create_item(
        uow,
        cmd,
        subject=cmd.subject,
        direction="out",
        medium=cmd.medium,
        received_via="manual",
        to=cmd.to,
        cc=cmd.cc,
        body=cmd.body,
        confidentiality=confidentiality,
        clearances=clearances,
        responds_to_id=cmd.responds_to_id,
        response_required=cmd.response_required,
        response_due=cmd.response_due,
        domain=domain,
        subtype=subtype,
    )


def mark_responded(
    uow: UnitOfWork,
    cmd: Command,
    item: registry.ItemRow,
    *,
    response_id: str,
    day: str,
    reason: str | None,
) -> CommandResult:
    """Move ``item`` to Responded and meet its answer clocks. The one place this is done.

    Called by ``RecordResponse`` and by issuing a reply. The item must be Received, Triaged or
    Issued (``ItemStateError`` otherwise).
    """
    require_state(item, ST_RECEIVED, ST_TRIAGED, ST_ISSUED)
    done = append(
        uow,
        cmd,
        item.id,
        CORRESPONDENCE,
        [
            NewEvent(
                event_type=CORR_RESPONDED, payload={"response_id": response_id, "responded_on": day}
            )
        ],
    )
    moved = transition(uow, cmd, item.id, "respond", reason=reason)
    met = close_clocks_of_item(
        uow,
        cmd,
        item.id,
        how="met",
        day=day,
        reason=reason or "answered",
        response_id=response_id,
        kinds=ANSWER_CLOCKS,
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*done.events, *moved.events, *met],
    )


def handle_record_response(uow: UnitOfWork, cmd: RecordResponse) -> CommandResult:
    """Append ``Correspondence.Responded``, move the item to Responded, meet its answer clocks.

    Raises ``RecordNotFoundError`` (the item or the answer is unknown or hidden),
    ``InvalidItemError`` (an item cannot answer itself), ``ItemStateError`` and the date errors
    of ``resolve_date``.
    """
    cmd = correlated(cmd)
    item = open_item(uow, cmd, cmd.stream_id)
    answer = registry.get_item(uow.conn(), cmd.response_id)
    if answer is None or answer.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {cmd.response_id!r}")
    if answer.id == item.id:
        raise InvalidItemError("an item cannot be its own answer")
    day, reason = resolve_date(cmd.responded_on, cmd.reason, "the answer day")
    return mark_responded(uow, cmd, item, response_id=answer.id, day=day, reason=reason)


def handle_close_correspondence(uow: UnitOfWork, cmd: CloseCorrespondence) -> CommandResult:
    """Move the item to Closed and cancel its open clocks.

    Raises ``ItemStateError`` (the item is not Triaged, Issued or Responded; or it wanted an
    answer, has none and no ``reason`` was given).
    """
    cmd = correlated(cmd)
    item = open_item(uow, cmd, cmd.stream_id)
    require_state(item, ST_TRIAGED, ST_ISSUED, ST_RESPONDED)
    unanswered = item.response_required and item.state != ST_RESPONDED
    if unanswered and not (cmd.reason and cmd.reason.strip()):
        raise ItemStateError(
            f"item {item.number} wanted an answer and has none; give the reason for closing it"
        )
    moved = transition(uow, cmd, item.id, "close", reason=cmd.reason, expected=cmd.expected_version)
    cancelled = close_clocks_of_item(
        uow, cmd, item.id, how="cancelled", day=today(), reason=cmd.reason or "item closed"
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*moved.events, *cancelled],
    )


def _void(
    uow: UnitOfWork,
    cmd: VoidDraft | VoidCorrespondence,
    allowed: Sequence[str],
) -> CommandResult:
    cmd = correlated(cmd)
    item = open_item(uow, cmd, cmd.stream_id)
    require_state(item, *allowed)
    cancelled = close_clocks_of_item(
        uow, cmd, item.id, how="cancelled", day=today(), reason=f"item void: {cmd.reason}"
    )
    moved = transition(uow, cmd, item.id, "void", reason=cmd.reason, expected=cmd.expected_version)
    voided = append(
        uow, cmd, item.id, CORRESPONDENCE, [NewEvent(event_type="Record.Voided", payload=_why(cmd))]
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=voided.new_version,
        events=[*cancelled, *moved.events, *voided.events],
    )


def _why(cmd: VoidDraft | VoidCorrespondence) -> dict[str, Any]:
    return {"reason": cmd.reason}


def handle_void_draft(uow: UnitOfWork, cmd: VoidDraft) -> CommandResult:
    """Void a Draft. ``ItemStateError`` for any other state."""
    return _void(uow, cmd, (ST_DRAFT,))


def handle_void_correspondence(uow: UnitOfWork, cmd: VoidCorrespondence) -> CommandResult:
    """Void a Draft or a Received item. ``ItemStateError`` for any other state."""
    return _void(uow, cmd, (ST_DRAFT, ST_RECEIVED))
