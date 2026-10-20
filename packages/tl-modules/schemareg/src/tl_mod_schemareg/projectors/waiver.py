"""WaiverProjector: the waiver events into ``cur_schemareg_waiver``."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_schemareg.names import (
    WAIVER_APPROVED,
    WAIVER_REQUESTED,
    WAIVER_REVOKED,
    WAIVER_TABLE,
    WAIVER_VIEW,
)
from tl_mod_schemareg.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {WAIVER_TABLE} (id, scope, project, path, number, reason, expires, "
    "requested_by, last_seq) VALUES (:id, :scope, :project, :path, :number, :reason, :expires, "
    ":requested_by, :last_seq)"
)
_APPROVE_SQL = text(
    f"UPDATE {WAIVER_TABLE} SET approver = :approver, approved_at = :stamp, last_seq = :last_seq "
    "WHERE id = :id"
)
_REVOKE_SQL = text(
    f"UPDATE {WAIVER_TABLE} SET revoked_by = :revoked_by, revoked_at = :stamp, "
    "last_seq = :last_seq WHERE id = :id"
)


class WaiverProjector:
    name = "schemareg_waiver"
    handles = frozenset({WAIVER_REQUESTED, WAIVER_APPROVED, WAIVER_REVOKED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(WAIVER_TABLE, dialect) + ddl_for(WAIVER_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == WAIVER_REQUESTED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "project": payload["project"],
                    "path": payload["path"],
                    "number": int(payload["number"]),
                    "reason": payload["reason"],
                    "expires": payload["expires"],
                    "requested_by": payload["requested_by"],
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == WAIVER_APPROVED:
            conn.execute(
                _APPROVE_SQL,
                {
                    "id": event.stream_id,
                    "approver": payload["approver"],
                    "stamp": stamp,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == WAIVER_REVOKED:
            conn.execute(
                _REVOKE_SQL,
                {
                    "id": event.stream_id,
                    "revoked_by": payload["revoked_by"],
                    "stamp": stamp,
                    "last_seq": event.seq,
                },
            )
        else:
            raise ValueError(f"WaiverProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {WAIVER_TABLE}"))
