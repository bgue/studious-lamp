"""Receive an item and change its register fields (brief 9 M10; P1-I5).

``ReceiveCorrespondence`` logs an item that arrived (a letter uploaded, an email ingested, a note
typed): it takes a number from the numbering pattern, starts in state Received, and is
``internal`` until a document controller sets another class. The file itself is attached after
the command, by a file upload into the slot ``original`` or ``attachment``. Triage, which gives
the item its domain, is a separate act (``ConfirmTriage``).

``UpdateCorrespondence`` changes the register fields of a draft or of an item that is only
received. After triage the fields are the record of what was triaged; use
``ReclassifyCorrespondence`` or a new item. Each handler runs inside an entered unit of work,
appends through it and never commits; a failed check raises a ``ServiceError`` before anything is
appended.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence.errors import InvalidItemError
from tl_mod_correspondence.handlers.common import (
    append,
    changes_of,
    correlated,
    open_item,
    plausible_date,
    require_project,
    require_state,
    today,
)
from tl_mod_correspondence.handlers.create import (
    check_body,
    check_party,
    check_recipients,
    create_item,
)
from tl_mod_correspondence.handlers.models import Medium, Recipient, Via, non_blank
from tl_mod_correspondence.limits import (
    MAX_BODY,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_correspondence.names import CORR_UPDATED, CORRESPONDENCE, ST_DRAFT, ST_RECEIVED
from tl_mod_correspondence.registry import find_by_message_id
from tl_mod_correspondence.textcheck import clean_optional_text, clean_text
from tl_mod_correspondence.threading import normalise_message_id


class ReceiveCorrespondence(Command):
    """Log an item that arrived. It is numbered, starts Received and is `internal`.

    ``received_on`` is the day it arrived (today by default; never after today). ``message_id``
    and ``in_reply_to`` are the email header values when there are any; an item whose message id
    is already in the register is refused. Attach the file afterwards, in the slot ``original``.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    medium: Medium = "letter"
    received_via: Via = "manual"
    external_ref: str | None = Field(default=None, max_length=MAX_NUMBER)
    message_id: str | None = Field(default=None, max_length=MAX_TEXT)
    in_reply_to: str | None = Field(default=None, max_length=MAX_TEXT)
    from_party_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    from_name: str | None = Field(default=None, max_length=MAX_TEXT)
    to: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    sent_on: str | None = Field(default=None, max_length=10)
    received_on: str | None = Field(default=None, max_length=10)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    response_required: bool = False
    response_due: str | None = Field(default=None, max_length=10)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("external_ref", "from_name", "message_id", "in_reply_to")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class UpdateCorrespondence(Command):
    """Change the register fields of a draft or a received item (not its number, direction,
    domain or class). A field you leave out stays as it is; ``null`` clears an optional one."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    medium: Medium | None = None
    external_ref: str | None = Field(default=None, max_length=MAX_NUMBER)
    from_party_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    from_name: str | None = Field(default=None, max_length=MAX_TEXT)
    to: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    sent_on: str | None = Field(default=None, max_length=10)
    received_on: str | None = Field(default=None, max_length=10)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    response_required: bool | None = None
    response_due: str | None = Field(default=None, max_length=10)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(non_blank(value))

    @field_validator("external_ref", "from_name")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def handle_receive_correspondence(uow: UnitOfWork, cmd: ReceiveCorrespondence) -> CommandResult:
    """Append ``Record.Created``, ``Correspondence.Defined`` and the move to Received.

    Raises ``CorrespondenceScopeError`` (not a project scope), ``InvalidItemError`` (a date after
    today or not a date, an unknown party, a text with a control character, a message id that is
    already in the register), and ``NoNumberingPatternError`` (no pattern for items).
    """
    require_project(cmd)
    cmd = correlated(cmd)
    arrived = cmd.received_on or today()
    if arrived > today():
        raise InvalidItemError(f"received_on {arrived} is after today ({today()})")
    message_id = normalise_message_id(cmd.message_id)
    if cmd.message_id is not None and message_id is None:
        raise InvalidItemError("message_id is not a usable Message-ID")
    if message_id is not None:
        known = find_by_message_id(uow.conn(), cmd.scope, message_id)
        if known is not None:
            raise InvalidItemError(f"message {message_id} is already item {known.number}")
    return create_item(
        uow,
        cmd,
        subject=cmd.subject,
        direction="in",
        medium=cmd.medium,
        received_via=cmd.received_via,
        to=cmd.to,
        cc=cmd.cc,
        external_ref=cmd.external_ref,
        message_id=message_id,
        in_reply_to=normalise_message_id(cmd.in_reply_to),
        from_party_id=cmd.from_party_id,
        from_name=cmd.from_name,
        sent_on=cmd.sent_on,
        received_on=arrived,
        body=cmd.body,
        response_required=cmd.response_required,
        response_due=cmd.response_due,
        received=True,
    )


def handle_update_correspondence(uow: UnitOfWork, cmd: UpdateCorrespondence) -> CommandResult:
    """Append ``Record.Updated`` (the subject) and ``Correspondence.Updated`` (register fields).

    Raises ``RecordNotFoundError`` (unknown, other scope or hidden), ``ItemStateError`` (the item
    is not a Draft or Received), ``InvalidItemError`` (a bad date, party or text) and
    ``NoChangesError`` (nothing differs).
    """
    cmd = correlated(cmd)
    item = open_item(uow, cmd, cmd.stream_id)
    require_state(item, ST_DRAFT, ST_RECEIVED)
    given = cmd.model_fields_set
    old: dict[str, Any] = {
        "medium": item.medium,
        "external_ref": item.external_ref,
        "from_party_id": item.from_party_id,
        "from_name": item.from_name,
        "to": item.to,
        "cc": item.cc,
        "sent_on": item.sent_on,
        "received_on": item.received_on,
        "body": item.body,
        "response_required": item.response_required,
        "response_due": item.response_due,
    }
    new: dict[str, Any] = {}
    for name in old:
        if name not in given:
            continue
        value: Any = getattr(cmd, name)
        if name in ("to", "cc"):
            if value is None:
                raise InvalidItemError(f"{name} is a list; send [] to clear it")
            check_recipients(uow, cmd, value)
            value = [r.as_payload() for r in value]
        if name in ("medium", "response_required") and value is None:
            raise InvalidItemError(f"{name} cannot be cleared")
        new[name] = value
    check_party(uow, cmd, [new.get("from_party_id")])
    for name in ("sent_on", "received_on", "response_due"):
        if name in new:
            try:
                new[name] = plausible_date(new[name], name)
            except ValueError as exc:
                raise InvalidItemError(str(exc)) from exc
    later = new.get("received_on")
    if "received_on" in new and later is not None and later > today():
        raise InvalidItemError(f"received_on {later} is after today ({today()})")
    if "body" in new:
        new["body"] = check_body(new["body"])
    register = changes_of(old, new)
    envelope = changes_of({"title": item.subject}, {"title": cmd.subject} if cmd.subject else {})
    if not register and not envelope:
        raise NoChangesError(f"no field of item {item.number} differs from the request")
    events: list[NewEvent] = []
    if envelope:
        events.append(NewEvent(event_type="Record.Updated", payload={"changes": envelope}))
    if register:
        events.append(
            NewEvent(
                event_type=CORR_UPDATED,
                payload={"changes": register, "reason": cmd.reason},
            )
        )
    done = append(
        uow,
        cmd,
        item.id,
        CORRESPONDENCE,
        events,
        expected=cmd.expected_version or item.version,
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=done.new_version,
        events=list(done.events),
    )
