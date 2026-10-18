# ruff: noqa: F401, F841
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

STUB (P1-I5-T07a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
    # STEPS
    # 1. `require_project(cmd)`; `cmd = correlated(cmd)`.
    # 2. `arrived = cmd.received_on or today()`. If `arrived > today()` (ISO dates compare as
    #    strings) raise `InvalidItemError(f"received_on {arrived} is after today ({today()})")`.
    # 3. `message_id = normalise_message_id(cmd.message_id)`. When `cmd.message_id is not None`
    #    and `message_id is None` raise `InvalidItemError("message_id is not a usable Message-
    #    ID")`.
    # 4. When `message_id` is not None: `known = find_by_message_id(uow.conn(), cmd.scope,
    #    message_id)`; when `known is not None` raise `InvalidItemError(f"message {message_id}
    #    is already item {known.number}")`.
    # 5. Return `create_item(uow, cmd, subject=cmd.subject, direction="in", medium=cmd.medium,
    #    received_via=cmd.received_via, to=cmd.to, cc=cmd.cc, external_ref=cmd.external_ref,
    #    message_id=message_id, in_reply_to=normalise_message_id(cmd.in_reply_to),
    #    from_party_id=cmd.from_party_id, from_name=cmd.from_name, sent_on=cmd.sent_on,
    #    received_on=arrived, body=cmd.body, response_required=cmd.response_required,
    #    response_due=cmd.response_due, received=True)`. `create_item` allocates the number,
    #    checks dates, parties, recipients and text, and appends everything; do not repeat its
    #    work.
    raise NotImplementedError


def handle_update_correspondence(uow: UnitOfWork, cmd: UpdateCorrespondence) -> CommandResult:
    """Append ``Record.Updated`` (the subject) and ``Correspondence.Updated`` (register fields).

    Raises ``RecordNotFoundError`` (unknown, other scope or hidden), ``ItemStateError`` (the item
    is not a Draft or Received), ``InvalidItemError`` (a bad date, party or text) and
    ``NoChangesError`` (nothing differs).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = open_item(uow, cmd, cmd.stream_id)` (it answers
    #    `RecordNotFoundError` for an unknown, foreign or hidden item and `ItemStateError` for a
    #    closed or replaced one: never read the item any other way); `require_state(item,
    #    ST_DRAFT, ST_RECEIVED)`; `given = cmd.model_fields_set`.
    # 2. `old` is a dict of the register fields as the item has them now: medium, external_ref,
    #    from_party_id, from_name, to, cc, sent_on, received_on, body, response_required,
    #    response_due (the `item.` attributes of the same names). `new` starts empty.
    # 3. For each `name` of `old` that is in `given`: `value = getattr(cmd, name)`. For `to` and
    #    `cc`: a `None` value raises `InvalidItemError(f"{name} is a list; send [] to clear
    #    it")`, otherwise `check_recipients(uow, cmd, value)` and `value = [r.as_payload() for r
    #    in value]`. For `medium` and `response_required`: a `None` value raises
    #    `InvalidItemError(f"{name} cannot be cleared")`. Then `new[name] = value`.
    # 4. `check_party(uow, cmd, [new.get("from_party_id")])`. For `sent_on`, `received_on` and
    #    `response_due` present in `new`: `new[name] = plausible_date(new[name], name)`; a
    #    `ValueError` becomes `InvalidItemError(str(exc))`. A `received_on` that is not None and
    #    later than `today()` raises `InvalidItemError(f"received_on {new['received_on']} is
    #    after today ({today()})")`. When `body` is in `new`: `new["body"] =
    #    check_body(new["body"])`.
    # 5. `register = changes_of(old, new)`; `envelope = changes_of({"title": item.subject},
    #    {"title": cmd.subject} if cmd.subject else {})`. If both are empty raise
    #    `NoChangesError(f"no field of item {item.number} differs from the request")`.
    # 6. `events = []`: when `envelope` add `NewEvent(event_type="Record.Updated",
    #    payload={"changes": envelope})`; when `register` add `NewEvent(event_type=CORR_UPDATED,
    #    payload={"changes": register, "reason": cmd.reason})`.
    # 7. `done = append(uow, cmd, item.id, CORRESPONDENCE, events, expected=cmd.expected_version
    #    or item.version)`; return `CommandResult(stream_id=item.id, key=item.number,
    #    version=done.new_version, events=list(done.events))`.
    raise NotImplementedError
