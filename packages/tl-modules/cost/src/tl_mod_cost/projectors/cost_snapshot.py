"""CostSnapshotProjector: ``CostSnapshot.Defined`` into ``cur_cost_cost_snapshot``.

A snapshot is never edited, so the event only inserts a row. Deterministic. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_cost.names import COST_SNAPSHOT_TABLE, COST_SNAPSHOT_VIEW, SNAPSHOT_DEFINED
from tl_mod_cost.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {COST_SNAPSHOT_TABLE} (id, scope, period, revision, as_of, currency, "
    "source_name, source_sha256, row_count, new_code_count, revised_code_count, last_seq) "
    "VALUES (:id, :scope, :period, :revision, :as_of, :currency, :source_name, :source_sha256, "
    ":row_count, :new_code_count, :revised_code_count, :last_seq)"
)


class CostSnapshotProjector:
    name = "cost_cost_snapshot"
    handles = frozenset({SNAPSHOT_DEFINED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(COST_SNAPSHOT_TABLE, dialect) + ddl_for(COST_SNAPSHOT_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != SNAPSHOT_DEFINED:
            raise ValueError(f"CostSnapshotProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        conn.execute(
            _INSERT_SQL,
            {
                "id": event.stream_id,
                "scope": event.scope,
                "period": payload["period"],
                "revision": int(payload["revision"]),
                "as_of": payload["as_of"],
                "currency": payload.get("currency"),
                "source_name": payload.get("source_name"),
                "source_sha256": payload.get("source_sha256"),
                "row_count": int(payload["row_count"]),
                "new_code_count": int(payload["new_code_count"]),
                "revised_code_count": int(payload["revised_code_count"]),
                "last_seq": event.seq,
            },
        )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {COST_SNAPSHOT_TABLE}"))
