"""NumberingProjector: ``Numbering.Allocated`` events into ``cur_numbering`` (brief 8).

One row per counter (a ledger stream ``numbering:<scope>:<pattern>:<prefix>``) holding the highest
sequence number allocated. The allocator reads this row inside the creating transaction, so the
row is also the read-your-writes view of the counter. Deterministic: depends only on the event and
the existing row.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc

ALLOCATED = "Numbering.Allocated"

_UPDATE_SQL = text(
    "UPDATE cur_numbering SET scope = :scope, pattern = :pattern, prefix = :prefix, "
    "last_sequence = :last_sequence, last_key = :last_key, last_record_id = :last_record_id, "
    "allocations = allocations + 1, version = :version, last_seq = :last_seq, "
    "updated_at = :updated_at WHERE counter_id = :counter_id"
)
_INSERT_SQL = text(
    "INSERT INTO cur_numbering (counter_id, scope, pattern, prefix, last_sequence, last_key, "
    "last_record_id, allocations, version, last_seq, updated_at) VALUES (:counter_id, :scope, "
    ":pattern, :prefix, :last_sequence, :last_key, :last_record_id, 1, :version, :last_seq, "
    ":updated_at)"
)


class NumberingProjector:
    name = "numbering"
    handles = frozenset({ALLOCATED})

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_numbering", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        params = {
            "counter_id": event.stream_id,
            "scope": event.scope,
            "pattern": payload["pattern"],
            "prefix": payload["prefix"],
            "last_sequence": payload["sequence"],
            "last_key": payload["key"],
            "last_record_id": payload.get("record_id"),
            "version": event.stream_version,
            "last_seq": event.seq,
            "updated_at": iso_utc(event.recorded_at),
        }
        if conn.execute(_UPDATE_SQL, params).rowcount == 0:
            conn.execute(_INSERT_SQL, params)

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_numbering"))
