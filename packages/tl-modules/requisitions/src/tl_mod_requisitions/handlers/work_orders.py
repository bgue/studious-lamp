"""Work order commands: schedule, assign, start, complete, close (P2-I4A S2).

A work order has its own stream; the requisition it carries out moves with it (D5): in one unit of
work the work order takes its ``by_module`` transition (the guard ``no_open_blocking_constraints``
of phase ``start`` runs there), its own event is appended, and the requisition takes the transition
of the same name. Dates the person gives for work that happened (``at``) are valid time (ADR-0026):
never in the future.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_requisitions.actions import states_for
from tl_mod_requisitions.errors import RequisitionRuleError, RequisitionStateError
from tl_mod_requisitions.guards import require_open
from tl_mod_requisitions.handlers.common import (
    RecordRef,
    append,
    correlated,
    load_record_of,
    move,
    record_state,
    require_project,
    require_version,
    silent,
    version_of,
)
from tl_mod_requisitions.handlers.requisitions import _day
from tl_mod_requisitions.names import (
    FEED_FULL,
    ST_OPEN,
    WORK_ORDER,
    WORK_ORDER_ASSIGNED,
    WORK_ORDER_CLOSED,
    WORK_ORDER_COMPLETED,
    WORK_ORDER_SCHEDULED,
    WORK_ORDER_STARTED,
    WORK_ORDER_TABLE,
)

if TYPE_CHECKING:
    from tl_mod_requisitions.commands import (
        AssignWorkOrder,
        CloseWorkOrder,
        CompleteWorkOrder,
        ScheduleWorkOrder,
        StartWorkOrder,
    )

MSG_PLAN = "the planned finish is before the planned start"
MSG_FUTURE = "the time is in the future"
MSG_BEFORE_START = "the work cannot finish before it started"
_ROW_SQL = text(f"SELECT requisition_id, actual_start FROM {WORK_ORDER_TABLE} WHERE id = :id")


@dataclass(frozen=True)
class WorkOrder:
    ref: RecordRef
    state: str
    requisition_id: str
    actual_start: str | None

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def key(self) -> str:
        return self.ref.key or ""


def load_work_order(uow: UnitOfWork, scope: str, work_order_id: str) -> WorkOrder:
    """The work order; ``RecordNotFoundError`` (the same words) when it is hidden, absent, in
    another project, voided or not a work order."""
    ref = load_record_of(uow, scope, work_order_id, (WORK_ORDER,))
    row = uow.conn().execute(_ROW_SQL, {"id": ref.id}).first()
    if row is None:
        raise LookupError(f"no work order row for {ref.id}")
    return WorkOrder(
        ref=ref,
        state=record_state(uow, ref.id, ST_OPEN),
        requisition_id=str(row.requisition_id),
        actual_start=None if row.actual_start is None else str(row.actual_start),
    )


def _require_state(work_order: WorkOrder, command: str) -> None:
    require_open(WORK_ORDER, work_order.state)
    if work_order.state not in states_for(command, WORK_ORDER):
        raise RequisitionStateError(
            f"a work order that is {work_order.state} does not take {command}"
        )


def _valid_time(at: datetime | None) -> str:
    """``at`` as the event carries it, now when not given; never in the future."""
    now = utcnow()
    moment = now if at is None else at
    if moment > now:
        raise RequisitionRuleError(MSG_FUTURE)
    return iso_utc(moment)


def _step(
    uow: UnitOfWork,
    cmd: Any,
    command: str,
    transition: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    with_requisition: bool,
) -> CommandResult:
    """The work order takes ``transition``, writes ``event_type``; the requisition takes the same
    transition when ``with_requisition``."""
    work_order = load_work_order(uow, cmd.scope, cmd.work_order)
    _require_state(work_order, command)
    require_version(uow, work_order.id, cmd.expected_version)
    return _run(uow, cmd, work_order, transition, event_type, payload, with_requisition)


def _run(
    uow: UnitOfWork,
    cmd: Command,
    work_order: WorkOrder,
    transition: str,
    event_type: str,
    payload: dict[str, Any],
    with_requisition: bool,
) -> CommandResult:
    moved = move(uow, cmd, work_order.id, transition)  # the guards run here, before any write
    written = append(
        uow,
        cmd,
        work_order.id,
        WORK_ORDER,
        [NewEvent(event_type=event_type, payload={"requisition_id": work_order.requisition_id, **payload})],
    )
    events = [*moved.events, *written.events]
    if with_requisition:
        events.extend(move(uow, cmd, work_order.requisition_id, transition).events)
    return CommandResult(
        stream_id=work_order.id,
        key=work_order.key,
        version=version_of(uow, work_order.id),
        events=events,
    )


def handle_schedule_work_order(uow: UnitOfWork, cmd: ScheduleWorkOrder) -> CommandResult:
    """Open to Scheduled with planned dates (finish not before start) and optional planned hours;
    the requisition becomes Scheduled."""
    require_project(cmd)
    cmd = correlated(cmd)
    if _day(cmd.planned_finish) < _day(cmd.planned_start):
        raise RequisitionRuleError(MSG_PLAN)
    payload: dict[str, Any] = {
        "planned_start": cmd.planned_start,
        "planned_finish": cmd.planned_finish,
    }
    if cmd.hours_planned is not None:
        payload["hours_planned"] = cmd.hours_planned
    return _step(
        uow, cmd, "ScheduleWorkOrder", "schedule", WORK_ORDER_SCHEDULED, payload, with_requisition=True
    )


def handle_assign_work_order(uow: UnitOfWork, cmd: AssignWorkOrder) -> CommandResult:
    """Set ``assigned_to`` while the work order is Open or Scheduled (no state moves)."""
    require_project(cmd)
    cmd = correlated(cmd)
    work_order = load_work_order(uow, cmd.scope, cmd.work_order)
    _require_state(work_order, "AssignWorkOrder")
    require_version(uow, work_order.id, cmd.expected_version)
    written = append(
        uow,
        cmd,
        work_order.id,
        WORK_ORDER,
        [
            NewEvent(
                event_type=WORK_ORDER_ASSIGNED,
                payload=silent(
                    {"requisition_id": work_order.requisition_id, "assigned_to": cmd.assigned_to}
                ),
            )
        ],
    )
    return CommandResult(
        stream_id=work_order.id,
        key=work_order.key,
        version=written.new_version,
        events=written.events,
    )


def handle_start_work_order(uow: UnitOfWork, cmd: StartWorkOrder) -> CommandResult:
    """Scheduled to In progress; ``at`` (not in the future) else now is the start. Refused while an
    open blocking constraint of phase ``start`` sits on the work order."""
    require_project(cmd)
    cmd = correlated(cmd)
    return _step(
        uow,
        cmd,
        "StartWorkOrder",
        "start",
        WORK_ORDER_STARTED,
        {"at": _valid_time(cmd.at)},
        with_requisition=True,
    )


def handle_complete_work_order(uow: UnitOfWork, cmd: CompleteWorkOrder) -> CommandResult:
    """In progress to Done; ``at`` (not in the future, not before the start) else now is the
    finish, and the actual hours when given."""
    require_project(cmd)
    cmd = correlated(cmd)
    work_order = load_work_order(uow, cmd.scope, cmd.work_order)
    _require_state(work_order, "CompleteWorkOrder")
    require_version(uow, work_order.id, cmd.expected_version)
    finished = _valid_time(cmd.at)
    if work_order.actual_start is not None and finished[:10] < work_order.actual_start:
        raise RequisitionRuleError(MSG_BEFORE_START)
    key = work_order.key
    return _run(
        uow,
        cmd,
        work_order,
        "complete",
        WORK_ORDER_COMPLETED,
        {
            "at": finished,
            "hours_actual": cmd.hours_actual,
            "feed_policy": FEED_FULL,
            "feed_text": f"Work order {key} completed",
        },
        True,
    )


def handle_close_work_order(uow: UnitOfWork, cmd: CloseWorkOrder) -> CommandResult:
    """Done to Closed; the requisition closes with it."""
    require_project(cmd)
    cmd = correlated(cmd)
    return _step(uow, cmd, "CloseWorkOrder", "close", WORK_ORDER_CLOSED, {}, with_requisition=True)


__all__ = [
    "WorkOrder",
    "handle_assign_work_order",
    "handle_close_work_order",
    "handle_complete_work_order",
    "handle_schedule_work_order",
    "handle_start_work_order",
    "load_work_order",
]
