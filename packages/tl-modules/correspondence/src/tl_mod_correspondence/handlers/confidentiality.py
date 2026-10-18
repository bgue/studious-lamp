"""Confidentiality commands: set an item's class, name and unname who may read it (ADR-0016).

A class is ``internal`` (any signed-in person and agent), ``restricted`` (a document controller or
admin; no agent) or ``privileged`` (only the accounts named on the item; nobody else, an admin
included). These commands are a document controller's: **setting a class is the controlled act**,
and a person cannot raise the class of their own item to hide it from review. The commands read the
item through the viewer, so a controller who is not named on a privileged item cannot even see it,
let alone change who may.

Rules that keep a privileged item readable and honest:

* making an item privileged needs at least one account to name, and the person who runs the command
  is always named (they could not read the item otherwise);
* a clearance is granted only to an active person account (an agent never reads a privileged
  item), and the last clearance of a privileged item cannot be withdrawn;
* leaving the privileged class withdraws every clearance, so a later return to it starts empty.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.auth.queries import find_account
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import ClearanceError
from tl_mod_correspondence.handlers.common import append, correlated, load_item, today
from tl_mod_correspondence.limits import MAX_CLEARANCES, MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_CLASS_CHANGED,
    CORR_CLEARANCE_GRANTED,
    CORR_CLEARANCE_WITHDRAWN,
    CORRESPONDENCE,
    LIMITS_NOTE_CLASSES,
)

ItemClass = Literal["internal", "restricted", "privileged"]


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


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
        uow, cmd, item.id, CORRESPONDENCE, events, expected=cmd.expected_version or item.version
    )
    return CommandResult(
        stream_id=item.id, key=item.number, version=done.new_version, events=list(done.events)
    )


def handle_grant_clearance(uow: UnitOfWork, cmd: GrantClearance) -> CommandResult:
    """Append ``Correspondence.ClearanceGranted``. ``ClearanceError`` unless the item is
    privileged, the account an active person, and not already named."""
    cmd = correlated(cmd)
    item = load_item(uow, cmd, cmd.stream_id)
    if item.confidentiality != "privileged":
        raise ClearanceError(f"item {item.number} is {item.confidentiality}, not privileged")
    require_person(uow, cmd.account)
    named = registry.clearances_of(uow.conn(), item.id)
    if any(row.account == cmd.account for row in named):
        raise ClearanceError(f"{cmd.account} is already named on item {item.number}")
    if len(named) >= MAX_CLEARANCES:
        raise ClearanceError(f"at most {MAX_CLEARANCES} accounts may be named on an item")
    done = append(uow, cmd, item.id, CORRESPONDENCE, granted_events([cmd.account], cmd.reason))
    return CommandResult(
        stream_id=item.id, key=item.number, version=done.new_version, events=list(done.events)
    )


def handle_withdraw_clearance(uow: UnitOfWork, cmd: WithdrawClearance) -> CommandResult:
    """Append ``Correspondence.ClearanceWithdrawn``. ``ClearanceError`` unless the item is
    privileged and the account is named; the last account cannot be withdrawn."""
    cmd = correlated(cmd)
    item = load_item(uow, cmd, cmd.stream_id)
    if item.confidentiality != "privileged":
        raise ClearanceError(f"item {item.number} is {item.confidentiality}, not privileged")
    named = registry.clearances_of(uow.conn(), item.id)
    if all(row.account != cmd.account for row in named):
        raise ClearanceError(f"{cmd.account} is not named on item {item.number}")
    if len(named) == 1:
        raise ClearanceError(
            f"{cmd.account} is the last account named on item {item.number}; change its class "
            "instead"
        )
    done = append(
        uow,
        cmd,
        item.id,
        CORRESPONDENCE,
        [
            NewEvent(
                event_type=CORR_CLEARANCE_WITHDRAWN,
                payload={"account": cmd.account, "reason": cmd.reason},
            )
        ],
    )
    return CommandResult(
        stream_id=item.id, key=item.number, version=done.new_version, events=list(done.events)
    )


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
    "inherited_class",
    "require_person",
]
