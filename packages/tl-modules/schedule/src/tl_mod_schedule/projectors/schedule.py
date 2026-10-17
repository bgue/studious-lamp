"""ScheduleProjector: ``Schedule.Defined`` and ``Schedule.SnapshotPublished`` into the table.

A schedule is registered once; each publication moves its current-snapshot pointer. Deterministic:
the row depends only on the events of the stream. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_schedule.names import (
    SCHEDULE_DEFINED,
    SCHEDULE_SNAPSHOT_PUBLISHED,
    SCHEDULE_TABLE,
    SCHEDULE_VIEW,
)
from tl_mod_schedule.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {SCHEDULE_TABLE} (id, scope, code, schedule_type, owner, p6_project, last_seq) "
    "VALUES (:id, :scope, :code, :schedule_type, :owner, :p6_project, :last_seq)"
)
_PUBLISH_SQL = text(
    f"UPDATE {SCHEDULE_TABLE} SET current_snapshot_id = :snapshot_id, "
    "current_snapshot_number = :number, current_data_date = :data_date, last_seq = :last_seq "
    "WHERE id = :id"
)


class ScheduleProjector:
    name = "schedule_schedule"
    handles = frozenset({SCHEDULE_DEFINED, SCHEDULE_SNAPSHOT_PUBLISHED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(SCHEDULE_TABLE, dialect) + ddl_for(SCHEDULE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == SCHEDULE_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "schedule_type": payload["schedule_type"],
                    "owner": payload.get("owner"),
                    "p6_project": payload.get("p6_project"),
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == SCHEDULE_SNAPSHOT_PUBLISHED:
            found = conn.execute(
                _PUBLISH_SQL,
                {
                    "id": event.stream_id,
                    "snapshot_id": payload["snapshot_id"],
                    "number": int(payload["snapshot_number"]),
                    "data_date": payload["data_date"],
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no {SCHEDULE_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"ScheduleProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {SCHEDULE_TABLE}"))
