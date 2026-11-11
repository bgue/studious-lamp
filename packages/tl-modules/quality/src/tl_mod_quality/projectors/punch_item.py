"""PunchItemProjector: ``PunchItem.Raised`` and the events after it.

``Record.Created`` makes the envelope row (``RecordProjector``); ``PunchItem.Raised`` follows in the
same append and makes this module's row. The workflow state is the envelope ``status``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_quality.names import (
    DEFAULT_CATEGORY,
    PUNCH_CLEARED,
    PUNCH_EDITED,
    PUNCH_EVENTS,
    PUNCH_ITEM_TABLE,
    PUNCH_ITEM_VIEW,
    PUNCH_RAISED,
    PUNCH_REOPENED,
    PUNCH_VERIFIED,
    PUNCH_VOIDED,
)
from tl_mod_quality.projectors._common import ddl_for, require_row, touch_record

#: The columns an ``Edited`` event may change (the subject and detail live on the envelope).
EDITABLE = ("area", "system", "due_on", "category", "assignee")

_INSERT = text(
    f"INSERT INTO {PUNCH_ITEM_TABLE} (id, scope, area, system, due_on, category, assignee, "
    "raised_by, source_id, reopen_count, last_seq) VALUES (:id, :scope, :area, :system, "
    ":due_on, :category, :assignee, :raised_by, :source_id, 0, :last_seq)"
)
_CLEAR = text(
    f"UPDATE {PUNCH_ITEM_TABLE} SET cleared_by = :by, cleared_on = :on, clear_note = :note, "
    "last_seq = :last_seq WHERE id = :id"
)
_VERIFY = text(
    f"UPDATE {PUNCH_ITEM_TABLE} SET verified_by = :by, verified_on = :on, last_seq = :last_seq "
    "WHERE id = :id"
)
_REOPEN = text(
    f"UPDATE {PUNCH_ITEM_TABLE} SET cleared_by = NULL, cleared_on = NULL, clear_note = NULL, "
    "verified_by = NULL, verified_on = NULL, reopen_count = reopen_count + 1, "
    "last_reopen_reason = :reason, last_seq = :last_seq WHERE id = :id"
)
_VOID = text(
    f"UPDATE {PUNCH_ITEM_TABLE} SET void_reason = :reason, last_seq = :last_seq WHERE id = :id"
)


def _date_part(value: Any) -> str:
    """The ``YYYY-MM-DD`` part of an ISO date or datetime text."""
    return str(value)[:10]


class PunchItemProjector:
    name = "quality_punch_item"
    handles = PUNCH_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(PUNCH_ITEM_TABLE, dialect) + ddl_for(PUNCH_ITEM_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == PUNCH_RAISED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "area": payload.get("area"),
                    "system": payload.get("system"),
                    "due_on": payload.get("due_on"),
                    "category": payload.get("category") or DEFAULT_CATEGORY,
                    "assignee": payload.get("assignee"),
                    "raised_by": payload["raised_by"],
                    "source_id": payload.get("source_id"),
                    "last_seq": event.seq,
                },
            )
        else:
            done = self._update(conn, event, kind, payload)
            require_row(done, PUNCH_ITEM_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, kind: str, payload: dict[str, Any]) -> int:
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        if kind == PUNCH_EDITED:
            changes: dict[str, Any] = payload["changes"]
            columns = [c for c in EDITABLE if c in changes]
            params: dict[str, Any] = {c: changes[c][1] for c in columns}
            sets = ", ".join(f"{c} = :{c}" for c in columns)
            sets = f"{sets}, " if sets else ""
            stmt = text(f"UPDATE {PUNCH_ITEM_TABLE} SET {sets}last_seq = :last_seq WHERE id = :id")
            return conn.execute(stmt, {**base, **params}).rowcount
        if kind == PUNCH_CLEARED:
            params = {"by": payload["by"], "on": _date_part(payload["at"]), "note": payload["note"]}
            return conn.execute(_CLEAR, {**base, **params}).rowcount
        if kind == PUNCH_VERIFIED:
            params = {"by": payload["by"], "on": _date_part(payload["at"])}
            return conn.execute(_VERIFY, {**base, **params}).rowcount
        if kind == PUNCH_REOPENED:
            return conn.execute(_REOPEN, {**base, "reason": payload["reason"]}).rowcount
        if kind == PUNCH_VOIDED:
            return conn.execute(_VOID, {**base, "reason": payload["reason"]}).rowcount
        raise ValueError(f"PunchItemProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PUNCH_ITEM_TABLE}"))
