# ruff: noqa: F401, F841
"""Triage: confirm the domain and subtype of a received item, and reclassify before issue.

A received item is **triaged** when a person confirms which domain it belongs to and what kind of
item it is (``ConfirmTriage``). The suggestion engine (``suggest.py``) proposes; the person decides;
an agent's ``propose_triage`` is a proposal that becomes this command only when a person accepts it.
Confirming does four things in one append: records the domain and subtype, links the item to the
records it refers to, starts the clocks the subtype defines for *receipt*, and moves the item to
Triaged. The clocks that start on *issue* start when a reply is issued (``IssueCorrespondence``).

``ReclassifyCorrespondence`` corrects the domain or subtype of a draft, a received or a triaged
item. After issue a misfiled item gets a linked item in the right domain instead (the issued item
is the record of what was sent).

STUB (P1-I5-T07b2): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core import confidentiality
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.domains import DomainDefinition
from tl_mod_correspondence.errors import InvalidClockError, InvalidItemError
from tl_mod_correspondence.handlers.clocks import start_clock
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    open_item,
    plausible_date,
    require_state,
    today,
    transition,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON, MAX_REFERENCES
from tl_mod_correspondence.names import (
    CORR_RECLASSIFIED,
    CORR_TRIAGED,
    CORR_UPDATED,
    CORRESPONDENCE,
    ST_DRAFT,
    ST_RECEIVED,
    ST_TRIAGED,
)
from tl_mod_correspondence.suggest import suggest

_RECORD_SQL = text("SELECT id, scope FROM cur_core_record WHERE id = :id")


class ConfirmTriage(Command):
    """Confirm the domain and subtype of a received item (an agent may propose it).

    ``referenced_ids`` are records the item refers to (the keys found in its text, confirmed by
    the person); each gets a ``references`` link from the item. ``response_required`` and
    ``response_due`` set what the subtype implies when you leave them out. ``start_clocks=false``
    skips the clocks the subtype starts on receipt (start them by hand later).
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    domain: str = Field(min_length=1, max_length=MAX_NUMBER)
    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    referenced_ids: list[str] = Field(default_factory=list, max_length=MAX_REFERENCES)
    response_required: bool | None = None
    response_due: str | None = Field(default=None, max_length=10)
    start_clocks: bool = True


class ReclassifyCorrespondence(Command):
    """Change the domain and subtype of a draft, received or triaged item. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    domain: str = Field(min_length=1, max_length=MAX_NUMBER)
    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


def _check_references(uow: UnitOfWork, cmd: Command, ids: list[str], own_id: str) -> list[str]:
    """The ids once each is a record of the scope the viewer may read (else ``RecordNotFoundError``,
    the same for an unknown, a foreign and a hidden record)."""
    # STEPS
    # 1. When `len(set(ids)) != len(ids)` raise `InvalidItemError("a record can be referenced
    #    only once")`.
    # 2. For each `record_id` in `ids`: `row = uow.conn().execute(_RECORD_SQL, {"id":
    #    record_id}).first()`. When `row is None`, or `row.scope != cmd.scope`, or
    #    `confidentiality.is_hidden(uow.conn(), record_id)`, raise `RecordNotFoundError(f"no
    #    record {record_id!r}")` (the same text for all three: a hidden record must look like a
    #    missing one). Then, when `record_id == own_id`, raise `InvalidItemError("an item cannot
    #    refer to itself")`.
    # 3. Return `list(ids)`.
    raise NotImplementedError


def _clause_id(
    uow: UnitOfWork, cmd: Command, definition: DomainDefinition, ref: str | None
) -> str | None:
    if ref is None:
        return None
    contract, _, number = ref.partition("/")
    found = registry.find_clause(uow.conn(), cmd.scope, contract, number)
    if found is None or not found.is_active:
        raise InvalidClockError(
            f"domain {definition.code} names clause {ref}, which is not an active clause of "
            f"{cmd.scope}"
        )
    return found.id


def start_template_clocks(
    uow: UnitOfWork,
    cmd: Command,
    item: registry.ItemRow,
    definition: DomainDefinition,
    subtype: str,
    trigger: str,
    start_on: str,
) -> tuple[list[str], list[Event]]:
    """Start the clocks of ``subtype`` whose trigger is ``trigger``; return their ids and events."""
    chosen = definition.subtype(subtype)
    assert chosen is not None  # check_subtype ran
    ids: list[str] = []
    events: list[Event] = []
    for template in chosen.clocks:
        if template.trigger != trigger:
            continue
        made = start_clock(
            uow,
            cmd,
            item=item,
            label=template.label,
            kind=template.kind,
            duration_days=template.duration_days,
            day_type=template.day_type,
            warn_days=template.warn_days,
            start_on=start_on,
            trigger=trigger,
            clause_id=_clause_id(uow, cmd, definition, template.clause),
        )
        ids.append(made.stream_id)
        events.extend(made.events)
    return ids, events


def handle_confirm_triage(uow: UnitOfWork, cmd: ConfirmTriage) -> CommandResult:
    """Record the triage: clocks, ``Correspondence.Triaged``, links, the move to Triaged.

    Raises ``RecordNotFoundError`` (the item or a referenced record is unknown, foreign or hidden),
    ``ItemStateError`` (the item is not Received), ``UnknownDomainError`` (no such domain or
    subtype), ``InvalidItemError`` and ``InvalidClockError`` (a clause the domain names is not
    registered). The suggestion the engine makes for the item is kept in the event when it
    differs from the confirmed domain.
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = open_item(uow, cmd, cmd.stream_id)` (never read the
    #    item any other way: it answers `RecordNotFoundError` for an unknown, foreign or hidden
    #    item); `require_state(item, ST_RECEIVED)`.
    # 2. `definition = catalog.check_subtype(cmd.scope, cmd.domain, cmd.subtype)`; `references =
    #    _check_references(uow, cmd, cmd.referenced_ids, item.id)`; `due =
    #    plausible_date(cmd.response_due, "response_due")` (a `ValueError` becomes
    #    `InvalidItemError(str(exc))`); `chosen = definition.subtype(cmd.subtype)` (assert it is
    #    not None).
    # 3. `proposed = suggest(catalog.domain_set().for_scope(cmd.scope), subject=item.subject,
    #    body=item.body)`.
    # 4. `clock_ids`, `clock_events` start empty. When `cmd.start_clocks`: `clock_ids,
    #    clock_events = start_template_clocks(uow, cmd, item, definition, cmd.subtype,
    #    "receipt", item.received_on or today())` (it creates the clock records and returns
    #    their ids and events).
    # 5. `required = chosen.response_required if cmd.response_required is None else
    #    cmd.response_required`.
    # 6. `events = [NewEvent(event_type=CORR_TRIAGED, payload={"domain": cmd.domain, "subtype":
    #    cmd.subtype, "referenced_ids": references, "clock_ids": clock_ids, "triaged_on":
    #    today(), "suggestion": proposed.domain if proposed.domain != cmd.domain else None})]`.
    # 7. `changes = {}`: when `required != item.response_required` set
    #    `changes["response_required"] = [item.response_required, required]`; when `due is not
    #    None and due != item.response_due` set `changes["response_due"] = [item.response_due,
    #    due]`. When `changes` is not empty append `NewEvent(event_type=CORR_UPDATED,
    #    payload={"changes": changes, "reason": "triage"})`.
    # 8. `done = append(uow, cmd, item.id, CORRESPONDENCE, events, expected=cmd.expected_version
    #    or item.version)`.
    # 9. For each `target` in `references`: `linked = handle_add_link(uow,
    #    AddLink(actor=cmd.actor, source=cmd.source, scope=cmd.scope,
    #    correlation_id=cmd.correlation_id, causation_id=cmd.causation_id, from_id=item.id,
    #    to_id=target, relation="references", link_source="rule", note="confirmed at triage"),
    #    by_module=True)`; collect `linked.events`.
    # 10. `moved = transition(uow, cmd, item.id, "triage")`. Return
    #    `CommandResult(stream_id=item.id, key=item.number, version=moved.version,
    #    events=[*clock_events, *done.events, *link_events, *moved.events])`.
    raise NotImplementedError


def handle_reclassify_correspondence(
    uow: UnitOfWork, cmd: ReclassifyCorrespondence
) -> CommandResult:
    """Append ``Correspondence.Reclassified`` with the old and new domain and subtype.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (not a Draft, Received or Triaged item),
    ``UnknownDomainError`` and ``NoChangesError`` (already that domain and subtype).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `item = open_item(uow, cmd, cmd.stream_id)`;
    #    `require_state(item, ST_DRAFT, ST_RECEIVED, ST_TRIAGED)`.
    # 2. `catalog.check_subtype(cmd.scope, cmd.domain, cmd.subtype)`. When `(item.domain,
    #    item.subtype) == (cmd.domain, cmd.subtype)` raise `NoChangesError(f"item {item.number}
    #    is already {cmd.domain}/{cmd.subtype}")`.
    # 3. `done = append(uow, cmd, item.id, CORRESPONDENCE,
    #    [NewEvent(event_type=CORR_RECLASSIFIED, payload={"from_domain": item.domain,
    #    "from_subtype": item.subtype, "domain": cmd.domain, "subtype": cmd.subtype, "reason":
    #    cmd.reason})], expected=cmd.expected_version or item.version)`; return
    #    `CommandResult(stream_id=item.id, key=item.number, version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError
