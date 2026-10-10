"""Pick the adapter from the database target, so callers and tests are written once.

A target is a SQLite file path or a ``postgresql://`` URL. ``tl_core`` and the services see only
what these functions return; the dialect work stays in ``tl_adapters.sqlite`` and
``tl_adapters.postgres``. The parity suite runs the same test against both kinds of target.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine
from sqlalchemy.engine import make_url
from tl_core.bus import Bus
from tl_core.projection.types import ProjectorRegistry
from tl_core.util import new_ulid, utcnow

from tl_adapters import postgres, sqlite
from tl_adapters._unit import AppendInLedger, BaseUnitOfWork

DbTarget = str | Path
"""A SQLite ledger file, or a ``postgresql://`` URL (optionally scoped by ``schema_url``)."""


class LedgerWithSchema(AppendInLedger):
    """A ledger that can create its own tables."""

    def create_schema(self) -> None: ...


def is_postgres(target: DbTarget) -> bool:
    """True when ``target`` names a Postgres database."""
    return isinstance(target, str) and target.startswith(("postgresql://", "postgres://"))


def display_target(target: DbTarget) -> str:
    """``target`` as text that is safe to print: a Postgres URL without its password."""
    if is_postgres(target):
        return make_url(str(target)).render_as_string(hide_password=True)
    return str(target)


def dialect_of(target: DbTarget) -> str:
    """``"postgres"`` or ``"sqlite"``."""
    return "postgres" if is_postgres(target) else "sqlite"


def make_engine(target: DbTarget) -> Engine:
    """A SQLAlchemy engine for ``target``. The caller disposes it."""
    if is_postgres(target):
        return postgres.engine.make_engine(str(target))
    return sqlite.engine.make_engine(target)


def write_tx(engine: Engine) -> AbstractContextManager[Connection]:
    """One write transaction on an engine from :func:`make_engine`."""
    if engine.dialect.name == "postgresql":
        return postgres.engine.write_tx(engine)
    return sqlite.engine.write_tx(engine)


def read_tx(engine: Engine) -> AbstractContextManager[Connection]:
    """One read transaction (a consistent snapshot) on an engine from :func:`make_engine`."""
    if engine.dialect.name == "postgresql":
        return postgres.engine.read_tx(engine)
    return sqlite.engine.read_tx(engine)


def make_ledger(
    engine: Engine,
    *,
    clock: Callable[[], datetime] = utcnow,
    id_gen: Callable[[], str] = new_ulid,
) -> Any:
    """The ledger class for the engine's dialect (``SqliteLedger`` or ``PostgresLedger``)."""
    if engine.dialect.name == "postgresql":
        return postgres.ledger.PostgresLedger(engine, clock=clock, id_gen=id_gen)
    return sqlite.ledger.SqliteLedger(engine, clock=clock, id_gen=id_gen)


def open_uow(
    target: DbTarget,
    *,
    readonly: bool = False,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> AbstractContextManager[BaseUnitOfWork]:
    """Open ``target`` and yield an entered unit of work (one transaction)."""
    if is_postgres(target):
        return postgres.uow.open_uow(str(target), readonly=readonly, registry=registry, bus=bus)
    return sqlite.uow.open_uow(target, readonly=readonly, registry=registry, bus=bus)


def create_schema(target: DbTarget, *, registry: ProjectorRegistry | None = None) -> None:
    """Create the events table and every registered projector's tables. Idempotent."""
    if is_postgres(target):
        postgres.uow.create_schema(str(target), registry=registry)
    else:
        sqlite.uow.create_schema(target, registry=registry)


def rebuild_projections(
    target: DbTarget,
    *,
    types: Sequence[str] | None = None,
    registry: ProjectorRegistry | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Reset projectors and replay the whole ledger into them, in one transaction."""
    if is_postgres(target):
        return postgres.uow.rebuild_projections(
            str(target), types=types, registry=registry, on_progress=on_progress
        )
    return sqlite.uow.rebuild_projections(
        target, types=types, registry=registry, on_progress=on_progress
    )


def make_uow_factory(
    target: DbTarget,
    *,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> sqlite.factory.SqliteUowFactory | postgres.factory.PostgresUowFactory:
    """A long-lived unit-of-work factory for ``target`` (one engine, many short transactions).

    ``factory()`` opens a write unit of work and ``factory(readonly=True)`` a read snapshot on
    either adapter; ``dispose()`` ends it. Servers and workers (the webhook worker, the API) build
    one at start-up and pass it around.
    """
    if is_postgres(target):
        return postgres.factory.PostgresUowFactory(str(target), registry=registry, bus=bus)
    return sqlite.factory.SqliteUowFactory(target, registry=registry, bus=bus)
