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

    Handlers rely on that: they raise to refuse a command, and the numbering allocator relies on it
    to stay gap-free (a number is allocated inside the same transaction as its record). Code that
    catches an exception *inside* the ``with`` block and carries on commits what was written so
    far, including an allocated number whose record never got written. Let the exception leave
    the block.
    """

    @property
    def ledger(self) -> Ledger:
        """The ledger this transaction appends to (read-only, so adapters may narrow its type)."""
        ...

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
