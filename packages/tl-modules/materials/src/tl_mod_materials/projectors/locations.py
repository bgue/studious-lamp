"""LocationProjector: ``InventoryLocation.*`` into ``cur_materials_location``.

``Defined`` inserts the node (parent and depth are the command's, checked there); ``Revised``
changes
its kind (the title is the envelope's, moved by ``Record.Updated``); ``Retired`` sets the flag.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_materials.names import (
    LOCATION_DEFINED,
    LOCATION_RETIRED,
    LOCATION_REVISED,
    LOCATION_TABLE,
    LOCATION_VIEW,
)
from tl_mod_materials.projectors._common import ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {LOCATION_TABLE} (id, scope, code, kind, parent_id, depth, retired, last_seq) "
    "VALUES (:id, :scope, :code, :kind, :parent_id, :depth, :retired, :last_seq)"
)
_KIND = text(f"UPDATE {LOCATION_TABLE} SET kind = :kind, last_seq = :last_seq WHERE id = :id")
_BUMP = text(f"UPDATE {LOCATION_TABLE} SET last_seq = :last_seq WHERE id = :id")
_RETIRE = text(
    f"UPDATE {LOCATION_TABLE} SET retired = :retired, last_seq = :last_seq WHERE id = :id"
)


class LocationProjector:
    name = "materials_location"
    handles = frozenset({LOCATION_DEFINED, LOCATION_REVISED, LOCATION_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(LOCATION_TABLE, dialect) + ddl_for(LOCATION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == LOCATION_DEFINED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "kind": payload["kind"],
                    "parent_id": payload.get("parent_id"),
                    "depth": int(payload["depth"]),
                    "retired": False,
                    "last_seq": event.seq,
                },
            )
        elif kind == LOCATION_REVISED:
            if payload.get("kind") is not None:
                done = conn.execute(
                    _KIND, {"id": event.stream_id, "kind": payload["kind"], "last_seq": event.seq}
                )
            else:
                done = conn.execute(_BUMP, {"id": event.stream_id, "last_seq": event.seq})
            require_row(done.rowcount, LOCATION_TABLE, event)
        elif kind == LOCATION_RETIRED:
            done = conn.execute(
                _RETIRE, {"id": event.stream_id, "retired": True, "last_seq": event.seq}
            )
            require_row(done.rowcount, LOCATION_TABLE, event)
        else:
            raise ValueError(f"LocationProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {LOCATION_TABLE}"))
