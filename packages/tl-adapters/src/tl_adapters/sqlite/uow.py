"""SQLite unit of work: ledger append, inline projectors, and bus publish in one transaction."""

from __future__ import annotations

from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

from sqlalchemy import Connection, Engine
from tl_core.bus import Bus
from tl_core.ledger import AppendResult, Event
from tl_core.projection.defaults import default_registry
from tl_core.projection.registry import InMemoryRegistry
from tl_core.projection.types import ProjectorRegistry

from tl_adapters.sqlite.engine import make_engine, read_tx, write_tx
from tl_adapters.sqlite.ledger import SqliteLedger

REPLAY_PAGE = 1000


class SqliteUnitOfWork:
    """One transaction. ``readonly=True`` opens a read snapshot and refuses ``append``."""

    def __init__(
        self,
        engine: Engine,
        ledger: SqliteLedger,
        registry: ProjectorRegistry,
        bus: Bus | None = None,
        *,
        readonly: bool = False,
    ) -> None:
        self.ledger = ledger
        self._engine = engine
        self._registry = registry
        self._bus = bus
        self._readonly = readonly
        self._tx: AbstractContextManager[Connection] | None = None
        self._conn: Connection | None = None
        self._pending: list[Event] = []

    def __enter__(self) -> SqliteUnitOfWork:
        if self._tx is not None:
            raise RuntimeError("unit of work is already open")
        self._tx = read_tx(self._engine) if self._readonly else write_tx(self._engine)
        self._conn = self._tx.__enter__()
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
        tx.__exit__(exc_type, exc, tb)  # commits when exc_type is None, otherwise rolls back
        if exc_type is None and pending and self._bus is not None:
            self._bus.publish(pending)

    def append(self, **kwargs: Any) -> AppendResult:
        if self._readonly:
            raise RuntimeError("read-only unit of work cannot append")
        conn = self.conn()
        result = self.ledger.append_in(conn, **kwargs)
        for event in result.events:
            for projector in self._registry.for_event(event.event_type):
                projector.apply(conn, event)
        self._pending.extend(result.events)
        return result

    def conn(self) -> Connection:
        if self._conn is None:
            raise RuntimeError("unit of work is not open; use it as a context manager")
        return self._conn


def _default_registry() -> InMemoryRegistry:
    return default_registry()


@contextmanager
def open_uow(
    path: str | Path,
    *,
    readonly: bool = False,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> Generator[SqliteUnitOfWork]:
    """Open the ledger file at ``path`` and yield an entered unit of work.

    The block is one transaction (commit on normal exit, rollback on exception). The engine is
    disposed afterwards.
    """
    engine = make_engine(path)
    try:
        ledger = SqliteLedger(engine)
        uow = SqliteUnitOfWork(
            engine,
            ledger,
            registry if registry is not None else _default_registry(),
            bus,
            readonly=readonly,
        )
        with uow:
            yield uow
    finally:
        engine.dispose()


def create_schema(path: str | Path, *, registry: ProjectorRegistry | None = None) -> None:
    """Create the events table and every registered projector's tables. Idempotent."""
    reg = registry if registry is not None else _default_registry()
    engine = make_engine(path)
    try:
        SqliteLedger(engine).create_schema()
        with write_tx(engine) as conn:
            for projector in reg.all():
                for statement in projector.ddl("sqlite"):
                    conn.exec_driver_sql(statement)
    finally:
        engine.dispose()


def rebuild_projections(
    path: str | Path,
    *,
    types: Sequence[str] | None = None,
    registry: ProjectorRegistry | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Reset projectors and replay the whole ledger into them, in one transaction.

    ``types`` names projectors (default: all). Returns the number of events replayed. If the replay
    fails nothing changes: the transaction rolls back and the old rows remain.
    """
    reg = registry if registry is not None else _default_registry()
    if types is None:
        selected = list(reg.all())
    elif isinstance(reg, InMemoryRegistry):
        selected = reg.named(types)
    else:
        selected = [p for p in reg.all() if p.name in set(types)]
    names = {p.name for p in selected}
    engine = make_engine(path)
    replayed = 0
    try:
        ledger = SqliteLedger(engine)
        with write_tx(engine) as conn:
            for projector in selected:
                projector.reset(conn)
            cursor = 0
            while True:
                page = ledger.read_after(cursor, limit=REPLAY_PAGE)
                if not page:
                    break
                for event in page:
                    for projector in reg.for_event(event.event_type):
                        if projector.name in names:
                            projector.apply(conn, event)
                replayed += len(page)
                cursor = page[-1].seq
                if on_progress is not None:
                    on_progress(replayed)
    finally:
        engine.dispose()
    return replayed
