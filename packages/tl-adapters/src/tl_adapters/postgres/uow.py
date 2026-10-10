"""Postgres unit of work: ledger append and inline projectors in one transaction, then bus publish.

Runs the projector registry exactly like the SQLite unit of work (fanout contract C2): the same
``Projector.apply(conn, event)`` calls, in ``seq`` order, inside the write transaction, then an
ordered bus publish after commit. ``target`` is a ``postgresql://`` URL; use
``tl_adapters.postgres.schema_url`` to point a URL at one schema for isolation.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from typing import cast

from sqlalchemy import Engine
from tl_core.bus import Bus
from tl_core.projection.defaults import default_registry
from tl_core.projection.registry import InMemoryRegistry
from tl_core.projection.types import ProjectorRegistry

from tl_adapters._unit import BaseUnitOfWork, create_projection_tables, replay
from tl_adapters.postgres.engine import make_engine, read_tx, write_tx
from tl_adapters.postgres.ledger import PostgresLedger

__all__ = ["PostgresUnitOfWork", "create_schema", "open_uow", "rebuild_projections"]


class PostgresUnitOfWork(BaseUnitOfWork):
    """One transaction. ``readonly=True`` opens a read snapshot and refuses ``append``."""

    def __init__(
        self,
        engine: Engine,
        ledger: PostgresLedger,
        registry: ProjectorRegistry,
        bus: Bus | None = None,
        *,
        readonly: bool = False,
    ) -> None:
        super().__init__(
            ledger,
            registry,
            bus,
            (lambda: read_tx(engine)) if readonly else (lambda: write_tx(engine)),
            readonly=readonly,
        )

    @property
    def ledger(self) -> PostgresLedger:
        return cast(PostgresLedger, self._ledger)


@contextmanager
def open_uow(
    url: str,
    *,
    readonly: bool = False,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> Generator[PostgresUnitOfWork]:
    """Open the database at ``url`` and yield an entered unit of work.

    The block is one transaction (commit on normal exit, rollback on exception). The engine is
    disposed afterwards.
    """
    engine = make_engine(url)
    try:
        uow = PostgresUnitOfWork(
            engine,
            PostgresLedger(engine),
            registry if registry is not None else default_registry(),
            bus,
            readonly=readonly,
        )
        with uow:
            yield uow
    finally:
        engine.dispose()


def create_schema(url: str, *, registry: ProjectorRegistry | None = None) -> None:
    """Create the events table and every registered projector's tables. Idempotent."""
    reg = registry if registry is not None else default_registry()
    engine = make_engine(url)
    try:
        PostgresLedger(engine).create_schema()
        with write_tx(engine) as conn:
            create_projection_tables(conn, reg, "postgres")
    finally:
        engine.dispose()


def rebuild_projections(
    url: str,
    *,
    types: Sequence[str] | None = None,
    registry: ProjectorRegistry | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Reset projectors and replay the whole ledger into them, in one transaction.

    ``types`` names projectors (default: all). Returns the number of events replayed. If the replay
    fails nothing changes: the transaction rolls back and the old rows remain.
    """
    reg = registry if registry is not None else default_registry()
    if types is None:
        selected = list(reg.all())
    elif isinstance(reg, InMemoryRegistry):
        selected = reg.named(types)
    else:
        selected = [p for p in reg.all() if p.name in set(types)]
    engine = make_engine(url)
    try:
        with write_tx(engine) as conn:
            return replay(conn, PostgresLedger(engine), reg, selected, on_progress)
    finally:
        engine.dispose()
