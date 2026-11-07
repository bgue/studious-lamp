"""Projector of the constraints: ``cur_awp_constraint``.

``Constraint.Raised`` inserts the row (``suppress_hash`` is the hash of the facts of a check
constraint, ``None`` for the other sources); ``Constraint.Assigned`` changes the owner;
``Constraint.Cleared`` sets who cleared it, when (the event's time) and why, and drops the hash when
the clear was a check's own (``suppress`` is false). The state is the envelope's (the workflow).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_awp.names import (
    CONSTRAINT_ASSIGNED,
    CONSTRAINT_CLEARED,
    CONSTRAINT_RAISED,
    CONSTRAINT_TABLE,
    CONSTRAINT_VIEW,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {CONSTRAINT_TABLE} (id, scope, iwp_id, constraint_type, source, owner, need_by, "
    "description_text, check_name, raised_at, suppress_hash, last_seq) VALUES (:id, :scope, "
    ":iwp_id, :constraint_type, :source, :owner, :need_by, :description, :check_name, "
    ":raised_at, :suppress_hash, :last_seq)"
)
_ASSIGN_SQL = text(
    f"UPDATE {CONSTRAINT_TABLE} SET owner = :owner, need_by = COALESCE(:need_by, need_by), "
    "last_seq = :last_seq WHERE id = :id"
)
_CLEAR_SQL = text(
    f"UPDATE {CONSTRAINT_TABLE} SET cleared_at = :cleared_at, cleared_by = :cleared_by, "
    "clear_reason = :reason, last_seq = :last_seq WHERE id = :id"
)
_DROP_HASH_SQL = text(f"UPDATE {CONSTRAINT_TABLE} SET suppress_hash = NULL WHERE id = :id")


class ConstraintProjector:
    name = "awp_constraint"
    handles = frozenset({CONSTRAINT_RAISED, CONSTRAINT_ASSIGNED, CONSTRAINT_CLEARED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CONSTRAINT_TABLE, dialect) + ddl_for(CONSTRAINT_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == CONSTRAINT_RAISED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "iwp_id": payload["iwp_id"],
                    "constraint_type": payload["constraint_type"],
                    "source": payload["source"],
                    "owner": payload["owner"],
                    "need_by": payload.get("need_by"),
                    "description": payload.get("description"),
                    "check_name": payload.get("check_name"),
                    "raised_at": payload["raised_at"],
                    "suppress_hash": payload.get("suppress_hash"),
                    "last_seq": event.seq,
                },
            )
        elif kind == CONSTRAINT_ASSIGNED:
            conn.execute(
                _ASSIGN_SQL,
                {
                    "id": event.stream_id,
                    "owner": payload["owner"],
                    "need_by": payload.get("need_by"),
                    "last_seq": event.seq,
                },
            )
        elif kind == CONSTRAINT_CLEARED:
            conn.execute(
                _CLEAR_SQL,
                {
                    "id": event.stream_id,
                    "cleared_at": iso_utc(event.recorded_at),
                    "cleared_by": payload["by"],
                    "reason": payload["reason"],
                    "last_seq": event.seq,
                },
            )
            if payload.get("suppress", True) is False:
                conn.execute(_DROP_HASH_SQL, {"id": event.stream_id})
        else:
            raise ValueError(f"ConstraintProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CONSTRAINT_TABLE}"))


def constraint_projectors() -> list[ConstraintProjector]:
    return [ConstraintProjector()]
