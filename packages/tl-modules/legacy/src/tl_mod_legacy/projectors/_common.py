"""What the legacy projector shares (the same helpers as the other modules')."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc
from tl_schema.ddl_loader import statements

_TOUCH_SQL = text(
    "UPDATE cur_core_record SET version = :version, last_seq = :last_seq, updated_at = :stamp "
    "WHERE id = :id"
)


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ddl_for(table: str, dialect: str) -> list[str]:
    if dialect == "sqlite" or dialect == "postgres":
        return statements(table, dialect)
    raise ValueError(f"unsupported dialect: {dialect}")


def touch_record(conn: Connection, event: Event) -> None:
    params: dict[str, Any] = {
        "id": event.stream_id,
        "version": event.stream_version,
        "last_seq": event.seq,
        "stamp": iso_utc(event.recorded_at),
    }
    if conn.execute(_TOUCH_SQL, params).rowcount == 0:
        raise LookupError(f"no cur_core_record row for stream {event.stream_id}")
