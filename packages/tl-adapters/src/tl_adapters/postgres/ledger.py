"""Postgres implementation of the ``Ledger`` Protocol (brief 5.1, 5.2, 14).

Same behaviour as ``SqliteLedger``: optimistic concurrency per stream, a hash chain per scope
that is byte-identical for the same events, and an append-only table. Every append runs inside a
write transaction that already holds the ledger lock (``engine.write_tx``), so no other
transaction can commit between reading the scope's last hash and inserting. An append also sends
``NOTIFY`` on ``tl_events`` with ``<schema>:<last seq>`` (delivered at commit) so pollers can wake
early; cursor reads stay authoritative.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping
from tl_core.ledger import (
    AppendResult,
    ConcurrencyError,
    Event,
    NewEvent,
    canonical_json,
    event_hash,
    iso_utc,
)
from tl_core.util import new_ulid, utcnow

from tl_adapters.postgres.ddl import EVENTS_DDL
from tl_adapters.postgres.engine import (
    NOTIFY_CHANNEL,
    is_write_connection,
    read_tx,
    take_ledger_lock,
    write_tx,
)

_INSERT_EVENT = text(
    """
    INSERT INTO events (
      seq, event_id, stream_id, stream_type, stream_version, event_type, schema_version, scope,
      payload, actor, recorded_at, effective_at, correlation_id, causation_id, source,
      prev_hash, hash
    ) VALUES (
      :seq, :event_id, :stream_id, :stream_type, :stream_version, :event_type, :schema_version,
      :scope,
      :payload, :actor, :recorded_at, :effective_at, :correlation_id, :causation_id, :source,
      :prev_hash, :hash
    )
    """
)


def _moment(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _row_to_event(row: RowMapping) -> Event:
    return Event(
        event_type=row["event_type"],
        schema_version=row["schema_version"],
        payload=json.loads(row["payload"]),
        seq=row["seq"],
        event_id=row["event_id"],
        stream_id=row["stream_id"],
        stream_type=row["stream_type"],
        stream_version=row["stream_version"],
        scope=row["scope"],
        actor=row["actor"],
        recorded_at=_moment(row["recorded_at"]),
        effective_at=_moment(row["effective_at"]),
        correlation_id=row["correlation_id"],
        causation_id=row["causation_id"],
        source=row["source"],
        prev_hash=row["prev_hash"],
        hash=row["hash"],
    )


class PostgresLedger:
    """Append-only event ledger in one Postgres schema; ``ddl.py`` holds the table and triggers."""

    def __init__(
        self,
        engine: Engine,
        *,
        clock: Callable[[], datetime] = utcnow,
        id_gen: Callable[[], str] = new_ulid,
    ) -> None:
        self._engine = engine
        self._clock = clock
        self._id_gen = id_gen

    def create_schema(self) -> None:
        """Create the events table, index, and append-only triggers. Idempotent."""
        with write_tx(self._engine) as conn:
            for statement in EVENTS_DDL:
                conn.exec_driver_sql(statement)

    def append(
        self,
        *,
        stream_id: str,
        stream_type: str,
        scope: str,
        expected_version: int,
        events: Sequence[NewEvent],
        actor: str,
        source: str,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> AppendResult:
        with write_tx(self._engine) as conn:
            return self.append_in(
                conn,
                stream_id=stream_id,
                stream_type=stream_type,
                scope=scope,
                expected_version=expected_version,
                events=events,
                actor=actor,
                source=source,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )

    def append_in(
        self,
        conn: Connection,
        *,
        stream_id: str,
        stream_type: str,
        scope: str,
        expected_version: int,
        events: Sequence[NewEvent],
        actor: str,
        source: str,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> AppendResult:
        """Append inside the caller's write transaction (a connection from ``write_tx``)."""
        if not is_write_connection(conn):
            raise RuntimeError("append_in needs a connection from write_tx")
        if not events:
            raise ValueError("append_in needs at least one event")
        take_ledger_lock(conn)  # already held by write_tx; taking it again is free and explicit

        found: int = conn.execute(
            text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s"),
            {"s": stream_id},
        ).scalar_one()
        if found != expected_version:
            raise ConcurrencyError(
                f"stream {stream_id!r}: expected version {expected_version}, found {found}"
            )

        prev_hash: str | None = conn.execute(
            text("SELECT hash FROM events WHERE scope = :scope ORDER BY seq DESC LIMIT 1"),
            {"scope": scope},
        ).scalar_one_or_none()

        last_seq: int = conn.execute(text("SELECT COALESCE(MAX(seq), 0) FROM events")).scalar_one()
        version = found
        stored: list[Event] = []
        for new in events:
            version += 1
            event_id = self._id_gen()
            recorded_at = self._clock()
            effective_at = new.effective_at if new.effective_at is not None else recorded_at
            payload_json = canonical_json(new.payload)
            recorded_iso = iso_utc(recorded_at)
            current_hash = event_hash(
                prev_hash,
                event_id,
                stream_id,
                version,
                new.event_type,
                payload_json,
                recorded_iso,
            )
            last_seq += 1
            params: dict[str, Any] = {
                "seq": last_seq,
                "event_id": event_id,
                "stream_id": stream_id,
                "stream_type": stream_type,
                "stream_version": version,
                "event_type": new.event_type,
                "schema_version": new.schema_version,
                "scope": scope,
                "payload": payload_json,
                "actor": actor,
                "recorded_at": recorded_iso,
                "effective_at": iso_utc(effective_at),
                "correlation_id": correlation_id,
                "causation_id": causation_id,
                "source": source,
                "prev_hash": prev_hash,
                "hash": current_hash,
            }
            conn.execute(_INSERT_EVENT, params)
            stored.append(
                Event(
                    event_type=new.event_type,
                    schema_version=new.schema_version,
                    payload=json.loads(payload_json),
                    seq=last_seq,
                    event_id=event_id,
                    stream_id=stream_id,
                    stream_type=stream_type,
                    stream_version=version,
                    scope=scope,
                    actor=actor,
                    recorded_at=recorded_at,
                    effective_at=effective_at,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    source=source,
                    prev_hash=prev_hash,
                    hash=current_hash,
                )
            )
            prev_hash = current_hash

        conn.execute(
            text("SELECT pg_notify(:channel, current_schema() || ':' || :seq)"),
            {"channel": NOTIFY_CHANNEL, "seq": str(last_seq)},
        )
        return AppendResult(events=stored, new_version=version, last_seq=last_seq)

    def read_stream(self, stream_id: str, *, from_version: int = 1) -> list[Event]:
        with read_tx(self._engine) as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM events WHERE stream_id = :s AND stream_version >= :v "
                        "ORDER BY stream_version"
                    ),
                    {"s": stream_id, "v": from_version},
                )
                .mappings()
                .all()
            )
            return [_row_to_event(row) for row in rows]

    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]:
        with read_tx(self._engine) as conn:
            if scope is None:
                rows = (
                    conn.execute(
                        text("SELECT * FROM events WHERE seq > :seq ORDER BY seq LIMIT :limit"),
                        {"seq": seq, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
            else:
                rows = (
                    conn.execute(
                        text(
                            "SELECT * FROM events WHERE seq > :seq AND scope = :scope "
                            "ORDER BY seq LIMIT :limit"
                        ),
                        {"seq": seq, "scope": scope, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
            return [_row_to_event(row) for row in rows]

    def head_seq(self) -> int:
        with read_tx(self._engine) as conn:
            head: int = conn.execute(text("SELECT COALESCE(MAX(seq), 0) FROM events")).scalar_one()
            return head

    def stream_version(self, stream_id: str) -> int:
        with read_tx(self._engine) as conn:
            version: int = conn.execute(
                text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s"),
                {"s": stream_id},
            ).scalar_one()
            return version
