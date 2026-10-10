"""A reusable unit-of-work factory for the Postgres adapter (one pooled engine, many transactions).

Same call shape as ``tl_adapters.sqlite.factory.SqliteUowFactory`` (``factory()`` for a write unit
of work, ``factory(readonly=True)`` or positionally ``factory(True)`` for a read snapshot) so a
worker is written once and runs on either adapter. It runs the projector registry exactly like
``open_uow`` (fanout contract C2).
"""

from __future__ import annotations

from sqlalchemy import Engine
from tl_core.bus import Bus
from tl_core.projection.defaults import default_registry
from tl_core.projection.types import ProjectorRegistry

from tl_adapters.postgres.engine import make_engine
from tl_adapters.postgres.ledger import PostgresLedger
from tl_adapters.postgres.uow import PostgresUnitOfWork


class PostgresUowFactory:
    """``factory()`` opens a write unit of work, ``factory(readonly=True)`` a read snapshot.

    Use the result as a context manager. Call :meth:`dispose` when the process is done.
    """

    def __init__(
        self,
        url: str,
        *,
        registry: ProjectorRegistry | None = None,
        bus: Bus | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._engine = engine if engine is not None else make_engine(url, pooled=True)
        self._ledger = PostgresLedger(self._engine)
        self._registry = registry if registry is not None else default_registry()
        self._bus = bus

    def __call__(self, readonly: bool = False) -> PostgresUnitOfWork:
        return PostgresUnitOfWork(
            self._engine, self._ledger, self._registry, self._bus, readonly=readonly
        )

    def dispose(self) -> None:
        self._engine.dispose()
