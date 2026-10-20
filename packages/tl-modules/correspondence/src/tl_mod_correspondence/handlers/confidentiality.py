"""Confidentiality commands: set an item's class, name and unname who may read it (ADR-0016).

A class is ``internal`` (any signed-in person and agent), ``restricted`` (a document controller or
admin; no agent) or ``privileged`` (only the accounts named on the item; nobody else, an admin
included). These commands are a document controller's: **setting a class is the controlled act**,
and a person cannot raise the class of their own item to hide it from review. Setting the class
reads the item through the viewer, so a controller who is not named on a privileged item cannot
see it or change its class; naming and unnaming readers work by id (see below).

Rules that keep a privileged item readable and honest:

* making an item privileged needs at least one account to name, and the person who runs the command
  is always named (they could not read the item otherwise);
* a clearance is granted only to an active person account (an agent never reads a privileged
  item), and the last clearance of a privileged item cannot be withdrawn;
* leaving the privileged class withdraws every clearance, so a later return to it starts empty.

**Lock-out (ADR-0016 section 2).** Naming and unnaming readers (``GrantClearance``,
``WithdrawClearance``) work **by id** for a controller-level actor who is not named on the item:
the handler checks that the item exists in the scope and that it is privileged, and shows nothing
of it. Setting the class reads the item through the viewer: a controller who cannot read it
cannot change its class, only name someone who can.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.queries import find_account
from tl_core.ledger import AppendResult, Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import ClearanceError
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    load_item,
    load_item_for_control,
    today,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.limits import MAX_CLEARANCES, MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_CLASS_CHANGED,
    CORR_CLEARANCE_GRANTED,
    CORR_CLEARANCE_WITHDRAWN,
    LIMITS_NOTE_CLASSES,
)

ItemClass = Literal["internal", "restricted", "privileged"]


_non_blank = non_blank


class SetCorrespondenceConfidentiality(Command):
    """Set the confidentiality class of an item (a document controller's act). The reason is kept.

    ``privileged`` needs ``grant``: the accounts (``user:<name>``) that may read the item; the
    person who runs the command is named too. Any other class takes no ``grant``. Leaving
    ``privileged`` withdraws every clearance. Confidentiality is enforced (ADR-0016).
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    to_class: ItemClass = Field(description=LIMITS_NOTE_CLASSES)
    reason: str = Field(max_length=MAX_REASON)
    grant: list[str] = Field(default_factory=list, max_length=MAX_CLEARANCES)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class GrantClearance(Command):
    """Name an account that may read a privileged item (a document controller's act)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    account: str = Field(min_length=6, max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class WithdrawClearance(Command):
    """Remove an account from the readers of a privileged item (a document controller's act).

    The last clearance cannot be withdrawn: change the class instead.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    account: str = Field(min_length=6, max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def require_person(uow: UnitOfWork, account: str) -> str:
    """``account`` when it names an active person account; otherwise ``ClearanceError``."""
    if not account.startswith("user:"):
        raise ClearanceError(f"{account!r} is not a person account (user:<name>)")
    found = find_account(uow.conn(), username=account[len("user:") :])
    if found is None or found.status != "active" or found.kind == "agent":
        raise ClearanceError(f"{account!r} is not an active person account")
    return account


def granted_events(accounts: list[str], reason: str) -> list[NewEvent]:
    return [
        NewEvent(
            event_type=CORR_CLEARANCE_GRANTED,
            payload={"account": account, "granted_on": today(), "reason": reason},
        )
        for account in accounts
    ]


def handle_set_confidentiality(
    uow: UnitOfWork, cmd: SetCorrespondenceConfidentiality
) -> CommandResult:
    """Append ``Correspondence.ConfidentialityChanged`` and the clearance events that go with it.

    Raises ``RecordNotFoundError`` (no such item, or one the viewer may not read),
    ``NoChangesError`` (the class is the one it has), ``ClearanceError`` (``privileged`` without an
    account to name, a name that is not an active person, ``grant`` given for another class).
    """
    cmd = correlated(cmd)
    item = load_item(uow, cmd, cmd.stream_id)
    if cmd.to_class == item.confidentiality:
        raise NoChangesError(f"item {item.number} is already {item.confidentiality}")
    events: list[NewEvent] = [
        NewEvent(
            event_type=CORR_CLASS_CHANGED,
            payload={
                "from_class": item.confidentiality,
                "to_class": cmd.to_class,
                "reason": cmd.reason,
            },
        )
    ]
    if cmd.to_class == "privileged":
        named = sorted({*cmd.grant, cmd.actor})
        if not cmd.grant:
            raise ClearanceError("a privileged item needs the accounts that may read it (grant)")
        if len(named) > MAX_CLEARANCES:
            raise ClearanceError(f"at most {MAX_CLEARANCES} accounts may be named on an item")
        for account in named:
            require_person(uow, account)
        events += granted_events(named, cmd.reason)
    elif cmd.grant:
        raise ClearanceError("only a privileged item names accounts (grant)")
    if item.confidentiality == "privileged":
        events += [
            NewEvent(
                event_type=CORR_CLEARANCE_WITHDRAWN,
                payload={"account": row.account, "reason": "the class changed"},
            )
            for row in registry.clearances_of(uow.conn(), item.id)
        ]
    done = append(
        uow, cmd, item.id, item.record_type, events, expected=cmd.expected_version or item.version
    )
    return CommandResult(
        stream_id=item.id, key=item.number, version=done.new_version, events=list(done.events)
    )


def _privileged_for_control(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """The item of a grant or withdraw, which a controller may run on an item they cannot read.

    Anything that is not a privileged item of the scope (unknown, foreign, or of a class the caller
    may not read: restricted to a plain viewer, a class nobody knows) answers the one
    ``RecordNotFoundError`` an unknown id gets, so the path shows an uncleared controller nothing
    about the item: not its number, not its class. An item the caller may read and that is not
    privileged gets a ``ClearanceError`` that says so.
    """
    item = load_item_for_control(uow, cmd, item_id)
    if item.confidentiality != "privileged":
        if registry.get_item(uow.conn(), item.id) is not None:  # one the caller may read: say so
            raise ClearanceError(f"item {item.number} is {item.confidentiality}, not privileged")
        raise RecordNotFoundError(f"no record {item_id!r}")
    return item


def _result(uow: UnitOfWork, item: registry.ItemRow, done: AppendResult) -> CommandResult:
    """The id and the new version; the number only to someone who may read the item."""
    readable = registry.get_item(uow.conn(), item.id) is not None
    return CommandResult(
        stream_id=item.id,
        key=item.number if readable else None,
        version=done.new_version,
        events=list(done.events),
    )


def handle_grant_clearance(uow: UnitOfWork, cmd: GrantClearance) -> CommandResult:
    """Append ``Correspondence.ClearanceGranted``. ``ClearanceError`` unless the account is an
    active person and not already named; ``RecordNotFoundError`` unless the item is a privileged
    one of the scope (the same answer for every other case, so a controller who cannot read the
    item learns nothing of it)."""
    cmd = correlated(cmd)
    item = _privileged_for_control(uow, cmd, cmd.stream_id)
    require_person(uow, cmd.account)
    named = registry.clearances_of(uow.conn(), item.id, for_control=True)
    if any(row.account == cmd.account for row in named):
        raise ClearanceError(f"{cmd.account} is already named on this item")
    if len(named) >= MAX_CLEARANCES:
        raise ClearanceError(f"at most {MAX_CLEARANCES} accounts may be named on an item")
    done = append(uow, cmd, item.id, item.record_type, granted_events([cmd.account], cmd.reason))
    return _result(uow, item, done)


def handle_withdraw_clearance(uow: UnitOfWork, cmd: WithdrawClearance) -> CommandResult:
    """Append ``Correspondence.ClearanceWithdrawn``. ``ClearanceError`` unless the account is
    named; the last account cannot be withdrawn. ``RecordNotFoundError`` as for a grant."""
    cmd = correlated(cmd)
    item = _privileged_for_control(uow, cmd, cmd.stream_id)
    named = registry.clearances_of(uow.conn(), item.id, for_control=True)
    if all(row.account != cmd.account for row in named):
        raise ClearanceError(f"{cmd.account} is not named on this item")
    if len(named) == 1:
        raise ClearanceError(
            f"{cmd.account} is the last account named on this item; change its class instead"
        )
    done = append(
        uow,
        cmd,
        item.id,
        item.record_type,
        [
            NewEvent(
                event_type=CORR_CLEARANCE_WITHDRAWN,
                payload={"account": cmd.account, "reason": cmd.reason},
            )
        ],
    )
    return _result(uow, item, done)


_RANK = {"internal": 0, "restricted": 1, "privileged": 2}


def _sources_and_target(
    uow: UnitOfWork, item: registry.ItemRow, source_ids: Sequence[str | None]
) -> tuple[list[registry.ItemRow], str]:
    """The readable items ``item`` is matched with, and the highest class of them and ``item``."""
    sources = [
        found
        for found in (
            registry.get_item(uow.conn(), i) for i in dict.fromkeys(i for i in source_ids if i)
        )
        if found is not None and found.id != item.id
    ]
    return sources, max([item.confidentiality, *(s.confidentiality for s in sources)], key=_rank)


def guard_move(uow: UnitOfWork, item: registry.ItemRow, source_ids: Sequence[str | None]) -> None:
    """Refuse to move an EXISTING ``item`` into a thread, or have it answer an item, of a higher
    class unless the actor is a document controller or admin (ADR-0016 section 5: a class change is
    a controller act, and a plain user must not be able to take an item out of its readers' sight
    by filing it in a privileged thread). Nothing is appended. ``ForbiddenError``."""
    _, target = _sources_and_target(uow, item, source_ids)
    if _rank(target) > _rank(item.confidentiality) and confidentiality.current_viewer().level < 1:
        raise ForbiddenError(
            f"item {item.number} is {item.confidentiality}; filing it where the class is "
            f"{target} would raise its class, which needs the document_controller or admin role"
        )


def inherit_from_matches(
    uow: UnitOfWork,
    cmd: Command,
    item: registry.ItemRow,
    source_ids: Sequence[str | None],
    *,
    reason: str = "it answers or joins an item of that class",
) -> list[Event]:
    """Raise ``item`` to the class of the items it was matched with (a reply is never lower).

    A received reply may quote the letter it answers, so it is at least as confidential as the
    item it answers and the thread it joins: ``source_ids`` are those items (the one answered and
    the one that opened the thread). Only the ones the viewer may read are seen here, and a viewer
    who matched them could. A privileged result names the accounts of the privileged sources and
    the person who ran the command, who could not read the item otherwise. Returns the events
    appended (``[]`` when nothing is raised).
    """
    sources, target = _sources_and_target(uow, item, source_ids)
    if _rank(target) <= _rank(item.confidentiality):
        return []
    events: list[NewEvent] = [
        NewEvent(
            event_type=CORR_CLASS_CHANGED,
            payload={
                "from_class": item.confidentiality,
                "to_class": target,
                "reason": reason,
            },
        )
    ]
    if target == "privileged":
        named = {cmd.actor}
        for source in sources:
            if source.confidentiality == "privileged":
                named |= {row.account for row in registry.clearances_of(uow.conn(), source.id)}
        events += granted_events(sorted(named), "inherited from the item it answers")
    return list(append(uow, cmd, item.id, item.record_type, events).events)


def _rank(klass: str) -> int:
    return _RANK.get(klass, 0)


def inherited_class(
    uow: UnitOfWork, parent: registry.ItemRow, author: str
) -> tuple[str, list[str]]:
    """The class and the accounts a reply to ``parent`` starts with: never lower than the parent.

    A reply to a privileged item is privileged and names the accounts of the parent plus its
    author, who could otherwise not read what they just wrote.
    """
    if parent.confidentiality != "privileged":
        return parent.confidentiality, []
    named = {row.account for row in registry.clearances_of(uow.conn(), parent.id)}
    return "privileged", sorted(named | {author})


__all__ = [
    "GrantClearance",
    "SetCorrespondenceConfidentiality",
    "WithdrawClearance",
    "granted_events",
    "handle_grant_clearance",
    "handle_set_confidentiality",
    "handle_withdraw_clearance",
    "guard_move",
    "inherit_from_matches",
    "inherited_class",
    "require_person",
]
