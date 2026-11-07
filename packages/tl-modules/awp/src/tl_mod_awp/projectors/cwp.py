"""Projectors of the package records: CWP, EWPRef, PWPRef.

``CwpProjector`` keeps ``cur_awp_cwp`` (``CWP.Defined`` inserts, ``CWP.Revised`` changes the
columns; the title is the envelope's) and ``cur_awp_cwp_allocation`` (``CWP.AllocatedToWbs``
replaces a package's lines). ``CWP.Released`` changes no column: it only moves the envelope's
version. ``PackageProjector`` keeps the table of one owner package type. Deterministic: the rows
depend only on the events. Register them after ``RecordProjector``.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event
from tl_core.projection.types import Projector

from tl_mod_awp.names import (
    CWP_ALLOCATED,
    CWP_ALLOCATION_TABLE,
    CWP_DEFINED,
    CWP_RELEASED,
    CWP_REVISED,
    CWP_TABLE,
    CWP_VIEW,
    EWP,
    EWP_VIEW,
    PACKAGE_DEFINED,
    PACKAGE_TABLE,
    PACKAGE_UPDATED,
    PWP,
    PWP_VIEW,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {CWP_TABLE} (id, scope, discipline, cwa_id, planned_start, planned_finish, "
    "budget_hours, quantities_json, contractor_text, last_seq) VALUES (:id, :scope, :discipline, "
    ":cwa_id, :planned_start, :planned_finish, :budget_hours, :quantities_json, "
    ":contractor_text, :last_seq)"
)
_ROW_SQL = text(
    "SELECT cwa_id, planned_start, planned_finish, budget_hours, quantities_json, "
    f"contractor_text FROM {CWP_TABLE} WHERE id = :id"
)
_REVISE_SQL = text(
    f"UPDATE {CWP_TABLE} SET cwa_id = :cwa_id, planned_start = :planned_start, "
    "planned_finish = :planned_finish, budget_hours = :budget_hours, "
    "quantities_json = :quantities_json, contractor_text = :contractor_text, "
    "last_seq = :last_seq WHERE id = :id"
)
_CLEAR_SQL = text(f"DELETE FROM {CWP_ALLOCATION_TABLE} WHERE cwp_id = :cwp_id")
_LINE_SQL = text(
    f"INSERT INTO {CWP_ALLOCATION_TABLE} (row_id, scope, cwp_id, wbs_node_id, percent, last_seq) "
    "VALUES (:row_id, :scope, :cwp_id, :wbs_node_id, :percent, :last_seq)"
)
_BUMP_SQL = text(f"UPDATE {CWP_TABLE} SET last_seq = :last_seq WHERE id = :id")
_REVISABLE = ("cwa_id", "planned_start", "planned_finish", "budget_hours", "contractor_text")


def allocation_row_id(cwp_id: str, wbs_node_id: str) -> str:
    """``<cwp id>:<wbs node id>``, the key of an allocation line."""
    return f"{cwp_id}:{wbs_node_id}"


def quantities_text(rows: Any) -> str | None:
    """The stored form of a quantities list (canonical JSON), or ``None``."""
    if rows is None:
        return None
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class CwpProjector:
    name = "awp_cwp"
    handles = frozenset({CWP_DEFINED, CWP_REVISED, CWP_ALLOCATED, CWP_RELEASED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(CWP_TABLE, dialect)
            + ddl_for(CWP_ALLOCATION_TABLE, dialect)
            + ddl_for(CWP_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == CWP_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "discipline": payload["discipline"],
                    "cwa_id": payload.get("cwa_id"),
                    "planned_start": payload.get("planned_start"),
                    "planned_finish": payload.get("planned_finish"),
                    "budget_hours": payload.get("budget_hours"),
                    "quantities_json": quantities_text(payload.get("quantities")),
                    "contractor_text": payload.get("contractor_text"),
                    "last_seq": event.seq,
                },
            )
        elif kind == CWP_REVISED:
            row = conn.execute(_ROW_SQL, {"id": event.stream_id}).first()
            if row is None:
                raise LookupError(f"no {CWP_TABLE} row for stream {event.stream_id}")
            changes: dict[str, list[Any]] = payload["changes"]
            values: dict[str, Any] = {name: getattr(row, name) for name in _REVISABLE}
            for name in _REVISABLE:
                if name in changes:
                    values[name] = changes[name][1]
            quantities = (
                quantities_text(changes["quantities"][1])
                if "quantities" in changes
                else row.quantities_json
            )
            conn.execute(
                _REVISE_SQL,
                {
                    "id": event.stream_id,
                    **values,
                    "quantities_json": quantities,
                    "last_seq": event.seq,
                },
            )
        elif kind == CWP_ALLOCATED:
            conn.execute(_CLEAR_SQL, {"cwp_id": event.stream_id})
            for line in payload["allocations"]:
                conn.execute(
                    _LINE_SQL,
                    {
                        "row_id": allocation_row_id(event.stream_id, line["wbs_node_id"]),
                        "scope": event.scope,
                        "cwp_id": event.stream_id,
                        "wbs_node_id": line["wbs_node_id"],
                        "percent": line["percent"],
                        "last_seq": event.seq,
                    },
                )
            conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        elif kind == CWP_RELEASED:
            conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        else:
            raise ValueError(f"CwpProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CWP_ALLOCATION_TABLE}"))
        conn.execute(text(f"DELETE FROM {CWP_TABLE}"))


_VIEWS = {EWP: EWP_VIEW, PWP: PWP_VIEW}
_NAMES = {EWP: "awp_ewp", PWP: "awp_pwp"}
_UPDATABLE = ("status_text", "forecast_date", "actual_date", "constraint_source")


class PackageProjector:
    """The table of one owner package type (``EWPRef`` or ``PWPRef``): ``Defined`` inserts the
    row, ``Updated`` changes the status words, dates and the flag."""

    def __init__(self, record_type: str) -> None:
        self.record_type = record_type
        self.table = PACKAGE_TABLE[record_type]
        self.name = _NAMES[record_type]
        self._defined = PACKAGE_DEFINED[record_type]
        self._updated = PACKAGE_UPDATED[record_type]
        self.handles = frozenset({self._defined, self._updated})
        self._insert = text(
            f"INSERT INTO {self.table} (id, scope, package_no, status_text, forecast_date, "
            "actual_date, constraint_source, source_system, last_seq) VALUES (:id, :scope, "
            ":package_no, :status_text, :forecast_date, :actual_date, :constraint_source, "
            ":source_system, :last_seq)"
        )
        self._row = text(f"SELECT {', '.join(_UPDATABLE)} FROM {self.table} WHERE id = :id")
        self._update = text(
            f"UPDATE {self.table} SET status_text = :status_text, forecast_date = "
            ":forecast_date, actual_date = :actual_date, constraint_source = :constraint_source, "
            "last_seq = :last_seq WHERE id = :id"
        )

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(self.table, dialect) + ddl_for(_VIEWS[self.record_type], dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == self._defined:
            conn.execute(
                self._insert,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "package_no": payload["package_no"],
                    "status_text": payload.get("status_text"),
                    "forecast_date": payload.get("forecast_date"),
                    "actual_date": payload.get("actual_date"),
                    "constraint_source": bool(payload["constraint_source"]),
                    "source_system": payload.get("source_system"),
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == self._updated:
            row = conn.execute(self._row, {"id": event.stream_id}).first()
            if row is None:
                raise LookupError(f"no {self.table} row for stream {event.stream_id}")
            changes: dict[str, list[Any]] = payload["changes"]
            values: dict[str, Any] = {name: getattr(row, name) for name in _UPDATABLE}
            for name in _UPDATABLE:
                if name in changes:
                    values[name] = changes[name][1]
            values["constraint_source"] = bool(values["constraint_source"])
            conn.execute(self._update, {"id": event.stream_id, **values, "last_seq": event.seq})
        else:
            raise ValueError(f"PackageProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {self.table}"))


def cwp_projectors() -> list[Projector]:
    """Fresh projectors of the package types, in the order they are registered."""
    return [CwpProjector(), PackageProjector(EWP), PackageProjector(PWP)]
