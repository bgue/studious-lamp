"""A reusable unit-of-work factory for the SQLite adapter (one engine, many short transactions).

``open_uow`` builds and disposes an engine per call, which is fine for a command but wasteful for a
long-running worker that opens a transaction per delivery. ``SqliteUowFactory`` keeps one engine and
hands out units of work that share it; it satisfies ``tl_core.webhooks.base.UowFactory``.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from tl_core.bus import Bus
from tl_core.projection.defaults import default_registry
from tl_core.projection.types import ProjectorRegistry
from tl_core.uow import UnitOfWork

from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_adapters.sqlite.uow import SqliteUnitOfWork


class SqliteUowFactory:
    """``factory()`` opens a write unit of work, ``factory(readonly=True)`` a read snapshot.

    Use the result as a context manager. Call :meth:`dispose` when the process is done.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        registry: ProjectorRegistry | None = None,
        bus: Bus | None = None,
    ) -> None:
        self._engine = make_engine(path)
        self._ledger = SqliteLedger(self._engine)
        self._registry = registry if registry is not None else default_registry()
        self._bus = bus

    def __call__(self, *, readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return SqliteUnitOfWork(
            self._engine, self._ledger, self._registry, self._bus, readonly=readonly
        )

    def dispose(self) -> None:
        self._engine.dispose()
