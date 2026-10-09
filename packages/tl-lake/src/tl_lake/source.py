"""Open the ledger for a sync: one read transaction that sees one consistent snapshot."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine


@contextmanager
def read_snapshot(engine: Engine) -> Generator[Connection]:
    """A connection whose reads all see the ledger as of one instant.

    SQLite: a deferred read transaction in WAL mode is a snapshot from its first read. PostgreSQL:
    ``REPEATABLE READ`` is, and READ COMMITTED (the default) is not, because each statement sees
    the newest commits. ``tl_lake.sync`` reads the head, the events and the current-state rows
    through this one connection and relies on that.
    """
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn = conn.execution_options(isolation_level="REPEATABLE READ")
        with conn.begin():
            yield conn
