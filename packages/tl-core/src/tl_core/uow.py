"""The unit-of-work contract (build spec 03 section 7)."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol

from sqlalchemy import Connection

from tl_core.ledger import AppendResult, Ledger


class UnitOfWork(Protocol):
    """One transaction: ledger append plus inline projectors, then bus publish after commit.

    Used as a context manager. Leaving the block normally commits and then publishes the appended
    events on the bus; leaving it with an exception rolls back, so neither events nor projection
    rows survive and nothing is published.
    """

    ledger: Ledger

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def append(self, **kwargs: Any) -> AppendResult:
        """Same keyword arguments as ``Ledger.append``; also runs the registered projectors."""
        ...

    def conn(self) -> Connection:
        """The transaction's connection, for projection reads and writes (read-your-writes)."""
        ...
