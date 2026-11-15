"""IsolationProjector: ``Isolation.Applied`` and the events after it.

The workflow state is the envelope ``status``. Who did a step is the event's actor.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_permits.names import (
    ISOLATION_APPLIED,
    ISOLATION_EVENTS,
    ISOLATION_REMOVED,
    ISOLATION_TABLE,
    ISOLATION_VERIFIED,
    ISOLATION_VIEW,
)
from tl_mod_permits.projectors._common import aware, ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {ISOLATION_TABLE} (id, scope, point_text, point_record_id, energy, method, "
    "lock_number, tag_number, applied_by, applied_at, last_seq) VALUES (:id, :scope, :point_text, "
    ":point_record_id, :energy, :method, :lock_number, :tag_number, :actor, :applied_at, :last_seq)"
)
_VERIFY = text(
    f"UPDATE {ISOLATION_TABLE} SET verified_by = :actor, verified_at = :verified_at, "
    "last_seq = :last_seq WHERE id = :id"
)
_REMOVE = text(
    f"UPDATE {ISOLATION_TABLE} SET removed_by = :actor, removed_at = :removed_at, "
    "last_seq = :last_seq WHERE id = :id"
)


class IsolationProjector:
    name = "permits_isolation"
    handles = ISOLATION_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(ISOLATION_TABLE, dialect) + ddl_for(ISOLATION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq, "actor": event.actor}
        if kind == ISOLATION_APPLIED:
            conn.execute(
                _INSERT,
                {
                    **base,
                    "scope": event.scope,
                    "point_text": payload["point_text"],
                    "point_record_id": payload.get("point_record_id"),
                    "energy": payload["energy"],
                    "method": payload.get("method"),
                    "lock_number": payload.get("lock_number"),
                    "tag_number": payload.get("tag_number"),
                    "applied_at": aware(payload["applied_at"]),
                },
            )
        elif kind == ISOLATION_VERIFIED:
            params = {**base, "verified_at": aware(payload["verified_at"])}
            require_row(conn.execute(_VERIFY, params).rowcount, ISOLATION_TABLE, event)
        elif kind == ISOLATION_REMOVED:
            params = {**base, "removed_at": aware(payload["removed_at"])}
            require_row(conn.execute(_REMOVE, params).rowcount, ISOLATION_TABLE, event)
        else:
            raise ValueError(f"IsolationProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {ISOLATION_TABLE}"))
