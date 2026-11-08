"""Requisition commands: raise, edit, approve, reject, cancel (P2-I4A S2).

A requisition is one of four record types (``names.KINDS``), numbered per kind. Every state move is
a ``by_module`` workflow transition run in the same unit of work as the module's own event, so the
record and its work order move together (D5). Refusals use fixed messages: an id the viewer may not
read, one in another project and one that does not exist answer alike. Who may act is checked here
after the platform checked the access word: nobody approves their own request; the requester or an
approver edits and cancels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_mod_engineering import codelists
from tl_mod_engineering.errors import UnknownCodeError, UnknownCodeListError

from tl_mod_requisitions.actions import states_for
from tl_mod_requisitions.errors import RequisitionRuleError, RequisitionStateError
from tl_mod_requisitions.guards import require_open
from tl_mod_requisitions.handlers.common import (
    RecordRef,
    append,
    correlated,
    holds_approve,
    load_record_of,
    move,
    record_state,
    require_project,
    require_version,
    silent,
    version_of,
)
from tl_mod_requisitions.names import (
    ACTIVITY_TYPE,
    COST_CODE_TYPE,
    CWP_TYPE,
    FEED_FULL,
    GENERAL,
    GENERAL_TYPE_LIST,
    IWP_TYPE,
    KINDS,
    LABOR,
    LOCATION_TYPE,
    MATERIAL,
    PROJECT_ITEM_TYPE,
    REFERENCES_RELATION,
    REQUIRES_RELATION,
    REQUISITION_APPROVED,
    REQUISITION_CANCELLED,
    REQUISITION_RAISED,
    REQUISITION_REJECTED,
    REQUISITION_REVISED,
    REQUISITION_TYPES,
    RULE_LINK_SOURCE,
    SCAFFOLD,
    ST_APPROVED,
    ST_REQUESTED,
    TABLES,
    WORK_ORDER,
    WORK_ORDER_OPENED,
)
from tl_mod_requisitions.projectors.requisition import BASE_COLUMNS, KIND_COLUMNS

if TYPE_CHECKING:
    from tl_mod_requisitions.commands import (
        ApproveRequisition,
        CancelRequisition,
        EditRequisition,
        RaiseRequisition,
        RejectRequisition,
    )

MSG_SELF = "the requester may not approve their own requisition"
MSG_NOT_PARTY = "only the requester or an approver may do this"
MSG_NO_SUBJECT = "no work package with that id in the project"
MSG_NO_COST_CODE = "no cost code with that id"
MSG_NO_ACTIVITY = "no schedule activity with that id in the project"
MSG_NO_ITEM = "a line names no project item of this project"
MSG_NO_LOCATION = "no inventory location with that id in the project"
MSG_NO_COST_LINE = "a line names no cost code with that id"
MSG_PERIOD = "the end date is before the start date or more than 366 days after it"
MSG_DATE = "a date is not a calendar date"
MSG_TYPE = "the type is not a value of the code list GeneralRequisitionType"
MSG_FIELD = "a field does not belong to this kind of requisition"
MSG_REQUIRED = "a required field cannot be cleared"
MSG_NOTHING = "nothing to change"
MAX_PERIOD_DAYS = 366
_ROW_SQL = "SELECT * FROM {table} WHERE id = :id"
_EDITABLE_BASE = ("subject", "need_by", "location_text", "priority")
_REQUIRED = frozenset(
    {
        "subject",
        "priority",
        "craft",
        "headcount",
        "start_date",
        "end_date",
        "lines",
        "general_type",
        "purpose",
        "duration_days",
    }
)
#: The work kind of the work order a kind of requisition opens (``work_order.yaml``).
_WORK_KIND = {LABOR: "labour", MATERIAL: "issue", GENERAL: "general", SCAFFOLD: "erect"}


@dataclass(frozen=True)
class Requisition:
    """A requisition as the handlers read it: the envelope, the typed row and the state."""

    ref: RecordRef
    state: str
    version: int
    row: dict[str, Any]

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def record_type(self) -> str:
        return self.ref.record_type

    @property
    def key(self) -> str:
        return self.ref.key or ""

    @property
    def requester(self) -> str:
        return str(self.row["requester"])


def load_requisition(uow: UnitOfWork, scope: str, requisition_id: str) -> Requisition:
    """The requisition ``requisition_id``; ``RecordNotFoundError`` (the same words) when it is
    hidden, absent, in another project, voided or not a requisition."""
    ref = load_record_of(uow, scope, requisition_id, REQUISITION_TYPES)
    row = (
        uow.conn()
        .execute(text(_ROW_SQL.format(table=TABLES[ref.record_type])), {"id": ref.id})
        .mappings()
        .first()
    )
    if row is None:
        raise LookupError(f"no row of {ref.record_type} for {ref.id}")
    return Requisition(
        ref=ref,
        state=record_state(uow, ref.id, ST_REQUESTED),
        version=version_of(uow, ref.id),
        row=dict(row),
    )


def require_state(requisition: Requisition, command: str) -> None:
    """The requisition is in a state ``command`` takes (``actions.RULES``)."""
    require_open(requisition.record_type, requisition.state)
    if requisition.state not in states_for(command, requisition.record_type):
        raise RequisitionStateError(
            f"a requisition that is {requisition.state} does not take {command}"
        )


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise RequisitionRuleError(MSG_DATE) from None


def check_period(start: str, end: str) -> None:
    """Both are dates, the end is not before the start and at most 366 days after it."""
    first, last = _day(start), _day(end)
    if last < first or (last - first).days > MAX_PERIOD_DAYS:
        raise RequisitionRuleError(MSG_PERIOD)


def _find(uow: UnitOfWork, scope: str, record_id: str, types: tuple[str, ...], message: str) -> str:
    """The id of a visible record of ``types`` in the project (a company record too, for a cost
    code); the one fixed ``message`` for a hidden, absent, voided or wrong one."""
    try:
        if COST_CODE_TYPE in types:
            return _find_company(uow, scope, record_id)
        return load_record_of(uow, scope, record_id, types).id
    except RecordNotFoundError:
        raise RequisitionRuleError(message) from None


def _find_company(uow: UnitOfWork, scope: str, record_id: str) -> str:
    """A cost code lives in company scope or the project's: try the project, then company."""
    try:
        return load_record_of(uow, scope, record_id, (COST_CODE_TYPE,)).id
    except RecordNotFoundError:
        return load_record_of(uow, "company", record_id, (COST_CODE_TYPE,)).id


def require_general_type(uow: UnitOfWork, scope: str, code: str) -> None:
    try:
        found = codelists.resolve(uow.conn(), scope, GENERAL_TYPE_LIST, code, on=date.today())
    except (UnknownCodeListError, UnknownCodeError):
        raise RequisitionRuleError(MSG_TYPE) from None
    if not found.usable:
        raise RequisitionRuleError(MSG_TYPE)


def check_lines(uow: UnitOfWork, scope: str, lines: list[dict[str, Any]]) -> None:
    """Every line names a project item, and a cost code when it names one."""
    for item in sorted({str(line["item_id"]) for line in lines}):
        _find(uow, scope, item, (PROJECT_ITEM_TYPE,), MSG_NO_ITEM)
    for code in sorted({str(c) for line in lines if (c := line.get("cost_code_id")) is not None}):
        _find(uow, scope, code, (COST_CODE_TYPE,), MSG_NO_COST_LINE)


def check_location(uow: UnitOfWork, scope: str, location_id: str | None) -> None:
    if location_id is not None:
        _find(uow, scope, location_id, (LOCATION_TYPE,), MSG_NO_LOCATION)


def _lines(body_lines: Any) -> list[dict[str, Any]]:
    """The lines as stored: the input and ``fulfilled_qty`` "0"."""
    return [
        {
            "item_id": line.item_id,
            "qty": line.qty,
            "uom": line.uom,
            "cost_code_id": line.cost_code_id,
            "fulfilled_qty": "0",
        }
        for line in body_lines
    ]


def _link(uow: UnitOfWork, cmd: Command, from_id: str, to_id: str, relation: str) -> list[Any]:
    made = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            link_source=RULE_LINK_SOURCE,
        ),
        by_module=True,
    )
    return list(made.events)


def handle_raise_requisition(uow: UnitOfWork, cmd: RaiseRequisition) -> CommandResult:
    """Raise a requisition of the kind the body names: ``Requisition.Raised`` in state Requested,
    numbered per kind, with a ``requires`` link from the IWP or CWP it serves and ``references``
    links to its cost code and activity. The requester is the actor."""
    require_project(cmd)
    cmd = correlated(cmd)
    body = cmd.requisition
    record_type = KINDS[body.kind]
    scope = cmd.scope
    payload: dict[str, Any] = {
        "kind": body.kind,
        "subject": body.subject,
        "requester": cmd.actor,
        "priority": body.priority,
        "need_by": body.need_by,
        "location_text": body.location_text,
        "for_record_id": None,
    }
    if body.need_by is not None:
        _day(body.need_by)
    if body.kind == "labor":
        check_period(body.start_date, body.end_date)
    elif body.kind == "general":
        require_general_type(uow, scope, body.general_type)
    elif body.kind == "material":
        lines = _lines(body.lines)
        check_lines(uow, scope, lines)
        check_location(uow, scope, body.from_location_id)
        payload["lines"] = lines
    payload.update(
        body.model_dump(
            exclude={"kind", "subject", "priority", "need_by", "location_text", "lines"}
        )
    )
    for_id = (
        None
        if cmd.for_record_id is None
        else _find(uow, scope, cmd.for_record_id, (IWP_TYPE, CWP_TYPE), MSG_NO_SUBJECT)
    )
    cost_code = (
        None
        if cmd.cost_code_id is None
        else _find(uow, scope, cmd.cost_code_id, (COST_CODE_TYPE,), MSG_NO_COST_CODE)
    )
    activity = (
        None
        if cmd.activity_id is None
        else _find(uow, scope, cmd.activity_id, (ACTIVITY_TYPE,), MSG_NO_ACTIVITY)
    )
    payload["for_record_id"] = for_id
    made = create_module_record(
        uow,
        cmd,
        record_type=record_type,
        title=body.subject,
        key=None,
        extra_events=[NewEvent(event_type=REQUISITION_RAISED, payload=payload)],
    )
    events = list(made.events)
    if for_id is not None:
        events.extend(_link(uow, cmd, for_id, made.stream_id, REQUIRES_RELATION))
    for target in (cost_code, activity):
        if target is not None:
            events.extend(_link(uow, cmd, made.stream_id, target, REFERENCES_RELATION))
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=events
    )


def _require_party(uow: UnitOfWork, cmd: Command, requisition: Requisition) -> None:
    """The actor is the requester or holds ``requisitions.approve``."""
    if cmd.actor != requisition.requester and not holds_approve(uow, cmd):
        raise ForbiddenError(MSG_NOT_PARTY)


def _current(row: dict[str, Any], field: str) -> Any:
    if field == "lines":
        held = row.get("lines_json")
        return None if held is None else json.loads(held)
    return row.get(field)


def handle_edit_requisition(uow: UnitOfWork, cmd: EditRequisition) -> CommandResult:
    """Change fields of a Requested requisition (the requester or an approver)."""
    require_project(cmd)
    cmd = correlated(cmd)
    requisition = load_requisition(uow, cmd.scope, cmd.requisition)
    require_open(requisition.record_type, requisition.state)
    _require_party(uow, cmd, requisition)
    require_state(requisition, "EditRequisition")
    require_version(uow, requisition.id, cmd.expected_version)
    allowed = {*_EDITABLE_BASE, *KIND_COLUMNS[requisition.record_type]}
    every = {*_EDITABLE_BASE, *(c for cols in KIND_COLUMNS.values() for c in cols)}
    sent = {f for f in cmd.model_fields_set if f in every}
    if not sent <= allowed:
        raise RequisitionRuleError(MSG_FIELD)
    changes: dict[str, list[Any]] = {}
    merged = {f: _current(requisition.row, f) for f in allowed}
    for field in sorted(sent):
        new = getattr(cmd, field)
        if new is None and field in _REQUIRED:
            raise RequisitionRuleError(MSG_REQUIRED)
        if field == "lines":
            new = _lines(new)
        old = merged[field]
        if new != old:
            changes[field] = [old, new]
            merged[field] = new
    if not changes:
        raise RequisitionRuleError(MSG_NOTHING)
    scope = cmd.scope
    if merged.get("need_by") is not None:
        _day(str(merged["need_by"]))
    if requisition.record_type == LABOR:
        check_period(str(merged["start_date"]), str(merged["end_date"]))
    if "general_type" in changes:
        require_general_type(uow, scope, str(merged["general_type"]))
    if "lines" in changes:
        check_lines(uow, scope, merged["lines"])
    if "from_location_id" in changes:
        check_location(uow, scope, merged["from_location_id"])
    done = append(
        uow,
        cmd,
        requisition.id,
        requisition.record_type,
        [NewEvent(event_type=REQUISITION_REVISED, payload=silent({"changes": changes}))],
    )
    return CommandResult(
        stream_id=requisition.id, key=requisition.key, version=done.new_version, events=done.events
    )


def handle_approve_requisition(uow: UnitOfWork, cmd: ApproveRequisition) -> CommandResult:
    """Requested to Approved and the work order (Open) in one unit of work. The requester (the
    actor who raised it) is refused whatever words they hold."""
    require_project(cmd)
    cmd = correlated(cmd)
    requisition = load_requisition(uow, cmd.scope, cmd.requisition)
    require_open(requisition.record_type, requisition.state)
    if cmd.actor == requisition.requester:
        raise ForbiddenError(MSG_SELF)
    require_state(requisition, "ApproveRequisition")
    require_version(uow, requisition.id, cmd.expected_version)
    opened = create_module_record(
        uow,
        cmd,
        record_type=WORK_ORDER,
        title=f"Work order for {requisition.key}",
        key=None,
        extra_events=[
            NewEvent(
                event_type=WORK_ORDER_OPENED,
                payload=silent(
                    {
                        "requisition_id": requisition.id,
                        "work_kind": _work_kind(requisition),
                        "hours_planned": None,
                    }
                ),
            )
        ],
    )
    approved = append(
        uow,
        cmd,
        requisition.id,
        requisition.record_type,
        [
            NewEvent(
                event_type=REQUISITION_APPROVED,
                payload={
                    "approved_by": cmd.actor,
                    "work_order_id": opened.stream_id,
                    "feed_policy": FEED_FULL,
                    "feed_text": f"Requisition {requisition.key} approved",
                },
            )
        ],
    )
    moved = move(uow, cmd, requisition.id, "approve")
    return CommandResult(
        stream_id=requisition.id,
        key=requisition.key,
        version=moved.version,
        events=[*opened.events, *approved.events, *moved.events],
    )


def _work_kind(requisition: Requisition) -> str:
    if requisition.record_type == GENERAL and requisition.row.get("general_type") == "crane_lift":
        return "lift"
    return _WORK_KIND[requisition.record_type]


def handle_reject_requisition(uow: UnitOfWork, cmd: RejectRequisition) -> CommandResult:
    """Requested to Rejected with a reason."""
    require_project(cmd)
    cmd = correlated(cmd)
    requisition = load_requisition(uow, cmd.scope, cmd.requisition)
    require_state(requisition, "RejectRequisition")
    require_version(uow, requisition.id, cmd.expected_version)
    rejected = append(
        uow,
        cmd,
        requisition.id,
        requisition.record_type,
        [
            NewEvent(
                event_type=REQUISITION_REJECTED,
                payload={
                    "by": cmd.actor,
                    "reason": cmd.reason,
                    "feed_policy": FEED_FULL,
                    "feed_text": f"Requisition {requisition.key} rejected",
                },
            )
        ],
    )
    moved = move(uow, cmd, requisition.id, "reject", cmd.reason)
    return CommandResult(
        stream_id=requisition.id,
        key=requisition.key,
        version=moved.version,
        events=[*rejected.events, *moved.events],
    )


def handle_cancel_requisition(uow: UnitOfWork, cmd: CancelRequisition) -> CommandResult:
    """Requested or Approved to Cancelled (the requester or an approver); the Open work order of
    an Approved requisition is cancelled with it."""
    require_project(cmd)
    cmd = correlated(cmd)
    requisition = load_requisition(uow, cmd.scope, cmd.requisition)
    require_open(requisition.record_type, requisition.state)
    _require_party(uow, cmd, requisition)
    require_state(requisition, "CancelRequisition")
    require_version(uow, requisition.id, cmd.expected_version)
    cancelled = append(
        uow,
        cmd,
        requisition.id,
        requisition.record_type,
        [
            NewEvent(
                event_type=REQUISITION_CANCELLED,
                payload={"by": cmd.actor, "reason": cmd.reason},
            )
        ],
    )
    events = [*cancelled.events]
    work_order = requisition.row.get("work_order_id")
    if requisition.state == ST_APPROVED and work_order is not None:
        events.extend(move(uow, cmd, str(work_order), "cancel", cmd.reason).events)
    moved = move(uow, cmd, requisition.id, "cancel", cmd.reason)
    return CommandResult(
        stream_id=requisition.id,
        key=requisition.key,
        version=moved.version,
        events=[*events, *moved.events],
    )


__all__ = [
    "BASE_COLUMNS",
    "Requisition",
    "check_lines",
    "check_period",
    "handle_approve_requisition",
    "handle_cancel_requisition",
    "handle_edit_requisition",
    "handle_raise_requisition",
    "handle_reject_requisition",
    "load_requisition",
    "require_state",
]
