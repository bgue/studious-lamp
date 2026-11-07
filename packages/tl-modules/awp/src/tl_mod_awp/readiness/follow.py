"""The readiness follower: ``tl awp worker`` reads ``outbox_events`` after its own cursor and
hands each event to ``hooks.on_event`` in its own unit of work.

The cursor is a ``rule_cursor`` row named ``awp.readiness`` (that table is ``(name, last_seq)``);
when the table is absent the position is kept in memory. A new follower starts at the head of the
outbox and first queues an evaluation for the IWPs in Constraint check or Ready (bounded per
scope by ``hooks.FALLBACK_CAP``), so nothing before it started is missed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Final

from sqlalchemy import Connection, text
from tl_core.ledger import Event
from tl_core.uow import UnitOfWork
from tl_core.webhooks.rows import OUTBOX_COLUMNS, OutboxRow

from tl_mod_awp.common import has_table
from tl_mod_awp.names import IWP, IWP_CHECK, IWP_READY
from tl_mod_awp.readiness import hooks
from tl_mod_awp.readiness.engine import Checks, request

log = logging.getLogger(__name__)

CURSOR_NAME: Final = "awp.readiness"
CURSOR_TABLE: Final = "rule_cursor"
BATCH: Final = 100
POISON_AFTER: Final = 3
_HEAD = text("SELECT COALESCE(MAX(seq), 0) FROM outbox_events")
_READ = text(f"SELECT {OUTBOX_COLUMNS} FROM outbox_events WHERE seq > :after ORDER BY seq LIMIT :n")
_GET = text(f"SELECT last_seq FROM {CURSOR_TABLE} WHERE name = :n")
_PUT = text(f"UPDATE {CURSOR_TABLE} SET last_seq = :seq WHERE name = :n AND last_seq < :seq")
_NEW = text(f"INSERT INTO {CURSOR_TABLE} (name, last_seq) VALUES (:n, :seq)")
_SCOPES = text(
    "SELECT DISTINCT scope FROM cur_core_record WHERE type = :type AND voided = :no "
    "AND status IN (:check, :ready)"
)


def event_of(row: OutboxRow) -> Event:
    """The ledger ``Event`` shape ``on_event`` reads (ids and payload; no hash chain)."""
    return Event(
        event_type=row.event_type,
        schema_version=row.schema_version,
        payload=dict(row.data),
        seq=row.seq,
        event_id=row.event_id,
        stream_id=row.stream_id,
        stream_type=row.stream_type,
        stream_version=row.stream_version,
        scope=row.scope,
        actor=row.actor,
        recorded_at=row.recorded_at,  # type: ignore[arg-type]
        effective_at=row.recorded_at,  # type: ignore[arg-type]
        correlation_id=row.correlation_id,
        causation_id=None,
        source=row.source,
        prev_hash=None,
        hash="",
    )


class Follower:
    def __init__(
        self,
        open_uow: Callable[[], AbstractContextManager[UnitOfWork]],
        checks: Checks | None = None,
        batch: int = BATCH,
    ) -> None:
        self._open = open_uow
        self._checks = checks
        self._batch = batch
        self._seq: int | None = None
        self._failed: tuple[int, int] = (0, 0)  # (seq, consecutive failures)

    def _read(self, conn: Connection) -> int | None:
        if not has_table(conn, CURSOR_TABLE):
            return self._seq
        row = conn.execute(_GET, {"n": CURSOR_NAME}).first()
        return None if row is None else int(row.last_seq)

    def _write(self, conn: Connection, seq: int) -> None:
        """Store the cursor row; the in-memory position moves after the unit of work commits."""
        if not has_table(conn, CURSOR_TABLE):
            return
        if conn.execute(_GET, {"n": CURSOR_NAME}).first() is None:
            conn.execute(_NEW, {"n": CURSOR_NAME, "seq": seq})
        else:
            conn.execute(_PUT, {"n": CURSOR_NAME, "seq": seq})

    def _start(self) -> None:
        position: int | None = None
        with self._open() as uow:
            conn = uow.conn()
            if self._read(conn) is None:
                head = int(conn.execute(_HEAD).scalar_one())
                params = {"type": IWP, "no": False, "check": IWP_CHECK, "ready": IWP_READY}
                for scope in [str(r.scope) for r in conn.execute(_SCOPES, params)]:
                    request(uow, hooks.fallback_ids(conn, scope), reason="follower start")
                self._write(conn, head)
                position = head
            else:
                position = self._read(conn)
        self._seq = position

    def poll(self) -> int:
        """Handle one batch of new events; the number of evaluations queued."""
        if self._seq is None:
            self._start()
        with self._open() as uow:
            rows = [
                OutboxRow.from_mapping(r)
                for r in uow.conn()
                .execute(_READ, {"after": self._seq, "n": self._batch})
                .mappings()
            ]
        queued = 0
        for row in rows:
            try:
                with self._open() as uow:
                    queued += hooks.on_event(uow, event_of(row), self._checks)
                    self._write(uow.conn(), row.seq)
                self._seq = row.seq  # the unit of work committed
            except Exception:
                seq, n = self._failed
                n = n + 1 if seq == row.seq else 1
                self._failed = (row.seq, n)
                log.exception(
                    "readiness follower failed on seq %s (%s of %s)", row.seq, n, POISON_AFTER
                )
                if n >= POISON_AFTER:
                    try:
                        with self._open() as uow:
                            self._write(uow.conn(), row.seq)
                        self._seq = row.seq
                        self._failed = (0, 0)
                    except Exception:
                        log.exception("readiness follower could not skip seq %s", row.seq)
                break  # the cursor stays; the next poll retries (request is idempotent)
        return queued


__all__ = ["BATCH", "CURSOR_NAME", "Follower", "event_of"]
