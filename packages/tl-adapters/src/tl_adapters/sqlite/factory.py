"""A long-lived SQLite unit-of-work factory for servers (P0-I4 workstream C).

``open_uow`` builds an engine for every unit of work, which suits a CLI call. A server opens one
transaction per request, so :class:`SqliteUowFactory` keeps one engine, one ledger and one bus for
the life of the process. It is callable with the same shape every server-side caller uses:

    factory(readonly) -> context manager that yields an entered UnitOfWork

The Postgres adapter (P0-I5) offers a factory with this call shape, so a server swaps adapters by
building a different factory and nothing else.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from sqlalchemy import Engine
from tl_core.bus import Bus, InProcessBus
from tl_core.projection.defaults import default_registry
from tl_core.projection.types import ProjectorRegistry
from tl_core.uow import UnitOfWork

from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_adapters.sqlite.uow import SqliteUnitOfWork


class SqliteUowFactory:
    """One engine and one bus; ``factory(readonly)`` opens a unit of work on them.

    Events committed through any unit of work from this factory are published on ``bus`` in commit
    order. Events written by another process reach subscribers through a change-feed poller on
    ``ledger``. ``close()`` (alias ``dispose()``) disposes the engine; call it at shutdown.
    ``readonly`` may be passed positionally or by keyword.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        bus: Bus | None = None,
        registry: ProjectorRegistry | None = None,
    ) -> None:
        self.path = Path(path)
        self.engine: Engine = make_engine(self.path)
        self.ledger = SqliteLedger(self.engine)
        self.bus: Bus = bus if bus is not None else InProcessBus()
        self._registry = registry if registry is not None else default_registry()

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return SqliteUnitOfWork(
            self.engine, self.ledger, self._registry, self.bus, readonly=readonly
        )

    def close(self) -> None:
        self.engine.dispose()

    def dispose(self) -> None:
        """Alias of :meth:`close` (the name P0-I5 callers use)."""
        self.close()
