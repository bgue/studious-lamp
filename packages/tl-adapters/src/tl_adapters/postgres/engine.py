"""Postgres engine factory and transaction helpers (pg8000 through SQLAlchemy).

Write transactions are serialised the way SQLite's ``BEGIN IMMEDIATE`` serialises them: the first
statement of every write transaction takes one transaction-scoped advisory lock (fanout decision
A3). That keeps commit order equal to ``seq`` order, so the seq cursor and the change feed's
dedupe stay correct (LEARNINGS L-P0-I4-A2), and every read inside a write transaction (workflow
guards, numbering counters) is safe from a concurrent writer (L-P0-I3-O2). Read transactions are
read-only snapshots (``REPEATABLE READ``) and never wait for the lock.

The driver is configured so rows look like SQLite's to ``tl_core``: JSON columns and timestamps
come back as canonical text (timestamps in the ``iso_utc`` form), booleans as 0/1 and sums of
integers as ints. Dialect differences stay in this package.

The driver is pg8000 (BSD-3-Clause); see ``docs/adr/0006-dependency-licences.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import URL, ExceptionContext, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from tl_core.ledger import iso_utc
from tl_core.services.errors import LockTimeoutError, RetryableTransactionError

WRITE_OPTION = "tl_write"
# The one lock every write transaction takes first. Any constant works; this is "tlledger".
LEDGER_LOCK_KEY = 0x746C6C6564676572
LOCK_TIMEOUT = "10s"
NOTIFY_CHANNEL = "tl_events"

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:key)")

# Postgres type OIDs (stable across versions).
_OID_BOOL = 16
_OID_JSON = 114
_OID_TIMESTAMPTZ = 1184
_OID_NUMERIC = 1700
_OID_JSONB = 3802


def _iso_timestamptz(value: str) -> str:
    """``timestamptz`` text (``2026-10-09 12:00:00.5+00``) as the canonical UTC ISO string."""
    return iso_utc(datetime.fromisoformat(value))


def _canonical_json(value: str) -> str:
    """``json``/``jsonb`` text as canonical compact text, like the text SQLite stores.

    JSONB re-renders its content (``{"a": 1}`` with spaces, keys ordered by length); callers that
    compare or hash the text expect the canonical form the projectors write on SQLite.
    """
    return json.dumps(json.loads(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _int_bool(value: str) -> int:
    """``boolean`` as 0 or 1, like SQLite."""
    return 1 if value == "t" else 0


def _number(value: str) -> int | float:
    """``numeric`` (what ``SUM`` of integers returns) as an int when whole, else a float."""
    number = Decimal(value)
    return int(number) if number == number.to_integral_value() else float(number)


_OPTION = re.compile(r"-c\s*([a-z_.]+)=(\S+)")


def sqlalchemy_url(url: str) -> str:
    """``postgresql://...`` as a SQLAlchemy URL for the pg8000 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+pg8000://" + url[len(prefix) :]
    return url


def split_url(url: str) -> tuple[URL, dict[str, Any]]:
    """The SQLAlchemy URL for ``url`` and the driver arguments it implies.

    A libpq-style ``?options=-csearch_path=<schema>`` (what ``admin.schema_url`` writes) becomes the
    startup parameter ``search_path``, because pg8000 does not read ``options``.
    """
    parsed = make_url(sqlalchemy_url(url))
    connect_args: dict[str, Any] = {}
    options = parsed.query.get("options")
    if options is not None:
        joined = options if isinstance(options, str) else " ".join(options)
        params = {key: value for key, value in _OPTION.findall(joined)}
        if params:
            connect_args["startup_params"] = params
        parsed = parsed.difference_update_query(["options"])
    return parsed, connect_args


def make_engine(url: str, *, pooled: bool = False) -> Engine:
    """An engine for the database at ``url`` (``postgresql://user:password@host:port/name``).

    One connection per use by default (``NullPool``), like the SQLite engine; ``pooled=True`` keeps
    a small pool for a long-running service. The caller disposes the engine.
    """
    parsed, connect_args = split_url(url)
    engine = (
        create_engine(
            parsed,
            connect_args=connect_args,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
        )
        if pooled
        else create_engine(parsed, connect_args=connect_args, poolclass=NullPool)
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        for oid in (_OID_JSON, _OID_JSONB):
            dbapi_connection.register_in_adapter(oid, _canonical_json)
        dbapi_connection.register_in_adapter(_OID_TIMESTAMPTZ, _iso_timestamptz)
        dbapi_connection.register_in_adapter(_OID_BOOL, _int_bool)
        dbapi_connection.register_in_adapter(_OID_NUMERIC, _number)

    @event.listens_for(engine, "handle_error")
    def _classify(context: ExceptionContext) -> Exception | None:
        # pg8000 raises IntegrityError only for a unique violation (23505); every other
        # constraint failure (class 23: not null, check, our append-only trigger) arrives as a
        # ProgrammingError. Report all of class 23 as IntegrityError, as SQLite does. A lock
        # timeout, a deadlock and a serialization failure become the named errors the services
        # and callers handle; nothing was written in any of those cases.
        original = context.original_exception
        code = _sqlstate(original)
        if code == "55P03":
            return LockTimeoutError("the ledger write lock was busy; retry")
        if code in ("40001", "40P01"):
            return RetryableTransactionError("the database rolled the transaction back; retry")
        if code is not None and code.startswith("23") and context.statement is not None:
            return IntegrityError(context.statement, context.parameters, original)
        return None

    return engine


def is_write_connection(conn: Connection) -> bool:
    """True when ``conn`` was opened by :func:`write_tx`."""
    return bool(conn.get_execution_options().get(WRITE_OPTION))


def take_ledger_lock(conn: Connection) -> None:
    """Take the transaction-scoped ledger lock (re-entrant within one transaction)."""
    conn.execute(_LOCK_SQL, {"key": LEDGER_LOCK_KEY})


def _sqlstate(error: BaseException) -> str | None:
    original: Any = getattr(error, "orig", error)
    args: tuple[Any, ...] = getattr(original, "args", ())
    info: Any = args[0] if args else None
    fields = cast(dict[str, Any], info) if isinstance(info, dict) else {}
    code: Any = fields.get("C")
    return code if isinstance(code, str) else None


@contextmanager
def write_tx(engine: Engine) -> Generator[Connection]:
    """One write transaction holding the ledger lock; rolls back on any exception.

    The transaction is ``READ COMMITTED`` whatever the server's ``default_transaction_isolation``
    says: under a stricter default the snapshot would be taken before the lock was granted and a
    waiting writer would read stale data. Waiting longer than ``LOCK_TIMEOUT`` for the lock raises
    ``LockTimeoutError`` (nothing was written; retry).
    """
    options: dict[str, Any] = {WRITE_OPTION: True, "isolation_level": "READ COMMITTED"}
    with engine.connect().execution_options(**options) as conn, conn.begin():
        conn.exec_driver_sql(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        take_ledger_lock(conn)  # a wait past LOCK_TIMEOUT raises LockTimeoutError (see _classify)
        yield conn


@contextmanager
def read_tx(engine: Engine) -> Generator[Connection]:
    """One read transaction: a read-only, consistent snapshot."""
    with engine.connect() as conn, conn.begin():
        conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        yield conn
