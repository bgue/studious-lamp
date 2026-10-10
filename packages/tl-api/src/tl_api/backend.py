"""The storage seam of the API (O5): a unit-of-work factory plus the ledger and bus behind it.

Routes never import an adapter. They call ``ctx.backend(readonly)`` and get an entered
``UnitOfWork``. Phase 0 opens SQLite; the Postgres adapter (P0-I5) provides an object with the same
shape and ``create_app`` takes it unchanged.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from tl_core.bus import Bus
from tl_core.ledger import Ledger
from tl_core.uow import UnitOfWork


class Backend(Protocol):
    """Call it with ``readonly`` to get a context manager that yields an entered unit of work."""

    @property
    def ledger(self) -> Ledger:
        """Read access for the change feed (``fetch_changes``, the poller)."""
        ...

    @property
    def bus(self) -> Bus:
        """Where committed events are published inside this process."""
        ...

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...

    def close(self) -> None: ...


def open_sqlite_backend(path: str | Path) -> Backend:
    """The Phase 0 backend: one SQLite file, one engine, one in-process bus."""
    from tl_adapters.sqlite.factory import SqliteUowFactory

    return SqliteUowFactory(path)
