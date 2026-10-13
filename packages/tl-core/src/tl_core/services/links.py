"""Link commands: create, accept, decline, repin, verify, flag, retract (brief 7.1, 7.3).

Each handler runs inside an already-entered unit of work and never commits. A refusal raises a
``ServiceError`` before anything is appended. Links are never deleted: ``RetractLink`` ends a
link's life but keeps its row and history. Which event may happen in which status is decided by
``tl_core.links.lifecycle.next_status``; this module adds the checks that need the records.

A link is its own ledger stream (``core.Link``, stream id = ``link_id``) in the scope of its
``from`` record. The ``to`` record must be in the same scope or in ``company`` (brief 3).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal

from pydantic import Field, field_validator
from sqlalchemy import text

from tl_core.ledger import Event, NewEvent
from tl_core.links.lifecycle import next_status
from tl_core.links.provider import get_vocabulary
from tl_core.links.vocabulary import LinkSource, default_relation
from tl_core.modules import is_module_record_type, require_generic
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import (
    CrossScopeLinkError,
    DuplicateLinkError,
    LinkNotFoundError,
    NoChangesError,
    RecordNotFoundError,
    RecordVoidedError,
    ReservedLinkSourceError,
    SelfLinkError,
    SuggestionDeclinedError,
    UnknownRelationError,
    UnsupportedRecordTypeError,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

LINK_STREAM_TYPE = "core.Link"
POST_RECORD_TYPE = "core.ActivityPost"


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


class AdminFlagLink(FlagLink):
    """Admin: flag any link stale or broken, including one a module wrote by rule (recovery)."""


class AdminRetractLink(RetractLink):
    """Admin: retract any link, including one a module wrote by rule (recovery)."""


class MarkPinsStale(Command):
    """A new revision of ``record_id`` was issued: flag active links pinned to another revision."""

    record_id: str
    current_pin: str  # the revision label just issued


_RECORD_SQL = text("SELECT id, key, scope, type, voided FROM cur_core_record WHERE id = :id")
_POST_SQL = text(
    "SELECT item_id, scope, retracted FROM cur_feed_items "
    "WHERE item_id = :id AND item_type = 'post'"
)
_LINK_SQL = text(
    "SELECT link_id, scope, status, pin, version, from_id, to_id, source "
    "FROM cur_links WHERE link_id = :id"
)
_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")
#: The generic command that makes each link event (ADR-0010 addendum: the life of a link).
_COMMAND_OF = {
    "Link.Accepted": "AcceptLink",
    "Link.Declined": "DeclineLink",
    "Link.Repinned": "RepinLink",
    "Link.Verified": "VerifyLink",
    "Link.Flagged": "FlagLink",
    "Link.Retracted": "RetractLink",
}
#: A relation only a module may write onto a module record: the module's own commands say
#: "this replaces that"; a person cannot claim it with a generic link.
RESERVED_RELATION = "supersedes"
#: Link sources only the system may claim: a rule, an enricher, an import and a mapping write
#: links no person made, and a link of such a source is kept by the module that wrote it. A client
#: that could claim one would make a link nobody can retract (P1-I2 security review).
SYSTEM_LINK_SOURCES = frozenset({"rule", "enricher", "import", "mapping"})
_SAME_ENDS_SQL = text(
    "SELECT link_id, status, declined FROM cur_links "
    "WHERE from_id = :from_id AND to_id = :to_id AND relation = :relation"
)
_PINNED_SQL = text(
    "SELECT link_id, scope, version FROM cur_links "
    "WHERE to_id = :id AND status = 'active' AND pin IS NOT NULL AND pin <> :pin "
    "ORDER BY created_at, link_id"
)


def _record(uow: UnitOfWork, record_id: str, *, allow_post: bool = False) -> Any:
    """The current row of a record (id, key, scope, type, voided); missing raises.

    With ``allow_post`` a feed post also counts as a record (type ``core.ActivityPost``, no key,
    "voided" once retracted). Only the ``from`` end of a link may be a post: a post references
    records (brief 21.2), records do not reference posts.
    """
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None and allow_post:
        post = uow.conn().execute(_POST_SQL, {"id": record_id}).first()
        if post is not None:
            return SimpleNamespace(
                id=post.item_id,
                key=None,
                scope=post.scope,
                type=POST_RECORD_TYPE,
                voided=bool(post.retracted),
            )
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    return row


def _create(
    uow: UnitOfWork,
    cmd: AddLink,
    event_type: str,
    extra: dict[str, Any],
    *,
    by_module: bool = False,
) -> CommandResult:
    """Shared body of ``handle_add_link`` and ``handle_suggest_link``."""
    if cmd.link_source in SYSTEM_LINK_SOURCES and not by_module:
        raise ReservedLinkSourceError(
            f"link source {cmd.link_source!r} is for links the system writes; "
            "a person's or an agent's link is manual"
        )
    source = _record(uow, cmd.from_id, allow_post=True)
    if not by_module:
        require_generic(
            uow.conn(),
            source.type,
            "SuggestLink" if event_type == "Link.Suggested" else "AddLink",
            source.id,
        )
    if source.type == POST_RECORD_TYPE and cmd.relation != "references":
        raise UnknownRelationError(
            f"a feed post can only reference records; relation {cmd.relation or 'default'!r} "
            "is not allowed from a post"
        )
    if source.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {cmd.from_id!r} in scope {cmd.scope!r}")
    target = _record(uow, cmd.to_id)
    if cmd.from_id == cmd.to_id:
        raise SelfLinkError("a record cannot be linked to itself")
    if target.scope not in (cmd.scope, "company"):
        raise CrossScopeLinkError(
            f"{target.key or cmd.to_id} is in {target.scope}; "
            "links may only point to the same scope or to company records"
        )
    for end in (source, target):
        if end.voided:
            raise RecordVoidedError(f"record {end.key or end.id} is voided and cannot be linked")

    relation = cmd.relation or default_relation(source.type, target.type)
    get_vocabulary().get(relation)  # raises UnknownRelationError for an unknown or inverse code
    if relation == RESERVED_RELATION and not by_module and is_module_record_type(target.type):
        raise UnsupportedRecordTypeError(
            f"a {relation} link to a {target.type} record is made by that module's own "
            "commands (a rename, a split, a merge, a supersession), not by a generic link"
        )

    link_id = new_ulid()
    same_ends = (
        uow.conn()
        .execute(_SAME_ENDS_SQL, {"from_id": cmd.from_id, "to_id": cmd.to_id, "relation": relation})
        .all()
    )
    for prior in same_ends:
        if event_type == "Link.Suggested" and prior.declined:
            raise SuggestionDeclinedError(
                f"this suggestion ({relation}) was declined before; add the link by hand instead"
            )
        if prior.status != "retracted":
            raise DuplicateLinkError(
                f"a {relation} link already exists between these records "
                f"({prior.status}, {prior.link_id})"
            )

    result = uow.append(
        stream_id=link_id,
        stream_type=LINK_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type=event_type,
                payload={
                    "link_id": link_id,
                    "from_ref": cmd.from_id,
                    "to_ref": cmd.to_id,
                    "relation": relation,
                    "pin": cmd.pin,
                    "source": cmd.link_source,
                    "note": cmd.note,
                    **extra,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=link_id,
        key=None,
        version=result.new_version,
        events=result.events,
    )


def _act(
    uow: UnitOfWork,
    cmd: _OnLink,
    event_type: str,
    payload: dict[str, Any],
    *,
    flag: str | None = None,
    same_pin_is_noop: bool = False,
    by_module: bool = False,
) -> CommandResult:
    """Shared body of the six lifecycle handlers."""
    link = uow.conn().execute(_LINK_SQL, {"id": cmd.link_id}).first()
    if link is None or link.scope != cmd.scope:
        raise LinkNotFoundError(f"no link {cmd.link_id!r} in scope {cmd.scope!r}")
    if not by_module:
        _require_owner_allows(uow, link, event_type)
    next_status(link.status, event_type, flag=flag)  # raises InvalidLinkTransitionError
    if same_pin_is_noop and link.status == "active" and link.pin == payload["pin"]:
        raise NoChangesError(f"link {cmd.link_id} already has that pin")

    expected = cmd.expected_version if cmd.expected_version is not None else link.version
    result = uow.append(
        stream_id=cmd.link_id,
        stream_type=LINK_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[NewEvent(event_type=event_type, payload={"link_id": cmd.link_id, **payload})],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.link_id,
        key=None,
        version=result.new_version,
        events=result.events,
    )


def _require_owner_allows(uow: UnitOfWork, link: Any, event_type: str) -> None:
    """The record a link starts at must allow the generic command, and a rule's link is kept.

    A link belongs to the record it starts at (ADR-0010 addendum). Phase 1 has no per-record
    access lists, so this is about the record *type* and the link's origin, not about who owns it.
    A link a module wrote by rule (``source`` rule, from a module record) is flagged or retracted
    only by that module's commands.
    """
    owner = uow.conn().execute(_TYPE_SQL, {"id": link.from_id}).scalar_one_or_none()
    if owner is None:  # a feed post is the start of a reference, not a module record
        return
    require_generic(uow.conn(), owner, _COMMAND_OF[event_type], link.from_id)
    if (
        link.source == "rule"
        and event_type in ("Link.Flagged", "Link.Retracted")
        and is_module_record_type(owner)
    ):
        raise UnsupportedRecordTypeError(
            f"this link was written by a rule of the module that owns {owner}; "
            "it changes through that module's commands"
        )


def handle_add_link(uow: UnitOfWork, cmd: AddLink, *, by_module: bool = False) -> CommandResult:
    """Create an active link. Emits ``Link.Added``.

    ``by_module`` is for a module or service path: its own command makes the link, so the type's
    generic-command allow-list, the reserved ``supersedes`` relation and the system link sources
    (``rule``, ``enricher``, ``import``, ``mapping``) do not apply. It is a Python argument, not a
    field of the command, so no client can set it.
    """
    return _create(uow, cmd, "Link.Added", {}, by_module=by_module)


def handle_suggest_link(
    uow: UnitOfWork, cmd: SuggestLink, *, by_module: bool = False
) -> CommandResult:
    """Create a suggested link that waits for accept or decline. Emits ``Link.Suggested``.

    Raises ``SuggestionDeclinedError`` when a person declined the same suggestion before.
    """
    return _create(uow, cmd, "Link.Suggested", {"confidence": cmd.confidence}, by_module=by_module)


def handle_accept_link(
    uow: UnitOfWork, cmd: AcceptLink, *, by_module: bool = False
) -> CommandResult:
    """Suggested to active. Emits ``Link.Accepted``."""
    return _act(uow, cmd, "Link.Accepted", {"note": cmd.note}, by_module=by_module)


def handle_decline_link(
    uow: UnitOfWork, cmd: DeclineLink, *, by_module: bool = False
) -> CommandResult:
    """Suggested to retracted, remembered as declined. Emits ``Link.Declined``."""
    return _act(uow, cmd, "Link.Declined", {"reason": cmd.reason}, by_module=by_module)


def handle_repin_link(uow: UnitOfWork, cmd: RepinLink, *, by_module: bool = False) -> CommandResult:
    """Set the pin and bring a stale link back to active. Emits ``Link.Repinned``.

    Raises ``NoChangesError`` for an active link that already has that pin.
    """
    return _act(
        uow, cmd, "Link.Repinned", {"pin": cmd.pin}, same_pin_is_noop=True, by_module=by_module
    )


def handle_verify_link(
    uow: UnitOfWork, cmd: VerifyLink, *, by_module: bool = False
) -> CommandResult:
    """Mark an active link verified by the actor. Emits ``Link.Verified``."""
    return _act(uow, cmd, "Link.Verified", {"note": cmd.note}, by_module=by_module)


def handle_flag_link(uow: UnitOfWork, cmd: FlagLink, *, by_module: bool = False) -> CommandResult:
    """Flag a link stale or broken with a reason. Emits ``Link.Flagged``."""
    return _act(
        uow,
        cmd,
        "Link.Flagged",
        {"status": cmd.status, "reason": cmd.reason},
        flag=cmd.status,
        by_module=by_module,
    )


def handle_retract_link(
    uow: UnitOfWork, cmd: RetractLink, *, by_module: bool = False
) -> CommandResult:
    """End a link's life with a reason. The row and history stay. Emits ``Link.Retracted``."""
    return _act(uow, cmd, "Link.Retracted", {"reason": cmd.reason}, by_module=by_module)


def handle_admin_flag_link(uow: UnitOfWork, cmd: AdminFlagLink) -> CommandResult:
    """Flag a link whatever its source or owner. The API gates it to an admin (ADR-0011)."""
    return handle_flag_link(uow, cmd, by_module=True)


def handle_admin_retract_link(uow: UnitOfWork, cmd: AdminRetractLink) -> CommandResult:
    """Retract a link whatever its source or owner. The API gates it to an admin (ADR-0011)."""
    return handle_retract_link(uow, cmd, by_module=True)


def handle_mark_pins_stale(uow: UnitOfWork, cmd: MarkPinsStale) -> CommandResult:
    """Flag every active link that points to ``record_id`` with a pin other than ``current_pin``.

    One ``Link.Flagged`` (stale, reason ``revision <current_pin> issued``) per link, in creation
    order. Floating links (no pin) are untouched. Raises ``NoChangesError`` when nothing matches.
    The result's ``stream_id`` is the record; ``version`` is 0 (no record event is written).
    """
    target = _record(uow, cmd.record_id)
    if target.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {cmd.record_id!r} in scope {cmd.scope!r}")
    pinned = uow.conn().execute(_PINNED_SQL, {"id": cmd.record_id, "pin": cmd.current_pin}).all()
    if not pinned:
        raise NoChangesError(f"no active link to {target.key or cmd.record_id} has an older pin")

    correlation_id = cmd.correlation_id or new_ulid()
    events: list[Event] = []
    for link in pinned:
        result = uow.append(
            stream_id=link.link_id,
            stream_type=LINK_STREAM_TYPE,
            scope=link.scope,
            expected_version=link.version,
            events=[
                NewEvent(
                    event_type="Link.Flagged",
                    payload={
                        "link_id": link.link_id,
                        "status": "stale",
                        "reason": f"revision {cmd.current_pin} issued",
                    },
                )
            ],
            actor=cmd.actor,
            source=cmd.source,
            correlation_id=correlation_id,
            causation_id=cmd.causation_id,
        )
        events.extend(result.events)
    return CommandResult(
        stream_id=cmd.record_id,
        key=target.key,
        version=0,
        events=events,
    )
