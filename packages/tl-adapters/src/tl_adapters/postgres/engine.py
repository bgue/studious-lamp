"""Postgres engine factory and transaction helpers (psycopg 3 through SQLAlchemy).

Write transactions are serialised the way SQLite's ``BEGIN IMMEDIATE`` serialises them: the first
statement of every write transaction takes one transaction-scoped advisory lock (fanout decision
A3). That keeps commit order equal to ``seq`` order, so the seq cursor and the change feed's
dedupe stay correct (LEARNINGS L-P0-I4-A2), and every read inside a write transaction (workflow
guards, numbering counters) is safe from a concurrent writer (L-P0-I3-O2). Read transactions are
read-only snapshots (``REPEATABLE READ``) and never wait for the lock.

The driver is configured so rows look like SQLite's to ``tl_core``: JSON columns and timestamps
come back as canonical text (timestamps in the ``iso_utc`` form), booleans as 0/1 and sums of
integers as ints. Dialect differences stay in this package.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from psycopg import adapt
from psycopg.abc import AdaptContext
from psycopg.postgres import types as pg_types
from psycopg.types.datetime import TimestamptzLoader
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.pool import NullPool
from tl_core.ledger import iso_utc

WRITE_OPTION = "tl_write"
# The one lock every write transaction takes first. Any constant works; this is "tlledger".
LEDGER_LOCK_KEY = 0x746C6C6564676572
LOCK_TIMEOUT = "10s"
NOTIFY_CHANNEL = "tl_events"

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:key)")


class _IsoTimestamptzLoader(adapt.Loader):
    """``timestamptz`` as the canonical UTC ISO string, like the strings SQLite stores."""

    def __init__(self, oid: int, context: AdaptContext | None = None) -> None:
        super().__init__(oid, context)
        self._inner = TimestamptzLoader(oid, context)

    def load(self, data: Any) -> str:
        return iso_utc(self._inner.load(data))


class _CanonicalJsonLoader(adapt.Loader):
    """``json`` and ``jsonb`` as canonical compact text, like the text SQLite stores.

    JSONB re-renders its content (``{"a": 1}`` with spaces, keys ordered by length); callers that
    compare or hash the text expect the canonical form the projectors write on SQLite.
    """

    def load(self, data: Any) -> str:
        return json.dumps(
            json.loads(bytes(data)), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


class _IntBoolLoader(adapt.Loader):
    """``boolean`` as 0 or 1, like SQLite."""

    def load(self, data: Any) -> int:
        return 1 if bytes(data) == b"t" else 0


class _NumericLoader(adapt.Loader):
    """``numeric`` (what ``SUM`` of integers returns) as an int when whole, else a float."""

    def load(self, data: Any) -> int | float:
        value = Decimal(bytes(data).decode("ascii"))
        return int(value) if value == value.to_integral_value() else float(value)


def sqlalchemy_url(url: str) -> str:
    """``postgresql://...`` as a SQLAlchemy URL for the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def make_engine(url: str, *, pooled: bool = False) -> Engine:
    """An engine for the database at ``url`` (``postgresql://user:password@host:port/name``).

    One connection per use by default (``NullPool``), like the SQLite engine; ``pooled=True`` keeps
    a small pool for a long-running service. The caller disposes the engine.
    """
    engine = (
        create_engine(sqlalchemy_url(url), pool_size=5, max_overflow=5, pool_pre_ping=True)
        if pooled
        else create_engine(sqlalchemy_url(url), poolclass=NullPool)
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        adapters = dbapi_connection.adapters
        for name in ("json", "jsonb"):
            adapters.register_loader(pg_types[name].oid, _CanonicalJsonLoader)
        adapters.register_loader(pg_types["timestamptz"].oid, _IsoTimestamptzLoader)
        adapters.register_loader(pg_types["bool"].oid, _IntBoolLoader)
        adapters.register_loader(pg_types["numeric"].oid, _NumericLoader)

    return engine


def is_write_connection(conn: Connection) -> bool:
    """True when ``conn`` was opened by :func:`write_tx`."""
    return bool(conn.get_execution_options().get(WRITE_OPTION))


def take_ledger_lock(conn: Connection) -> None:
    """Take the transaction-scoped ledger lock (re-entrant within one transaction)."""
    conn.execute(_LOCK_SQL, {"key": LEDGER_LOCK_KEY})


@contextmanager
def write_tx(engine: Engine) -> Generator[Connection]:
    """One write transaction holding the ledger lock; rolls back on any exception."""
    with engine.connect().execution_options(**{WRITE_OPTION: True}) as conn, conn.begin():
        conn.exec_driver_sql(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        take_ledger_lock(conn)
        yield conn


@contextmanager
def read_tx(engine: Engine) -> Generator[Connection]:
    """One read transaction: a read-only, consistent snapshot."""
    with (
        engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as conn,
        conn.begin(),
    ):
        yield conn
