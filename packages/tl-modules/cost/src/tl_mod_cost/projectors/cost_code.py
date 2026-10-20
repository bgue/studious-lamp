"""CostCodeProjector: the ``CostCode.*`` events into ``cur_cost_costcode`` and the value history.

``CostCode.Defined`` inserts the code; ``Revised`` changes its parent, level and unit of measure
(the title is the envelope's, moved by ``Record.Updated``); ``MeasuresRecorded`` adds the code's row
to ``cur_cost_snapshot_value`` and, when the snapshot is as of the same day as the matrix or later,
replaces the matrix. A snapshot imported late (an earlier ``as_of``) therefore adds history and
leaves the matrix of the later one alone. Deterministic: the rows depend only on the events of the
stream. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_cost.names import (
    CODE_DEFINED,
    CODE_REVISED,
    COST_CODE_TABLE,
    COST_CODE_VIEW,
    MEASURE_COLUMNS,
    MEASURES_RECORDED,
    SNAPSHOT_VALUE_TABLE,
)
from tl_mod_cost.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {COST_CODE_TABLE} (id, scope, code, parent_code, level, uom, is_active, "
    "last_seq) VALUES (:id, :scope, :code, :parent_code, :level, :uom, :is_active, :last_seq)"
)
_REVISE_SQL = text(
    f"UPDATE {COST_CODE_TABLE} SET parent_code = :parent_code, level = :level, uom = :uom, "
    "last_seq = :last_seq WHERE id = :id"
)
_ROW_SQL = text(
    f"SELECT code, parent_code, level, uom, as_of FROM {COST_CODE_TABLE} WHERE id = :id"
)
_VALUE_COLUMNS = ", ".join(MEASURE_COLUMNS)
_VALUE_PARAMS = ", ".join(f":{c}" for c in MEASURE_COLUMNS)
_VALUE_SQL = text(
    f"INSERT INTO {SNAPSHOT_VALUE_TABLE} (row_id, scope, snapshot_id, cost_code_id, code, period, "
    f"revision, as_of, {_VALUE_COLUMNS}, last_seq) VALUES (:row_id, :scope, :snapshot_id, "
    f":cost_code_id, :code, :period, :revision, :as_of, {_VALUE_PARAMS}, :last_seq)"
)
_MATRIX_SET = ", ".join(f"{c} = :{c}" for c in MEASURE_COLUMNS)
_MATRIX_SQL = text(
    f"UPDATE {COST_CODE_TABLE} SET snapshot_id = :snapshot_id, period = :period, as_of = :as_of, "
    f"{_MATRIX_SET}, last_seq = :last_seq WHERE id = :id"
)
_BUMP_SQL = text(f"UPDATE {COST_CODE_TABLE} SET last_seq = :last_seq WHERE id = :id")


def value_row_id(snapshot_id: str, cost_code_id: str) -> str:
    """``<snapshot id>:<cost code id>``, the key of a history row."""
    return f"{snapshot_id}:{cost_code_id}"


def _figure(measures: dict[str, Any], column: str) -> float | None:
    value = measures.get(column)
    return None if value is None else float(value)


class CostCodeProjector:
    name = "cost_cost_code"
    handles = frozenset({CODE_DEFINED, CODE_REVISED, MEASURES_RECORDED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(COST_CODE_TABLE, dialect)
            + ddl_for(SNAPSHOT_VALUE_TABLE, dialect)
            + ddl_for(COST_CODE_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == CODE_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "parent_code": payload.get("parent_code"),
                    "level": int(payload["level"]),
                    "uom": payload.get("uom"),
                    "is_active": True,
                    "last_seq": event.seq,
                },
            )
        elif kind == CODE_REVISED:
            row = conn.execute(_ROW_SQL, {"id": event.stream_id}).first()
            if row is None:
                raise LookupError(f"no {COST_CODE_TABLE} row for stream {event.stream_id}")
            changes: dict[str, list[Any]] = payload["changes"]
            conn.execute(
                _REVISE_SQL,
                {
                    "id": event.stream_id,
                    "parent_code": changes["parent_code"][1]
                    if "parent_code" in changes
                    else row.parent_code,
                    "level": int(changes["level"][1]) if "level" in changes else row.level,
                    "uom": changes["uom"][1] if "uom" in changes else row.uom,
                    "last_seq": event.seq,
                },
            )
        elif kind == MEASURES_RECORDED:
            row = conn.execute(_ROW_SQL, {"id": event.stream_id}).first()
            if row is None:
                raise LookupError(f"no {COST_CODE_TABLE} row for stream {event.stream_id}")
            measures: dict[str, Any] = payload["measures"]
            figures = {c: _figure(measures, c) for c in MEASURE_COLUMNS}
            conn.execute(
                _VALUE_SQL,
                {
                    "row_id": value_row_id(payload["snapshot_id"], event.stream_id),
                    "scope": event.scope,
                    "snapshot_id": payload["snapshot_id"],
                    "cost_code_id": event.stream_id,
                    "code": row.code,
                    "period": payload["period"],
                    "revision": int(payload["revision"]),
                    "as_of": payload["as_of"],
                    "last_seq": event.seq,
                    **figures,
                },
            )
            if row.as_of is None or payload["as_of"] >= row.as_of:
                conn.execute(
                    _MATRIX_SQL,
                    {
                        "id": event.stream_id,
                        "snapshot_id": payload["snapshot_id"],
                        "period": payload["period"],
                        "as_of": payload["as_of"],
                        "last_seq": event.seq,
                        **figures,
                    },
                )
            else:
                conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        else:
            raise ValueError(f"CostCodeProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {SNAPSHOT_VALUE_TABLE}"))
        conn.execute(text(f"DELETE FROM {COST_CODE_TABLE}"))
