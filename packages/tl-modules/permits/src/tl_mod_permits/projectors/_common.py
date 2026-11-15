"""What every permits projector shares (the same helpers as the quality module's).

A module event lands on the stream of a record whose envelope row ``RecordProjector`` made. The
event moves the stream's version, so each record projector keeps ``cur_core_record`` in step
(``version``, ``last_seq``, ``updated_at``), the way the pset and workflow projectors do.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc
from tl_schema.ddl_loader import statements

_TOUCH_SQL = text(
    "UPDATE cur_core_record SET version = :version, last_seq = :last_seq, updated_at = :stamp "
    "WHERE id = :id"
)


def ddl_for(table: str, dialect: str) -> list[str]:
    """The generated CREATE statements of ``table`` for ``dialect`` (``ValueError`` otherwise)."""
    if dialect == "sqlite" or dialect == "postgres":
        return statements(table, dialect)
    raise ValueError(f"unsupported dialect: {dialect}")


def touch_record(conn: Connection, event: Event) -> None:
    """Move the envelope row of the event's stream to the event's version."""
    params: dict[str, Any] = {
        "id": event.stream_id,
        "version": event.stream_version,
        "last_seq": event.seq,
        "stamp": iso_utc(event.recorded_at),
    }
    if conn.execute(_TOUCH_SQL, params).rowcount == 0:
        raise LookupError(f"no cur_core_record row for stream {event.stream_id}")


def require_row(rowcount: int, table: str, event: Event) -> None:
    """An event that changes a row finds it: a missing one is a broken stream, not a no-op."""
    if rowcount == 0:
        raise LookupError(f"no {table} row for stream {event.stream_id}")


def aware(value: Any) -> str | None:
    """An aware time as the one stored form (UTC, microseconds); ``None`` stays ``None``.

    A naive time is refused (``ValueError``): a permit's times are aware.
    """
    if value is None:
        return None
    return iso_utc(datetime.fromisoformat(str(value)))


def reading(value: Any) -> float | None:
    """A reading sent as decimal text, as the number a NUMERIC column is bound with."""
    return None if value is None else float(Decimal(str(value)))


def dumps(value: Any) -> str:
    """The JSON text of a column that holds JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
