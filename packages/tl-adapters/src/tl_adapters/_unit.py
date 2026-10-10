"""The unit of work both adapters share: one transaction of ledger append plus inline projectors.

An adapter supplies a ledger that can append inside a caller's connection and a factory for the
transaction context (``write_tx`` / ``read_tx`` of its engine). Everything else is dialect-neutral.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Protocol, Self

from sqlalchemy import Connection
from tl_core.bus import Bus
from tl_core.ledger import AppendResult, Event, Ledger, NewEvent
from tl_core.projection.types import Projector, ProjectorRegistry

from tl_adapters._publish import COMMIT_LOCK, publisher_for

REPLAY_PAGE = 1000

OpenTx = Callable[[], AbstractContextManager[Connection]]


class AppendInLedger(Ledger, Protocol):
    """A ledger that can append inside a connection the caller already opened for writing."""

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
    ) -> AppendResult: ...


class BaseUnitOfWork:
    """One transaction. ``readonly=True`` opens a read snapshot and refuses ``append``."""

    def __init__(
        self,
        ledger: AppendInLedger,
        registry: ProjectorRegistry,
        bus: Bus | None,
        open_tx: OpenTx,
        *,
        readonly: bool,
    ) -> None:
        self._ledger = ledger
        self._registry = registry
        self._bus = bus
        self._open_tx = open_tx
        self._readonly = readonly
        self._tx: AbstractContextManager[Connection] | None = None
        self._conn: Connection | None = None
        self._pending: list[Event] = []

    @property
    def ledger(self) -> AppendInLedger:
        """The ledger this transaction appends to (adapters narrow the type)."""
        return self._ledger

    def __enter__(self) -> Self:
        if self._tx is not None:
            raise RuntimeError("unit of work is already open")
        tx = self._open_tx()
        self._conn = tx.__enter__()  # if this raises (lock timeout), the unit stays reusable
        self._tx = tx
        self._pending = []
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        tx, self._tx, self._conn = self._tx, None, None
        pending, self._pending = self._pending, []
        assert tx is not None
        if exc_type is not None or not pending or self._bus is None:
            tx.__exit__(exc_type, exc, tb)  # rolls back on an exception, otherwise commits
            return
        publisher = publisher_for(self._bus)
        with COMMIT_LOCK:
            tx.__exit__(exc_type, exc, tb)  # commit; if it fails nothing is enqueued
            publisher.enqueue(pending)
        publisher.drain()

    def append(self, **kwargs: Any) -> AppendResult:
        if self._readonly:
            raise RuntimeError("read-only unit of work cannot append")
        conn = self.conn()
        result = self._ledger.append_in(conn, **kwargs)
        for event in result.events:
            for projector in self._registry.for_event(event.event_type):
                projector.apply(conn, event)
        self._pending.extend(result.events)
        return result

    def conn(self) -> Connection:
        if self._conn is None:
            raise RuntimeError("unit of work is not open; use it as a context manager")
        return self._conn


def create_projection_tables(conn: Connection, registry: ProjectorRegistry, dialect: str) -> None:
    """Run every registered projector's DDL for ``dialect`` on ``conn``."""
    for projector in registry.all():
        for statement in projector.ddl(dialect):
            conn.exec_driver_sql(statement)


def replay(
    conn: Connection,
    ledger: Ledger,
    registry: ProjectorRegistry,
    selected: Sequence[Projector],
    on_progress: Callable[[int], None] | None,
) -> int:
    """Reset the ``selected`` projectors on ``conn`` and replay the whole ledger into them."""
    names = {p.name for p in selected}
    for projector in selected:
        projector.reset(conn)
    replayed = 0
    cursor = 0
    while True:
        page = ledger.read_after(cursor, limit=REPLAY_PAGE)
        if not page:
            break
        for event in page:
            for projector in registry.for_event(event.event_type):
                if projector.name in names:
                    projector.apply(conn, event)
        replayed += len(page)
        cursor = page[-1].seq
        if on_progress is not None:
            on_progress(replayed)
    return replayed
