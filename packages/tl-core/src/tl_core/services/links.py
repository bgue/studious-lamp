"""Link commands: create, accept, decline, repin, verify, flag, retract (brief 7.1, 7.3).

Each handler runs inside an already-entered unit of work and never commits. A refusal raises a
``ServiceError`` before anything is appended. Links are never deleted: ``RetractLink`` ends a
link's life but keeps its row and history. Which event may happen in which status is decided by
``tl_core.links.lifecycle.next_status``; this module adds the checks that need the records.

A link is its own ledger stream (``core.Link``, stream id = ``link_id``) in the scope of its
``from`` record. The ``to`` record must be in the same scope or in ``company`` (brief 3).

STUB (P0-I3-T02): the models, SQL constants and signatures are final; the twelve bodies marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from sqlalchemy import text

from tl_core.links.vocabulary import LinkSource
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

LINK_STREAM_TYPE = "core.Link"


class AddLink(Command):
    from_id: str
    to_id: str
    relation: str | None = None  # a forward relation code; None: the default for the two types
    pin: str | None = None  # a revision label; None floats to the current revision
    link_source: LinkSource = "manual"  # how the link arose (``Command.source`` is the caller)
    note: str | None = None


class SuggestLink(AddLink):
    link_source: LinkSource = "key_detected"
    confidence: float | None = Field(default=None, ge=0, le=1)


class _OnLink(Command):
    link_id: str
    expected_version: int | None = None  # None: whatever version the link has now


class AcceptLink(_OnLink):
    note: str | None = None


class DeclineLink(_OnLink):
    reason: str | None = None


class RepinLink(_OnLink):
    pin: str | None = None  # the new revision label; None floats


class VerifyLink(_OnLink):
    note: str | None = None


class FlagLink(_OnLink):
    status: Literal["stale", "broken"]
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class RetractLink(_OnLink):
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class MarkPinsStale(Command):
    """A new revision of ``record_id`` was issued: flag active links pinned to another revision."""

    record_id: str
    current_pin: str  # the revision label just issued


_RECORD_SQL = text("SELECT id, key, scope, type, voided FROM cur_core_record WHERE id = :id")
_LINK_SQL = text(
    "SELECT link_id, scope, status, pin, version, from_id, to_id FROM cur_links WHERE link_id = :id"
)
_SAME_ENDS_SQL = text(
    "SELECT link_id, status, declined FROM cur_links "
    "WHERE from_id = :from_id AND to_id = :to_id AND relation = :relation"
)
_PINNED_SQL = text(
    "SELECT link_id, scope, version FROM cur_links "
    "WHERE to_id = :id AND status = 'active' AND pin IS NOT NULL AND pin <> :pin "
    "ORDER BY created_at, link_id"
)


def handle_add_link(uow: UnitOfWork, cmd: AddLink) -> CommandResult:
    """Create an active link. Emits ``Link.Added``."""
    raise NotImplementedError


def handle_suggest_link(uow: UnitOfWork, cmd: SuggestLink) -> CommandResult:
    """Create a suggested link that waits for accept or decline. Emits ``Link.Suggested``.

    Raises ``SuggestionDeclinedError`` when a person declined the same suggestion before.
    """
    raise NotImplementedError


def handle_accept_link(uow: UnitOfWork, cmd: AcceptLink) -> CommandResult:
    """Suggested to active. Emits ``Link.Accepted``."""
    raise NotImplementedError


def handle_decline_link(uow: UnitOfWork, cmd: DeclineLink) -> CommandResult:
    """Suggested to retracted, remembered as declined. Emits ``Link.Declined``."""
    raise NotImplementedError


def handle_repin_link(uow: UnitOfWork, cmd: RepinLink) -> CommandResult:
    """Set the pin and bring a stale link back to active. Emits ``Link.Repinned``.

    Raises ``NoChangesError`` for an active link that already has that pin.
    """
    raise NotImplementedError


def handle_verify_link(uow: UnitOfWork, cmd: VerifyLink) -> CommandResult:
    """Mark an active link verified by the actor. Emits ``Link.Verified``."""
    raise NotImplementedError


def handle_flag_link(uow: UnitOfWork, cmd: FlagLink) -> CommandResult:
    """Flag a link stale or broken with a reason. Emits ``Link.Flagged``."""
    raise NotImplementedError


def handle_retract_link(uow: UnitOfWork, cmd: RetractLink) -> CommandResult:
    """End a link's life with a reason. The row and history stay. Emits ``Link.Retracted``."""
    raise NotImplementedError


def handle_mark_pins_stale(uow: UnitOfWork, cmd: MarkPinsStale) -> CommandResult:
    """Flag every active link that points to ``record_id`` with a pin other than ``current_pin``.

    One ``Link.Flagged`` (stale, reason ``revision <current_pin> issued``) per link, in creation
    order. Floating links (no pin) are untouched. Raises ``NoChangesError`` when nothing matches.
    The result's ``stream_id`` is the record; ``version`` is 0 (no record event is written).
    """
    raise NotImplementedError
