"""Projector of the interim work packages: ``cur_awp_iwp``.

``IWP.Created`` inserts the row; ``IWP.Revised`` changes the columns it names (the title is the
envelope's). The scope, pin and split events change no column: they only move the envelope's
version. Deterministic: the rows depend only on the events. Register after ``RecordProjector``.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_awp.names import (
    IWP_CREATED,
    IWP_DOCUMENT_PINNED,
    IWP_HELD,
    IWP_HOLD_RELEASED,
    IWP_ISSUED_EVENT,
    IWP_REVISED,
    IWP_SCOPE_ADDED,
    IWP_SCOPE_REMOVED,
    IWP_SIGNED_OFF,
    IWP_SPLIT,
    IWP_TABLE,
    IWP_VIEW,
    MAX_SIGNOFFS,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {IWP_TABLE} (id, scope, discipline, cwp_id, planned_start, planned_finish, "
    "foreman, estimated_hours, crew_text, last_seq) VALUES (:id, :scope, :discipline, :cwp_id, "
    ":planned_start, :planned_finish, :foreman, :estimated_hours, :crew_text, :last_seq)"
)
_ROW_SQL = text(
    "SELECT cwp_id, planned_start, planned_finish, foreman, estimated_hours, crew_text "
    f"FROM {IWP_TABLE} WHERE id = :id"
)
_REVISE_SQL = text(
    f"UPDATE {IWP_TABLE} SET cwp_id = :cwp_id, planned_start = :planned_start, "
    "planned_finish = :planned_finish, foreman = :foreman, estimated_hours = :estimated_hours, "
    "crew_text = :crew_text, last_seq = :last_seq WHERE id = :id"
)
_BUMP_SQL = text(f"UPDATE {IWP_TABLE} SET last_seq = :last_seq WHERE id = :id")
_REVISABLE = (
    "cwp_id",
    "planned_start",
    "planned_finish",
    "foreman",
    "estimated_hours",
    "crew_text",
)
_SIGNOFFS_SQL = text(f"SELECT signoffs_json FROM {IWP_TABLE} WHERE id = :id")
_SIGNOFF_SQL = text(
    f"UPDATE {IWP_TABLE} SET signoffs_json = :rows, last_seq = :last_seq WHERE id = :id"
)
_FOREMAN_SQL = text(
    f"UPDATE {IWP_TABLE} SET foreman = :foreman, last_seq = :last_seq WHERE id = :id"
)
_BUMPS = frozenset(
    {
        IWP_SCOPE_ADDED,
        IWP_SCOPE_REMOVED,
        IWP_DOCUMENT_PINNED,
        IWP_SPLIT,
        IWP_HELD,
        IWP_HOLD_RELEASED,
    }
)


def signoff_rows(value: Any) -> list[dict[str, Any]]:
    """The sign-off rows of a ``signoffs_json`` cell (text on SQLite, a list on Postgres)."""
    if value is None:
        return []
    found = json.loads(value) if isinstance(value, str | bytes) else value
    return [dict(r) for r in found]


class IwpProjector:
    name = "awp_iwp"
    handles = frozenset({IWP_CREATED, IWP_REVISED, IWP_SIGNED_OFF, IWP_ISSUED_EVENT, *_BUMPS})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(IWP_TABLE, dialect) + ddl_for(IWP_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == IWP_CREATED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "discipline": payload["discipline"],
                    "cwp_id": payload.get("cwp_id"),
                    "planned_start": payload.get("planned_start"),
                    "planned_finish": payload.get("planned_finish"),
                    "foreman": payload.get("foreman"),
                    "estimated_hours": payload.get("estimated_hours"),
                    "crew_text": payload.get("crew_text"),
                    "last_seq": event.seq,
                },
            )
        elif kind == IWP_REVISED:
            row = conn.execute(_ROW_SQL, {"id": event.stream_id}).first()
            if row is None:
                raise LookupError(f"no {IWP_TABLE} row for stream {event.stream_id}")
            changes: dict[str, list[Any]] = payload["changes"]
            values: dict[str, Any] = {name: getattr(row, name) for name in _REVISABLE}
            for name in _REVISABLE:
                if name in changes:
                    values[name] = changes[name][1]
            conn.execute(_REVISE_SQL, {"id": event.stream_id, **values, "last_seq": event.seq})
        elif kind == IWP_SIGNED_OFF:
            held = conn.execute(_SIGNOFFS_SQL, {"id": event.stream_id}).scalar_one_or_none()
            rows = signoff_rows(held)
            rows.append(
                {
                    "by": payload["by"],
                    "role": payload["role"],
                    "at": iso_utc(event.effective_at),
                    "record_hash": payload["record_hash"],
                }
            )
            text_rows = json.dumps(
                rows[-MAX_SIGNOFFS:], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            conn.execute(
                _SIGNOFF_SQL, {"id": event.stream_id, "rows": text_rows, "last_seq": event.seq}
            )
        elif kind == IWP_ISSUED_EVENT:
            conn.execute(
                _FOREMAN_SQL,
                {"id": event.stream_id, "foreman": payload["foreman"], "last_seq": event.seq},
            )
        elif kind in _BUMPS:
            conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        else:
            raise ValueError(f"IwpProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {IWP_TABLE}"))


def iwp_projectors() -> list[IwpProjector]:
    return [IwpProjector()]
