"""ActivityRefProjector: the ``ActivityRef.*`` events into ``cur_schedule_activity_ref``.

``Defined`` inserts the reference (present, last seen in the snapshot that had the activity);
``PresenceChanged`` records that a publication found the activity gone or back. Deterministic.
Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_schedule.names import (
    ACTIVITY_REF_TABLE,
    ACTIVITY_REF_VIEW,
    REF_DEFINED,
    REF_PRESENCE,
)
from tl_mod_schedule.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {ACTIVITY_REF_TABLE} (id, scope, schedule_id, schedule_code, activity_id, "
    "first_snapshot_id, first_snapshot_number, present, last_seen_snapshot_id, last_seen_number, "
    "last_seq) VALUES (:id, :scope, :schedule_id, :schedule_code, :activity_id, "
    ":first_snapshot_id, :first_snapshot_number, :present, :first_snapshot_id, "
    ":first_snapshot_number, :last_seq)"
)
_PRESENCE_SQL = text(
    f"UPDATE {ACTIVITY_REF_TABLE} SET present = :present, "
    "last_seen_snapshot_id = :last_seen_snapshot_id, last_seen_number = :last_seen_number, "
    "last_seq = :last_seq WHERE id = :id"
)


class ActivityRefProjector:
    name = "schedule_activity_ref"
    handles = frozenset({REF_DEFINED, REF_PRESENCE})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(ACTIVITY_REF_TABLE, dialect) + ddl_for(ACTIVITY_REF_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == REF_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "schedule_id": payload["schedule_id"],
                    "schedule_code": payload["schedule_code"],
                    "activity_id": payload["activity_id"],
                    "first_snapshot_id": payload["first_snapshot_id"],
                    "first_snapshot_number": int(payload["first_snapshot_number"]),
                    "present": True,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == REF_PRESENCE:
            found = conn.execute(
                _PRESENCE_SQL,
                {
                    "id": event.stream_id,
                    "present": bool(payload["present"]),
                    "last_seen_snapshot_id": payload["last_seen_snapshot_id"],
                    "last_seen_number": int(payload["last_seen_number"]),
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no {ACTIVITY_REF_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"ActivityRefProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {ACTIVITY_REF_TABLE}"))
