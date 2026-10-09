"""SQLite engine factory and transaction helpers.

pysqlite's legacy transaction handling interferes with an explicit ``BEGIN IMMEDIATE``, so the
driver runs in autocommit mode (``isolation_level = None``) and SQLAlchemy's ``begin`` event
issues the ``BEGIN``. Write transactions take the database write lock up front (``BEGIN
IMMEDIATE``), so the version check and the insert that follows cannot interleave with another
writer.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event

WRITE_OPTION = "tl_write"


def make_engine(path: str | Path) -> Engine:
    """An engine for the SQLite file at ``path``: WAL, foreign keys on, 5 s busy timeout."""
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        mode = "IMMEDIATE" if conn.get_execution_options().get(WRITE_OPTION) else "DEFERRED"
        conn.exec_driver_sql(f"BEGIN {mode}")

    return engine


def is_write_connection(conn: Connection) -> bool:
    """True when ``conn`` was opened by :func:`write_tx`."""
    return bool(conn.get_execution_options().get(WRITE_OPTION))


@contextmanager
def write_tx(engine: Engine) -> Generator[Connection]:
    """One write transaction (``BEGIN IMMEDIATE``); rolls back on any exception."""
    with engine.connect().execution_options(**{WRITE_OPTION: True}) as conn, conn.begin():
        yield conn


@contextmanager
def read_tx(engine: Engine) -> Generator[Connection]:
    """One read transaction (a consistent snapshot)."""
    with engine.connect() as conn, conn.begin():
        yield conn
