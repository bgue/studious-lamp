"""Insert archived events verbatim into an empty ``events`` table (shared by both dialects).

Restore never goes through ``Ledger.append``, which assigns seq, ids, hashes and times. The archive
already holds all of them, and the hash chain is only worth anything if the restored rows are
byte-for-byte the sealed ones. The dialect modules call this inside their own write transaction.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from itertools import islice

from sqlalchemy import Connection, text
from tl_core.archive import RestoreError
from tl_core.ledger import Event, canonical_json, iso_utc

BATCH = 1000

_INSERT = text(
    """
    INSERT INTO events (
      seq, event_id, stream_id, stream_type, stream_version, event_type, schema_version, scope,
      payload, actor, recorded_at, effective_at, correlation_id, causation_id, source,
      prev_hash, hash
    ) VALUES (
      :seq, :event_id, :stream_id, :stream_type, :stream_version, :event_type, :schema_version,
      :scope, :payload, :actor, :recorded_at, :effective_at, :correlation_id, :causation_id,
      :source, :prev_hash, :hash
    )
    """
)


def _params(event: Event) -> dict[str, object]:
    return {
        "seq": event.seq,
        "event_id": event.event_id,
        "stream_id": event.stream_id,
        "stream_type": event.stream_type,
        "stream_version": event.stream_version,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "scope": event.scope,
        "payload": canonical_json(event.payload),
        "actor": event.actor,
        "recorded_at": iso_utc(event.recorded_at),
        "effective_at": iso_utc(event.effective_at),
        "correlation_id": event.correlation_id,
        "causation_id": event.causation_id,
        "source": event.source,
        "prev_hash": event.prev_hash,
        "hash": event.hash,
    }


def _gap_free(events: Iterable[Event]) -> Iterator[Event]:
    expected = 1
    for event in events:
        if event.seq != expected:
            raise RestoreError(f"restore needs seq {expected} next, found {event.seq}")
        expected += 1
        yield event


def insert_events(conn: Connection, events: Iterable[Event]) -> int:
    """Insert ``events`` (seq 1, 2, 3, ... without gaps) into an empty ``events`` table.

    Raises ``RestoreError`` if the table already has rows or the seqs are not gap-free from 1.
    Returns the number inserted.
    """
    if conn.execute(text("SELECT 1 FROM events LIMIT 1")).first() is not None:
        raise RestoreError("the events table is not empty; restore only into an empty database")
    stream = _gap_free(events)
    total = 0
    while batch := list(islice(stream, BATCH)):
        conn.execute(_INSERT, [_params(event) for event in batch])
        total += len(batch)
    return total
