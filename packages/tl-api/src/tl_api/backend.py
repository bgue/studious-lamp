"""The storage seam of the API (O5): a unit-of-work factory plus the ledger and bus behind it.

Routes never import an adapter. They call ``ctx.backend(readonly)`` and get an entered
``UnitOfWork``. ``open_backend`` builds the backend from a SQLite path or a ``postgresql://`` URL
(P1-I0 workstream B); ``create_app`` takes either unchanged.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from tl_adapters.db import DbTarget
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


def open_backend(target: DbTarget) -> Backend:
    """The backend for ``target``: a SQLite file path or a ``postgresql://`` URL.

    One engine and one in-process bus for the life of the process, whichever database it is. The
    caller closes it. See :func:`tl_adapters.backend.open_backend`.
    """
    from tl_adapters.backend import open_backend as open_database_backend

    return open_database_backend(target)
