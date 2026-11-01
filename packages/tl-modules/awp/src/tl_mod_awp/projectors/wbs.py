"""WbsProjector: the ``WBSNode.*`` events into ``cur_awp_wbs_node`` and ``cur_awp_wbs_allocation``.

``Defined`` inserts the node; ``Revised`` changes its parent, depth and position (the title is the
envelope's, moved by ``Record.Updated``, and is ignored here); ``Retired`` sets the flag;
``CostCodesMapped`` replaces the node's allocation lines. Deterministic: the rows depend only on
the events. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_awp.names import (
    WBS_ALLOCATION_TABLE,
    WBS_COST_CODES_MAPPED,
    WBS_DEFINED,
    WBS_NODE_TABLE,
    WBS_NODE_VIEW,
    WBS_RETIRED,
    WBS_REVISED,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {WBS_NODE_TABLE} (id, scope, code, parent_id, depth, position, retired, "
    "last_seq) VALUES (:id, :scope, :code, :parent_id, :depth, :position, :retired, :last_seq)"
)
_ROW_SQL = text(f"SELECT parent_id, depth, position FROM {WBS_NODE_TABLE} WHERE id = :id")
_REVISE_SQL = text(
    f"UPDATE {WBS_NODE_TABLE} SET parent_id = :parent_id, depth = :depth, position = :position, "
    "last_seq = :last_seq WHERE id = :id"
)
_RETIRE_SQL = text(
    f"UPDATE {WBS_NODE_TABLE} SET retired = :retired, last_seq = :last_seq WHERE id = :id"
)
_CLEAR_SQL = text(f"DELETE FROM {WBS_ALLOCATION_TABLE} WHERE node_id = :node_id")
_LINE_SQL = text(
    f"INSERT INTO {WBS_ALLOCATION_TABLE} (row_id, scope, node_id, cost_code_id, percent, "
    "last_seq) VALUES (:row_id, :scope, :node_id, :cost_code_id, :percent, :last_seq)"
)


def allocation_row_id(node_id: str, cost_code_id: str) -> str:
    """``<node id>:<cost code id>``, the key of an allocation line."""
    return f"{node_id}:{cost_code_id}"


class WbsProjector:
    name = "awp_wbs"
    handles = frozenset({WBS_DEFINED, WBS_REVISED, WBS_RETIRED, WBS_COST_CODES_MAPPED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(WBS_NODE_TABLE, dialect)
            + ddl_for(WBS_ALLOCATION_TABLE, dialect)
            + ddl_for(WBS_NODE_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == WBS_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "parent_id": payload.get("parent_id"),
                    "depth": int(payload["depth"]),
                    "position": int(payload["position"]),
                    "retired": False,
                    "last_seq": event.seq,
                },
            )
        elif kind == WBS_REVISED:
            row = conn.execute(_ROW_SQL, {"id": event.stream_id}).first()
            if row is None:
                raise LookupError(f"no {WBS_NODE_TABLE} row for stream {event.stream_id}")
            changes: dict[str, list[Any]] = payload["changes"]
            conn.execute(
                _REVISE_SQL,
                {
                    "id": event.stream_id,
                    "parent_id": changes["parent_id"][1]
                    if "parent_id" in changes
                    else row.parent_id,
                    "depth": int(changes["depth"][1]) if "depth" in changes else row.depth,
                    "position": int(changes["position"][1])
                    if "position" in changes
                    else row.position,
                    "last_seq": event.seq,
                },
            )
        elif kind == WBS_RETIRED:
            conn.execute(
                _RETIRE_SQL, {"id": event.stream_id, "retired": True, "last_seq": event.seq}
            )
        elif kind == WBS_COST_CODES_MAPPED:
            conn.execute(_CLEAR_SQL, {"node_id": event.stream_id})
            for line in payload["allocations"]:
                conn.execute(
                    _LINE_SQL,
                    {
                        "row_id": allocation_row_id(event.stream_id, line["cost_code_id"]),
                        "scope": event.scope,
                        "node_id": event.stream_id,
                        "cost_code_id": line["cost_code_id"],
                        "percent": line["percent"],
                        "last_seq": event.seq,
                    },
                )
        else:
            raise ValueError(f"WbsProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {WBS_ALLOCATION_TABLE}"))
        conn.execute(text(f"DELETE FROM {WBS_NODE_TABLE}"))
