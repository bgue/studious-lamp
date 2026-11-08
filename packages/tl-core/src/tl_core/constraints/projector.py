"""Projector of the constraints: ``cur_core_constraint`` (ADR-0024).

``Constraint.Raised`` inserts the row. ``suppress_hash`` holds the facts hash of a check raise
(``None`` for the other sources): ``Constraint.Cleared`` keeps it when a person cleared a
check-raised constraint (``suppress`` true) and drops it when the clear was a module's
(``suppress`` false). ``cleared_at``, ``effective_at`` and ``due_at`` are world time from the
payload; the event envelope times are never read. The workflow state is the envelope's (the
workflow projector)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.constraints.commands import (
    EV_ASSIGNED,
    EV_CLEARED,
    EV_RAISED,
    EV_WITHDRAWN,
    EVENT_TYPES,
    TABLE,
)
from tl_core.ledger import Event, iso_utc

_INSERT_SQL = text(
    f"INSERT INTO {TABLE} (id, scope, subject_id, phase, severity, category, source, owner, "
    "description_text, check_name, suppress_hash, target_kind, target_id, target_ref_type, "
    "target_ref_text, effective_at, due_at, last_seq) VALUES (:id, :scope, :subject_id, :phase, "
    ":severity, :category, :source, :owner, :description, :check_name, :suppress_hash, "
    ":target_kind, :target_id, :target_ref_type, :target_ref_text, :effective_at, :due_at, "
    ":last_seq)"
)
_ASSIGN_SQL = text(f"UPDATE {TABLE} SET owner = :owner, last_seq = :last_seq WHERE id = :id")
_CLEAR_SQL = text(
    f"UPDATE {TABLE} SET cleared_at = :cleared_at, cleared_by = :cleared_by, "
    "clear_reason = :reason, last_seq = :last_seq WHERE id = :id"
)
_DROP_HASH_SQL = text(f"UPDATE {TABLE} SET suppress_hash = NULL WHERE id = :id")
_SEQ_SQL = text(f"UPDATE {TABLE} SET last_seq = :last_seq WHERE id = :id")
_TOUCH_SQL = text(
    "UPDATE cur_core_record SET version = :version, last_seq = :last_seq, updated_at = :stamp "
    "WHERE id = :id"
)


def _touch(conn: Connection, event: Event) -> None:
    params: dict[str, Any] = {
        "id": event.stream_id,
        "version": event.stream_version,
        "last_seq": event.seq,
        "stamp": iso_utc(event.recorded_at),
    }
    if conn.execute(_TOUCH_SQL, params).rowcount == 0:
        raise LookupError(f"no cur_core_record row for stream {event.stream_id}")


class ConstraintProjector:
    name = "core_constraint"
    handles = EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect not in ("sqlite", "postgres"):
            raise ValueError(f"unsupported dialect: {dialect}")
        return statements(TABLE, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        sid = event.stream_id
        if kind == EV_RAISED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": sid,
                    "scope": event.scope,
                    "subject_id": payload["subject_id"],
                    "phase": payload["phase"],
                    "severity": payload["severity"],
                    "category": payload["category"],
                    "source": payload["source"],
                    "owner": payload.get("owner"),
                    "description": payload.get("description"),
                    "check_name": payload.get("check_name"),
                    "suppress_hash": payload.get("facts_hash"),
                    "target_kind": payload.get("target_kind"),
                    "target_id": payload.get("target_id"),
                    "target_ref_type": payload.get("target_ref_type"),
                    "target_ref_text": payload.get("target_ref_text"),
                    "effective_at": payload.get("effective_at"),
                    "due_at": payload.get("due_at"),
                    "last_seq": event.seq,
                },
            )
        elif kind == EV_ASSIGNED:
            conn.execute(_ASSIGN_SQL, {"id": sid, "owner": payload["owner"], "last_seq": event.seq})
        elif kind == EV_CLEARED:
            conn.execute(
                _CLEAR_SQL,
                {
                    "id": sid,
                    "cleared_at": payload["cleared_at"],
                    "cleared_by": payload["cleared_by"],
                    "reason": payload["reason"],
                    "last_seq": event.seq,
                },
            )
            if payload.get("suppress") is False:
                conn.execute(_DROP_HASH_SQL, {"id": sid})
        elif kind == EV_WITHDRAWN:
            conn.execute(_SEQ_SQL, {"id": sid, "last_seq": event.seq})
        else:
            raise ValueError(f"ConstraintProjector cannot apply event type: {kind}")
        _touch(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {TABLE}"))
