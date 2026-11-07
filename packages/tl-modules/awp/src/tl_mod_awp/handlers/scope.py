"""Scope items and the scope of an IWP: create an item, add and remove scope, split a package.

A scope item (``awp.ScopeItem``, numbered ``{project}-SCI-{seq:6}``) or an engineering tag is in the
scope of an IWP when a link from it to the IWP of relation ``belongs_to`` and source ``rule`` is
active (the IWP reads it as ``contains``; the vocabulary holds ``contains`` only as the inverse, so
it cannot be written forward). The module writes and retracts these links (``by_module``); a person
cannot. An item belongs to at most one IWP that is not Closed, Split or Cancelled. The
estimated hours of an IWP follow its scope while they are unset or equal to the sum of the
items' hours; a value a person gave stays. Fixed messages, never a cell of the input.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_awp.common import (
    append,
    correlated,
    load_record_of,
    move,
    record_state,
    require_list_code,
    require_project,
    silent,
)
from tl_mod_awp.errors import IwpRuleError, ScopeRuleError, ScopeTakenError
from tl_mod_awp.facts import MAX_SCOPE_IDS
from tl_mod_awp.handlers.iwp import (
    Iwp,
    IwpFields,
    create_iwp,
    load_iwp,
    pin_document,
    require_cwp,
    require_state,
    size_bounds,
    size_warnings,
    with_warnings,
)
from tl_mod_awp.limits import MAX_SPLIT_GROUPS, MAX_TITLE
from tl_mod_awp.names import (
    DOCUMENT_TYPE,
    IWP,
    IWP_REVISED,
    IWP_SCOPE_ADDED,
    IWP_SCOPE_REMOVED,
    IWP_SPLIT,
    IWP_TERMINAL,
    PIN_RELATION,
    RULE_LINK_SOURCE,
    SCI_PLANNED,
    SCI_VERIFIED,
    SCI_VOID,
    SCOPE_ITEM,
    SCOPE_ITEM_CREATED,
    SCOPE_RELATION,
    TAG_TYPE,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import AddIwpScope, CreateScopeItem, RemoveIwpScope, SplitIwp

COMMODITY_LIST = "Commodity"
UNIT_LIST = "UnitOfMeasure"
MSG_REPEAT = "a record is already in the scope of this package"
MSG_NOT_MEMBER = "a record of the list is not in the scope of this package"
MSG_TOO_MANY = "a package holds at most 5000 scope records"
MSG_UNUSABLE = "a verified or void scope item cannot be added to a package"
MSG_TAKEN = "the item already belongs to another package"
MSG_BOUND = "the estimated hours would be above 10000000.0"
MSG_NO_SCOPE = "a package with no scope cannot be split"
MSG_GROUPS = "the groups must be non-empty and together hold exactly the scope"
MSG_ONE_GROUP = "the split gives fewer than two packages"
MSG_MANY_GROUPS = "the split gives more than 50 packages"
MSG_CWP_UNKNOWN = "no work package with that id in the project"
SCOPE_REASON = "removed from the scope of the package"
MOVE_REASON = "moved to a package made by a split"
MAX_HOURS = Decimal("10000000.0")
ONE_DP = Decimal("0.1")

_MEMBERS_SQL = text(
    "SELECT l.link_id, l.from_id AS item_id, r.type AS record_type, r.key AS key, "
    "s.est_hours AS est_hours FROM cur_links l JOIN cur_core_record r ON r.id = l.from_id "
    "LEFT JOIN cur_awp_scope_item s ON s.id = l.from_id "
    "WHERE l.to_id = :iwp AND l.relation = :relation AND l.source = :source "
    "AND l.status = 'active' AND r.type IN (:item_type, :tag_type) ORDER BY r.key, l.from_id"
)
_OWNER_SQL = text(
    "SELECT r.id, r.key, r.status FROM cur_links l JOIN cur_core_record r ON r.id = l.to_id "
    "WHERE l.from_id = :item AND l.relation = :relation AND l.source = :source "
    "AND l.status = 'active' AND r.type = :iwp_type AND r.id <> :iwp ORDER BY r.key"
)
_ITEM_HOURS_SQL = text("SELECT est_hours FROM cur_awp_scope_item WHERE id = :id")
_PINS_SQL = text(
    "SELECT l.to_id, l.pin FROM cur_links l JOIN cur_core_record d ON d.id = l.to_id "
    "WHERE l.from_id = :iwp AND l.relation = :relation AND l.status = 'active' "
    "AND d.type = :document_type ORDER BY l.created_at, l.link_id"
)


@dataclass(frozen=True)
class Member:
    """One record in the scope of an IWP: the link that holds it and its hours (tags have none)."""

    link_id: str
    item_id: str
    record_type: str
    key: str
    hours: Decimal | None


def members_of(conn: Connection, iwp_id: str) -> list[Member]:
    """The scope of an IWP in key order."""
    rows = conn.execute(
        _MEMBERS_SQL,
        {
            "iwp": iwp_id,
            "relation": SCOPE_RELATION,
            "source": RULE_LINK_SOURCE,
            "item_type": SCOPE_ITEM,
            "tag_type": TAG_TYPE,
        },
    ).all()
    return [
        Member(
            str(r.link_id),
            str(r.item_id),
            str(r.record_type),
            str(r.key or ""),
            None if r.est_hours is None else Decimal(str(r.est_hours)),
        )
        for r in rows
    ]


def hours_sum(rows: list[Member]) -> Decimal:
    return sum((m.hours for m in rows if m.hours is not None), Decimal("0.0"))


def _hours_text(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.quantize(ONE_DP):.1f}"


def _derived(rows: list[Member]) -> str | None:
    """The hours the scope gives: ``None`` while no scope item has hours."""
    if not any(m.hours is not None for m in rows):
        return None
    return _hours_text(hours_sum(rows))


def _is_derived(iwp: Iwp, rows: list[Member]) -> bool:
    """The IWP's hours are unset or equal the sum of its scope (so they follow the scope)."""
    return iwp.estimated_hours is None or Decimal(iwp.estimated_hours) == (
        hours_sum(rows).quantize(ONE_DP)
    )


def _rehours(
    iwp: Iwp, before: list[Member], after: list[Member]
) -> tuple[str | None, list[NewEvent]]:
    """The IWP's hours after the change and the ``IWP.Revised`` event when they move."""
    current = iwp.estimated_hours
    if not _is_derived(iwp, before):
        return current, []
    new = _derived(after)
    if new is not None and Decimal(new) > MAX_HOURS:
        raise IwpRuleError(MSG_BOUND)
    if new == current:
        return current, []
    event = NewEvent(
        event_type=IWP_REVISED, payload={"changes": {"estimated_hours": [current, new]}}
    )
    return new, [event]


def handle_create_scope_item(uow: UnitOfWork, cmd: CreateScopeItem) -> CommandResult:
    """Create a scope item: ``Numbering.Allocated``, ``Record.Created``, ``ScopeItem.Created`` (no
    card). Raises ``UnknownListCodeError`` (commodity, unit), ``IwpRuleError`` (work package)."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    require_list_code(conn, cmd.scope, COMMODITY_LIST, cmd.commodity, "the commodity")
    require_list_code(conn, cmd.scope, UNIT_LIST, cmd.uom, "the unit of measure")
    require_cwp(uow, cmd.scope, cmd.cwp_id)
    made = create_module_record(
        uow,
        cmd,
        record_type=SCOPE_ITEM,
        title=cmd.description,
        key=None,
        description=None,
        extra_events=[
            NewEvent(
                event_type=SCOPE_ITEM_CREATED,
                payload=silent(
                    {
                        "commodity": cmd.commodity,
                        "description": cmd.description,
                        "qty": cmd.qty,
                        "uom": cmd.uom,
                        "est_hours": cmd.est_hours,
                        "cwp_id": cmd.cwp_id,
                    }
                ),
            )
        ],
    )
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=made.events
    )


def _check_item(conn: Connection, iwp: Iwp, item_id: str, record_type: str) -> None:
    """A scope item is usable and free: not Verified or Void, in no other live IWP."""
    if record_type != SCOPE_ITEM:
        return
    if record_state(conn, item_id, SCI_PLANNED) in (SCI_VERIFIED, SCI_VOID):
        raise ScopeRuleError(MSG_UNUSABLE)
    for owner in conn.execute(
        _OWNER_SQL,
        {
            "item": item_id,
            "relation": SCOPE_RELATION,
            "source": RULE_LINK_SOURCE,
            "iwp_type": IWP,
            "iwp": iwp.id,
        },
    ):
        if (owner.status or "Draft") in IWP_TERMINAL:
            continue
        if confidentiality.is_hidden(conn, str(owner.id)):
            raise ScopeTakenError(MSG_TAKEN)
        raise ScopeTakenError(f"the item already belongs to package {owner.key}")


def _link(uow: UnitOfWork, cmd: Command, from_id: str, to_id: str) -> list[Any]:
    added = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=from_id,
            to_id=to_id,
            relation=SCOPE_RELATION,
            link_source=RULE_LINK_SOURCE,
        ),
        by_module=True,
    )
    return list(added.events)


def _unlink(uow: UnitOfWork, cmd: Command, link_id: str, reason: str) -> list[Any]:
    gone = handle_retract_link(
        uow,
        RetractLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            link_id=link_id,
            reason=reason,
        ),
        by_module=True,
    )
    return list(gone.events)


def _scope_event(kind: str, item_id: str, record_type: str) -> NewEvent:
    return NewEvent(
        event_type=kind, payload=silent({"record_id": item_id, "record_type": record_type})
    )


def handle_add_iwp_scope(uow: UnitOfWork, cmd: AddIwpScope) -> CommandResult:
    """Add scope items or tags to an IWP: ``IWP.ScopeAdded`` each, ``IWP.Revised`` when the derived
    hours move, ``Link.Added`` each. Raises ``IwpStateError``, ``ScopeRuleError`` (a repeat, a
    verified or void item, the bound), ``ScopeTakenError`` (an item of another live package),
    ``IwpRuleError`` (hours above the bound). The sizing warning rides on the last IWP event."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, "AddIwpScope")
    before = members_of(conn, iwp.id)
    if len(before) + len(cmd.items) > MAX_SCOPE_IDS:
        raise ScopeRuleError(MSG_TOO_MANY)
    held = {m.item_id for m in before}
    added: list[Member] = []
    for item_id in cmd.items:
        ref = load_record_of(uow, cmd.scope, item_id, (SCOPE_ITEM, TAG_TYPE))
        if ref.id in held:
            raise ScopeRuleError(MSG_REPEAT)
        _check_item(conn, iwp, ref.id, ref.record_type)
        raw = conn.execute(_ITEM_HOURS_SQL, {"id": ref.id}).scalar_one_or_none()
        hours = None if raw is None else Decimal(str(raw))
        added.append(Member("", ref.id, ref.record_type, ref.key or "", hours))
    after = [*before, *added]
    hours_now, revised = _rehours(iwp, before, after)
    events = [_scope_event(IWP_SCOPE_ADDED, m.item_id, m.record_type) for m in added]
    events.extend(revised)
    with_warnings(events, size_warnings(conn, cmd.scope, hours_now))
    made = append(uow, cmd, iwp.id, IWP, events)
    result = list(made.events)
    for m in added:
        result.extend(_link(uow, cmd, m.item_id, iwp.id))
    return CommandResult(stream_id=iwp.id, key=iwp.key, version=made.new_version, events=result)


def handle_remove_iwp_scope(uow: UnitOfWork, cmd: RemoveIwpScope) -> CommandResult:
    """Remove records from the scope of an IWP: ``IWP.ScopeRemoved`` each, ``IWP.Revised`` when the
    derived hours move, ``Link.Retracted`` each. Raises ``IwpStateError``, ``ScopeRuleError`` (a
    record that is not in the scope)."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, "RemoveIwpScope")
    before = members_of(conn, iwp.id)
    by_id = {m.item_id: m for m in before}
    gone: list[Member] = []
    for item_id in cmd.items:
        confidentiality.require_visible(conn, item_id)
        if item_id not in by_id:
            raise ScopeRuleError(MSG_NOT_MEMBER)
        gone.append(by_id[item_id])
    drop = {m.item_id for m in gone}
    after = [m for m in before if m.item_id not in drop]
    hours_now, revised = _rehours(iwp, before, after)
    events = [_scope_event(IWP_SCOPE_REMOVED, m.item_id, m.record_type) for m in gone]
    events.extend(revised)
    with_warnings(events, size_warnings(conn, cmd.scope, hours_now))
    made = append(uow, cmd, iwp.id, IWP, events)
    result = list(made.events)
    for m in gone:
        result.extend(_unlink(uow, cmd, m.link_id, SCOPE_REASON))
    return CommandResult(stream_id=iwp.id, key=iwp.key, version=made.new_version, events=result)


def split_by_hours(rows: list[Member], high: Decimal) -> list[list[Member]]:
    """The records in key order cut into the fewest consecutive groups each at most ``high``
    hours (a single record above ``high`` is a group of its own)."""
    groups: list[list[Member]] = []
    current: list[Member] = []
    total = Decimal("0.0")
    for member in rows:
        hours = member.hours or Decimal("0.0")
        if current and total + hours > high:
            groups.append(current)
            current, total = [], Decimal("0.0")
        current.append(member)
        total += hours
    if current:
        groups.append(current)
    return groups


def split_by_scope(rows: list[Member], groups: list[list[str]]) -> list[list[Member]]:
    """The given groups: each non-empty, together exactly the scope, no record twice."""
    by_id = {m.item_id: m for m in rows}
    flat = [item for group in groups for item in group]
    if any(not group for group in groups) or len(flat) != len(set(flat)) or set(flat) != set(by_id):
        raise ScopeRuleError(MSG_GROUPS)
    return [sorted((by_id[i] for i in group), key=lambda m: (m.key, m.item_id)) for group in groups]


def _title(source: str, number: int, count: int) -> str:
    suffix = f" ({number}/{count})"
    return source[: MAX_TITLE - len(suffix)] + suffix


def handle_split_iwp(uow: UnitOfWork, cmd: SplitIwp) -> CommandResult:
    """Split an IWP into two or more of the same discipline, each taking a group of the scope.

    The new packages copy the foreman, the work package, the planned dates, the crew text and the
    pins; the ``belongs_to`` scope links move to them; the open constraints of the source are
    voided with the reason ``split``; the source gets ``IWP.Split`` {new_ids} and goes to Split.
    Raises ``IwpStateError``, ``ScopeRuleError`` (no scope, bad groups, fewer than two or more
    than 50 packages)."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, "SplitIwp")
    rows = members_of(conn, iwp.id)
    if not rows:
        raise ScopeRuleError(MSG_NO_SCOPE)
    if cmd.mode == "by_hours":
        groups = split_by_hours(rows, size_bounds(conn, cmd.scope)[1])
    else:
        groups = split_by_scope(rows, cmd.groups or [])
    if len(groups) < 2:
        raise ScopeRuleError(MSG_ONE_GROUP)
    if len(groups) > MAX_SPLIT_GROUPS:
        raise ScopeRuleError(MSG_MANY_GROUPS)
    pins = [
        (str(r.to_id), None if r.pin is None else str(r.pin))
        for r in conn.execute(
            _PINS_SQL, {"iwp": iwp.id, "relation": PIN_RELATION, "document_type": DOCUMENT_TYPE}
        )
    ]
    events: list[Any] = []
    new_ids: list[str] = []
    for number, group in enumerate(groups, start=1):
        made = create_iwp(
            uow,
            cmd,
            IwpFields(
                discipline=iwp.discipline,
                title=_title(iwp.title, number, len(groups)),
                cwp_id=iwp.cwp_id,
                planned_start=iwp.planned_start,
                planned_finish=iwp.planned_finish,
                foreman=iwp.foreman,
                estimated_hours=_derived(group),
                crew_text=iwp.crew_text,
            ),
        )
        events.extend(made.events)
        new_ids.append(made.stream_id)
        for member in group:
            events.extend(_unlink(uow, cmd, member.link_id, MOVE_REASON))
            events.extend(_link(uow, cmd, member.item_id, made.stream_id))
        for document_id, pin in pins:
            if not confidentiality.is_hidden(conn, document_id):
                events.extend(pin_document(uow, cmd, made.stream_id, document_id, pin))
    split = append(
        uow, cmd, iwp.id, IWP, [NewEvent(event_type=IWP_SPLIT, payload={"new_ids": new_ids})]
    )
    events.extend(split.events)
    moved = move(uow, cmd, iwp.id, "split", cmd.reason)
    events.extend(moved.events)
    return CommandResult(stream_id=iwp.id, key=iwp.key, version=moved.version, events=events)


__all__ = [
    "Member",
    "handle_add_iwp_scope",
    "handle_create_scope_item",
    "handle_remove_iwp_scope",
    "handle_split_iwp",
    "hours_sum",
    "members_of",
    "split_by_hours",
    "split_by_scope",
]
