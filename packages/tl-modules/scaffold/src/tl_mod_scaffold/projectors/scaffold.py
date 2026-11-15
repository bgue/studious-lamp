"""ScaffoldProjector: ``Scaffold.Registered`` and the events after it, both tables.

``Record.Created`` makes the envelope row (``RecordProjector``); ``Scaffold.Registered`` follows in
the same append and makes the scaffold row. ``Scaffold.Inspected`` updates the scaffold row and
makes the row of the inspection record named by ``inspection_id`` (its envelope was made by
the command just before). The workflow state is the envelope ``status``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_scaffold.names import (
    DESIGNED,
    DISMANTLE_STARTED,
    ERECTING,
    INSPECTED,
    INSPECTION_DUE,
    INSPECTION_TABLE,
    INSPECTION_VIEW,
    MODIFIED,
    REGISTERED,
    RELEASED,
    REMOVED_EVENT,
    SCAFFOLD_EVENTS,
    SCAFFOLD_TABLE,
    SCAFFOLD_VIEW,
)
from tl_mod_scaffold.projectors._common import ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {SCAFFOLD_TABLE} (id, scope, request_id, for_record_id, location_text, "
    "elevation, gridline, load_class, inspection_count, last_seq) VALUES (:id, :scope, "
    ":request_id, :for_record_id, :location_text, :elevation, :gridline, :load_class, 0, "
    ":last_seq)"
)
_ERECTING = text(
    f"UPDATE {SCAFFOLD_TABLE} SET next_due_on = :due, last_seq = :last_seq WHERE id = :id"
)
_INSPECTED = text(
    f"UPDATE {SCAFFOLD_TABLE} SET tag = :tag, tagged_on = :on, last_inspected_on = :on, "
    "next_due_on = :due, inspection_count = inspection_count + 1, last_seq = :last_seq "
    "WHERE id = :id"
)
_INSPECTION = text(
    f"INSERT INTO {INSPECTION_TABLE} (id, scope, scaffold_id, inspector, inspected_on, result, "
    "tag, note, last_seq) VALUES (:inspection, :scope, :id, :inspector, :on, :result, :tag, "
    ":note, :last_seq)"
)
_MODIFIED = text(
    f"UPDATE {SCAFFOLD_TABLE} SET modify_reason = :reason, last_seq = :last_seq WHERE id = :id"
)
_DISMANTLE = text(
    f"UPDATE {SCAFFOLD_TABLE} SET dismantle_reason = :reason, last_seq = :last_seq WHERE id = :id"
)
_FLAGGED = text(
    f"UPDATE {SCAFFOLD_TABLE} SET flagged_due_on = :due, last_seq = :last_seq WHERE id = :id"
)
_TOUCH_ONLY = text(f"UPDATE {SCAFFOLD_TABLE} SET last_seq = :last_seq WHERE id = :id")


class ScaffoldProjector:
    name = "scaffold_scaffold"
    handles = SCAFFOLD_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return [
            *ddl_for(SCAFFOLD_TABLE, dialect),
            *ddl_for(SCAFFOLD_VIEW, dialect),
            *ddl_for(INSPECTION_TABLE, dialect),
            *ddl_for(INSPECTION_VIEW, dialect),
        ]

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == REGISTERED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "request_id": payload["request_id"],
                    "for_record_id": payload.get("for_record_id"),
                    "location_text": payload.get("location_text"),
                    "elevation": payload.get("elevation"),
                    "gridline": payload.get("gridline"),
                    "load_class": payload.get("load_class"),
                    "last_seq": event.seq,
                },
            )
        else:
            done = self._update(conn, event, kind, payload)
            require_row(done, SCAFFOLD_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, kind: str, payload: dict[str, Any]) -> int:
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        if kind == ERECTING:
            return conn.execute(_ERECTING, {**base, "due": payload["next_due_on"]}).rowcount
        if kind == INSPECTED:
            params = {
                "tag": payload["tag"],
                "on": payload["inspected_on"],
                "due": payload["next_due_on"],
            }
            done = conn.execute(_INSPECTED, {**base, **params}).rowcount
            conn.execute(
                _INSPECTION,
                {
                    **base,
                    "inspection": payload["inspection_id"],
                    "scope": event.scope,
                    "inspector": event.actor,
                    "on": payload["inspected_on"],
                    "result": payload["result"],
                    "tag": payload["tag"],
                    "note": payload.get("note"),
                },
            )
            return done
        if kind == MODIFIED:
            return conn.execute(_MODIFIED, {**base, "reason": payload["reason"]}).rowcount
        if kind == DISMANTLE_STARTED:
            return conn.execute(_DISMANTLE, {**base, "reason": payload["reason"]}).rowcount
        if kind == INSPECTION_DUE:
            return conn.execute(_FLAGGED, {**base, "due": payload["due_on"]}).rowcount
        if kind in (DESIGNED, RELEASED, REMOVED_EVENT):
            return conn.execute(_TOUCH_ONLY, base).rowcount
        raise ValueError(f"ScaffoldProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {INSPECTION_TABLE}"))
        conn.execute(text(f"DELETE FROM {SCAFFOLD_TABLE}"))
