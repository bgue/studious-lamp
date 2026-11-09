"""The hold rule (P2-I5 S4b, D9): a blocking constraint raised on an Issued IWP puts it On hold.

``HoldFollower`` reads ``outbox_events`` after its own cursor (``rule_cursor`` row ``awp.hold``),
like ``follow.Follower``, and acts on ``Constraint.Raised`` only. It reads no payload key: the
constraint id is the event's stream, and the subject, phase and severity are re-read from
``cur_core_constraint`` when the event is applied, in the hold's own unit of work. The blocking
predicate is the one the guard counts (``guard.open_blocking``), so a constraint cleared or
withdrawn before the follower runs holds nothing. Only an Issued IWP moves (``hold_by_module``);
a replay finds On hold and writes nothing. The hold never raises a constraint, so it cannot loop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Final

from sqlalchemy import Connection, text
from tl_core.constraints.commands import EV_RAISED
from tl_core.constraints.guard import open_blocking
from tl_core.uow import UnitOfWork
from tl_core.webhooks.rows import OUTBOX_COLUMNS, OutboxRow

from tl_mod_awp.common import has_table
from tl_mod_awp.handlers.signoff import hold_by_module

log = logging.getLogger(__name__)

CURSOR_NAME: Final = "awp.hold"
CURSOR_TABLE: Final = "rule_cursor"
BATCH: Final = 100
POISON_AFTER: Final = 3
REASON_PREFIX: Final = "blocking constraint raised: "
_HEAD = text("SELECT COALESCE(MAX(seq), 0) FROM outbox_events")
_READ = text(f"SELECT {OUTBOX_COLUMNS} FROM outbox_events WHERE seq > :after ORDER BY seq LIMIT :n")
_GET = text(f"SELECT last_seq FROM {CURSOR_TABLE} WHERE name = :n")
_PUT = text(f"UPDATE {CURSOR_TABLE} SET last_seq = :seq WHERE name = :n AND last_seq < :seq")
_NEW = text(f"INSERT INTO {CURSOR_TABLE} (name, last_seq) VALUES (:n, :seq)")
_CONSTRAINT = text(
    "SELECT c.subject_id, c.phase, r.key FROM cur_core_constraint c "
    "JOIN cur_core_record r ON r.id = c.id WHERE c.id = :id AND r.voided = :no"
)


def apply_raised(uow: UnitOfWork, constraint_id: str) -> bool:
    """Hold the subject of an open blocking constraint when it is an Issued IWP."""
    conn = uow.conn()
    row = conn.execute(_CONSTRAINT, {"id": constraint_id, "no": False}).first()
    if row is None or row.key is None:
        return False
    if str(row.key) not in open_blocking(conn, str(row.subject_id), str(row.phase)):
        return False  # cleared, withdrawn or not blocking by now
    return hold_by_module(uow, str(row.subject_id), f"{REASON_PREFIX}{row.key}")


class HoldFollower:
    def __init__(
        self,
        open_uow: Callable[[], AbstractContextManager[UnitOfWork]],
        batch: int = BATCH,
    ) -> None:
        self._open = open_uow
        self._batch = batch
        self._seq: int | None = None
        self._failed: tuple[int, int] = (0, 0)  # (seq, consecutive failures)

    def _read(self, conn: Connection) -> int | None:
        if not has_table(conn, CURSOR_TABLE):
            return self._seq
        row = conn.execute(_GET, {"n": CURSOR_NAME}).first()
        return None if row is None else int(row.last_seq)

    def _write(self, conn: Connection, seq: int) -> None:
        if not has_table(conn, CURSOR_TABLE):
            return
        if conn.execute(_GET, {"n": CURSOR_NAME}).first() is None:
            conn.execute(_NEW, {"n": CURSOR_NAME, "seq": seq})
        else:
            conn.execute(_PUT, {"n": CURSOR_NAME, "seq": seq})

    def _start(self) -> None:
        with self._open() as uow:
            conn = uow.conn()
            position = self._read(conn)
            if position is None:  # a new follower starts at the head of the outbox
                position = int(conn.execute(_HEAD).scalar_one())
                self._write(conn, position)
        self._seq = position

    def poll(self) -> int:
        """Handle one batch of new events; the number of holds applied."""
        if self._seq is None:
            self._start()
        with self._open() as uow:
            rows = [
                OutboxRow.from_mapping(r)
                for r in uow.conn()
                .execute(_READ, {"after": self._seq, "n": self._batch})
                .mappings()
            ]
        held = 0
        for row in rows:
            try:
                with self._open() as uow:
                    if row.event_type == EV_RAISED and apply_raised(uow, row.stream_id):
                        held += 1
                    self._write(uow.conn(), row.seq)
                self._seq = row.seq  # the unit of work committed
            except Exception:
                seq, n = self._failed
                n = n + 1 if seq == row.seq else 1
                self._failed = (row.seq, n)
                log.exception("hold follower failed on seq %s (%s of %s)", row.seq, n, POISON_AFTER)
                if n >= POISON_AFTER:
                    try:
                        with self._open() as uow:
                            self._write(uow.conn(), row.seq)
                        self._seq = row.seq
                        self._failed = (0, 0)
                    except Exception:
                        log.exception("hold follower could not skip seq %s", row.seq)
                break  # the cursor stays; the next poll retries
        return held


__all__ = ["BATCH", "CURSOR_NAME", "HoldFollower", "apply_raised"]
