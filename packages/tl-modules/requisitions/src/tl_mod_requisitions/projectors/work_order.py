"""WorkOrderProjector: ``WorkOrder.*`` into ``cur_requisitions_work_order``.

``Opened`` inserts the row; ``Scheduled`` sets the planned dates; ``Assigned`` the assignee;
``Started`` and ``Completed`` set the actual dates (the day of the payload's ``at``, valid time)
and the actual hours; ``Closed`` changes no column (the state is the envelope's)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_requisitions.names import (
    WORK_ORDER_ASSIGNED,
    WORK_ORDER_CLOSED,
    WORK_ORDER_COMPLETED,
    WORK_ORDER_EVENTS,
    WORK_ORDER_OPENED,
    WORK_ORDER_SCHEDULED,
    WORK_ORDER_STARTED,
    WORK_ORDER_TABLE,
    WORK_ORDER_VIEW,
)
from tl_mod_requisitions.projectors._common import ddl_for, touch_record, update_row

_INSERT = text(
    f"INSERT INTO {WORK_ORDER_TABLE} (id, scope, requisition_id, work_kind, hours_planned, "
    "last_seq) VALUES (:id, :scope, :requisition_id, :work_kind, :hours_planned, :last_seq)"
)


def _day(payload: dict[str, Any], event: Event) -> str:
    """The date of the payload's ``at``, else of the time the event was recorded."""
    return str(payload.get("at") or iso_utc(event.recorded_at))[:10]


class WorkOrderProjector:
    name = "requisitions_work_order"
    handles = WORK_ORDER_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(WORK_ORDER_TABLE, dialect) + ddl_for(WORK_ORDER_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == WORK_ORDER_OPENED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "requisition_id": payload["requisition_id"],
                    "work_kind": payload["work_kind"],
                    "hours_planned": payload.get("hours_planned"),
                    "last_seq": event.seq,
                },
            )
        elif kind == WORK_ORDER_SCHEDULED:
            update_row(
                conn,
                WORK_ORDER_TABLE,
                event,
                {
                    "planned_start": payload["planned_start"],
                    "planned_finish": payload.get("planned_finish"),
                    # the schedule command may set the planned hours (the event schema has no slot)
                    **(
                        {"hours_planned": payload["hours_planned"]}
                        if "hours_planned" in payload
                        else {}
                    ),
                },
            )
        elif kind == WORK_ORDER_ASSIGNED:
            update_row(conn, WORK_ORDER_TABLE, event, {"assigned_to": payload["assigned_to"]})
        elif kind == WORK_ORDER_STARTED:
            update_row(conn, WORK_ORDER_TABLE, event, {"actual_start": _day(payload, event)})
        elif kind == WORK_ORDER_COMPLETED:
            update_row(
                conn,
                WORK_ORDER_TABLE,
                event,
                {
                    "actual_finish": _day(payload, event),
                    "hours_actual": payload.get("hours_actual"),
                },
            )
        elif kind == WORK_ORDER_CLOSED:
            update_row(conn, WORK_ORDER_TABLE, event, {})
        else:
            raise ValueError(f"WorkOrderProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {WORK_ORDER_TABLE}"))
