"""RequisitionProjector: ``Requisition.*`` into the table of the requisition's kind.

``Raised`` inserts the row of the kind its payload names (and checks it against the record type of
the stream); ``Revised`` changes the fields it carries; ``Approved`` records who, when and the
work order; ``Rejected`` records the reason; ``Cancelled`` and ``Fulfilled`` change no column here
(the state is the envelope's, and the fulfilled quantities are written with the fulfilment
command, P2-I4A S3)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_requisitions.names import (
    GENERAL_TABLE,
    GENERAL_VIEW,
    KINDS,
    LABOR_TABLE,
    LABOR_VIEW,
    MATERIAL_TABLE,
    MATERIAL_VIEW,
    REQUISITION_APPROVED,
    REQUISITION_CANCELLED,
    REQUISITION_EVENTS,
    REQUISITION_FULFILLED,
    REQUISITION_RAISED,
    REQUISITION_REJECTED,
    REQUISITION_REVISED,
    REQUISITION_TYPES,
    SCAFFOLD_TABLE,
    SCAFFOLD_VIEW,
    TABLES,
)
from tl_mod_requisitions.projectors._common import (
    ddl_for,
    record_type_of,
    touch_record,
    update_row,
)

#: Columns every kind has and a ``Raised`` event carries.
BASE_COLUMNS = (
    "kind",
    "subject",
    "requester",
    "need_by",
    "location_text",
    "priority",
    "for_record_id",
)
#: Columns of each kind beyond the base, in table order. ``lines`` is the column ``lines_json``.
KIND_COLUMNS: dict[str, tuple[str, ...]] = {
    "requisitions.LaborRequisition": (
        "craft",
        "classification",
        "headcount",
        "start_date",
        "end_date",
        "shift",
        "requirements",
    ),
    "requisitions.MaterialRequisition": ("from_location_id", "lines"),
    "requisitions.GeneralRequisition": ("general_type",),
    "requisitions.ScaffoldRequest": (
        "purpose",
        "elevation",
        "gridline",
        "length_m",
        "width_m",
        "height_m",
        "load_class",
        "duration_days",
    ),
}
_INTEGERS = frozenset({"headcount", "duration_days"})


def _column(field: str) -> str:
    return "lines_json" if field == "lines" else field


def _cell(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "lines":
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if field in _INTEGERS:
        return int(value)
    return value


class RequisitionProjector:
    name = "requisitions_requisition"
    handles = REQUISITION_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        tables = (LABOR_TABLE, MATERIAL_TABLE, GENERAL_TABLE, SCAFFOLD_TABLE)
        views = (LABOR_VIEW, MATERIAL_VIEW, GENERAL_VIEW, SCAFFOLD_VIEW)
        return [s for name in (*tables, *views) for s in ddl_for(name, dialect)]

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == REQUISITION_RAISED:
            self._raise(conn, event, payload)
        else:
            table = TABLES[self._record_type(conn, event)]
            if kind == REQUISITION_REVISED:
                self._revise(conn, table, event, payload["changes"])
            elif kind == REQUISITION_APPROVED:
                stamp = payload.get("at") or iso_utc(event.recorded_at)
                update_row(
                    conn,
                    table,
                    event,
                    {
                        "approved_by": payload["approved_by"],
                        "approved_at": stamp,
                        "work_order_id": payload["work_order_id"],
                    },
                )
            elif kind == REQUISITION_REJECTED:
                update_row(conn, table, event, {"reject_reason": payload["reason"]})
            elif kind in (REQUISITION_CANCELLED, REQUISITION_FULFILLED):
                update_row(conn, table, event, {})
            else:
                raise ValueError(f"RequisitionProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    @staticmethod
    def _record_type(conn: Connection, event: Event) -> str:
        found = record_type_of(conn, event)
        if found not in REQUISITION_TYPES:
            raise ValueError(f"stream {event.stream_id} is a {found}, not a requisition")
        return found

    def _raise(self, conn: Connection, event: Event, payload: dict[str, Any]) -> None:
        record_type = self._record_type(conn, event)
        if KINDS.get(payload["kind"]) != record_type:
            raise ValueError(f"kind {payload['kind']!r} does not match record type {record_type}")
        fields = (*BASE_COLUMNS, *KIND_COLUMNS[record_type])
        values: dict[str, Any] = {_column(f): _cell(f, payload.get(f)) for f in fields}
        values.update({"id": event.stream_id, "scope": event.scope, "last_seq": event.seq})
        columns = ", ".join(values)
        marks = ", ".join(f":{c}" for c in values)
        conn.execute(
            text(f"INSERT INTO {TABLES[record_type]} ({columns}) VALUES ({marks})"), values
        )

    @staticmethod
    def _revise(conn: Connection, table: str, event: Event, changes: dict[str, list[Any]]) -> None:
        record_type = record_type_of(conn, event)
        allowed = {f for f in (*BASE_COLUMNS, *KIND_COLUMNS[record_type]) if f != "kind"}
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise ValueError(f"Requisition.Revised changes unknown fields: {', '.join(unknown)}")
        update_row(
            conn, table, event, {_column(f): _cell(f, pair[1]) for f, pair in changes.items()}
        )

    def reset(self, conn: Connection) -> None:
        for table in (LABOR_TABLE, MATERIAL_TABLE, GENERAL_TABLE, SCAFFOLD_TABLE):
            conn.execute(text(f"DELETE FROM {table}"))
