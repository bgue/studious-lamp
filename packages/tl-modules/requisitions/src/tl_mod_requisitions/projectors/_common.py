"""What both requisitions projectors share (the same helpers as the materials module's).

A module event lands on the stream of a record whose envelope row ``RecordProjector`` made. The
event moves the stream's version, so each projector keeps ``cur_core_record`` in step
(``version``, ``last_seq``, ``updated_at``)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc
from tl_schema.ddl_loader import statements

_TOUCH_SQL = text(
    "UPDATE cur_core_record SET version = :version, last_seq = :last_seq, updated_at = :stamp "
    "WHERE id = :id"
)
_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")


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


def record_type_of(conn: Connection, event: Event) -> str:
    """The record type of the event's stream, from its envelope row."""
    found = conn.execute(_TYPE_SQL, {"id": event.stream_id}).scalar_one_or_none()
    if found is None:
        raise LookupError(f"no cur_core_record row for stream {event.stream_id}")
    return str(found)


def update_row(conn: Connection, table: str, event: Event, values: dict[str, Any]) -> None:
    """Set ``values`` and ``last_seq`` on the stream's row; a missing row is a broken stream."""
    sets = ", ".join(f"{column} = :{column}" for column in values)
    done = conn.execute(
        text(f"UPDATE {table} SET {sets}{', ' if sets else ''}last_seq = :last_seq WHERE id = :id"),
        {**values, "id": event.stream_id, "last_seq": event.seq},
    )
    if done.rowcount == 0:
        raise LookupError(f"no {table} row for stream {event.stream_id}")
