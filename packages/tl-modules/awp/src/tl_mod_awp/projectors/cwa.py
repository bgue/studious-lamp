"""CwaProjector: the ``CWA.*`` events into ``cur_awp_cwa``.

``Defined`` inserts the area; ``Revised`` changes its location (the title is the envelope's, moved
by ``Record.Updated``, and is ignored here); ``Retired`` sets the flag. Deterministic. Register it
after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_awp.names import CWA_DEFINED, CWA_RETIRED, CWA_REVISED, CWA_TABLE, CWA_VIEW
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {CWA_TABLE} (id, scope, code, location_text, retired, last_seq) "
    "VALUES (:id, :scope, :code, :location_text, :retired, :last_seq)"
)
_LOCATION_SQL = text(
    f"UPDATE {CWA_TABLE} SET location_text = :location_text, last_seq = :last_seq WHERE id = :id"
)
_RETIRE_SQL = text(
    f"UPDATE {CWA_TABLE} SET retired = :retired, last_seq = :last_seq WHERE id = :id"
)
_BUMP_SQL = text(f"UPDATE {CWA_TABLE} SET last_seq = :last_seq WHERE id = :id")


class CwaProjector:
    name = "awp_cwa"
    handles = frozenset({CWA_DEFINED, CWA_REVISED, CWA_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CWA_TABLE, dialect) + ddl_for(CWA_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == CWA_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "location_text": payload.get("location_text"),
                    "retired": False,
                    "last_seq": event.seq,
                },
            )
        elif kind == CWA_REVISED:
            changes: dict[str, list[Any]] = payload["changes"]
            if "location_text" in changes:
                conn.execute(
                    _LOCATION_SQL,
                    {
                        "id": event.stream_id,
                        "location_text": changes["location_text"][1],
                        "last_seq": event.seq,
                    },
                )
            else:
                conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        elif kind == CWA_RETIRED:
            conn.execute(
                _RETIRE_SQL, {"id": event.stream_id, "retired": True, "last_seq": event.seq}
            )
        else:
            raise ValueError(f"CwaProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CWA_TABLE}"))
