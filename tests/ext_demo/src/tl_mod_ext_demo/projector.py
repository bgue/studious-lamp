"""The note table: one row per note, made by ``Note.Added`` (plain DDL, no schema file)."""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from . import NOTE_ADDED, NOTE_TABLE

_CREATE = (
    f"CREATE TABLE IF NOT EXISTS {NOTE_TABLE} ("
    "id TEXT PRIMARY KEY, scope TEXT NOT NULL, body TEXT NOT NULL, "
    "note_class TEXT NOT NULL, last_seq INTEGER NOT NULL)"
)
_INSERT = text(
    f"INSERT INTO {NOTE_TABLE} (id, scope, body, note_class, last_seq) "
    "VALUES (:id, :scope, :body, :note_class, :last_seq)"
)
_TOUCH = text(
    "UPDATE cur_core_record SET version = :version, last_seq = :last_seq, updated_at = :stamp "
    "WHERE id = :id"
)


class NoteProjector:
    name = "ext_demo_note"
    handles = frozenset({NOTE_ADDED})

    def ddl(self, dialect: str) -> list[str]:
        if dialect not in ("sqlite", "postgres"):
            raise ValueError(f"unsupported dialect: {dialect}")
        return [_CREATE]

    def apply(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        conn.execute(
            _INSERT,
            {
                "id": event.stream_id,
                "scope": event.scope,
                "body": payload["body"],
                "note_class": payload["note_class"],
                "last_seq": event.seq,
            },
        )
        conn.execute(
            _TOUCH,
            {
                "id": event.stream_id,
                "version": event.stream_version,
                "last_seq": event.seq,
                "stamp": iso_utc(event.recorded_at),
            },
        )

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {NOTE_TABLE}"))
