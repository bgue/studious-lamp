"""Open the ledger for a sync: one read transaction that sees one consistent snapshot."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine
from tl_adapters.db import read_tx


@contextmanager
def read_snapshot(engine: Engine) -> Generator[Connection]:
    """A connection whose reads all see the ledger as of one instant.

    It is the adapter's own read transaction (``tl_adapters.db.read_tx``): a deferred transaction
    in WAL mode on SQLite, ``REPEATABLE READ READ ONLY`` on PostgreSQL. READ COMMITTED, the
    PostgreSQL default, would not do, because each statement would see the newest commits.
    ``tl_lake.sync`` reads the head, the events and the current-state rows through this one
    connection and relies on that.
    """
    with read_tx(engine) as conn:
        yield conn
