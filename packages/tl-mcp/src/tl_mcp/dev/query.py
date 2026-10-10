"""Run one guarded SELECT against the dev database, read-only, with limits (``query_db``).

Layers, in order: the SQL guard (:mod:`tl_mcp.dev.sqlguard`); a read-only connection; and the
database's own enforcement.

* SQLite: the file is opened ``mode=ro`` with ``PRAGMA query_only``, and an authoriser allows only
  SELECT, reads of non-secret columns, recursion, and functions outside a short deny-list;
  statement length, string length and compound-select size are capped; a progress handler stops a
  statement after the timeout.
* Postgres: one transaction that is ``READ ONLY`` with ``statement_timeout`` and ``lock_timeout``
  set locally; the transaction is always rolled back.

Rows, bytes and time are limited. Error text is short and carries no absolute path.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as dtime
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from tl_mcp.dev import sqlguard
from tl_mcp.dev.errors import DevGuardError, DevToolFailure
from tl_mcp.dev.guard import DevTarget

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MAX_RESULT_BYTES = 1024 * 1024
TIMEOUT_S = 10.0
ERROR_TEXT_CHARS = 200
_ABSOLUTE_PATH = re.compile(r"(?<![\w>])(?:/[^/\s'\"]+){2,}/?")

_SQLITE_DENIED_FUNCTIONS = frozenset(
    {"load_extension", "fts3_tokenizer", "readfile", "writefile", "edit", "zipfile"}
)
_SQLITE_DENIED_COLUMNS = frozenset({("wh_secret", "secret")})
_SQLITE_RAW_TABLES = frozenset({"sqlite_dbpage", "dbstat"})
"""Virtual tables that expose raw database pages, secret rows included."""
_SQLITE_LIMIT_LENGTH = 1_000_000
_SQLITE_LIMIT_COMPOUND = 20
_SQLITE_LIMIT_SQL = 20_000


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    truncated_by: str | None
    limit: int
    dialect: str
    elapsed_ms: float


class QueryFailed(DevToolFailure):
    """The statement passed the guard but failed or ran too long (short text, no paths)."""


def jsonable(value: Any) -> Any:
    """``value`` as something ``json.dumps`` accepts."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else str(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return str(value)


def clean_error(exc: BaseException) -> str:
    """A short, path-free sentence for a failed statement."""
    text = _ABSOLUTE_PATH.sub("<path>", str(exc)).strip().splitlines()[0:1]
    message = text[0] if text else type(exc).__name__
    return f"{type(exc).__name__}: {message}"[:ERROR_TEXT_CHARS]


def _collect(
    columns: list[str], fetch: Any, limit: int, started: float, dialect: str
) -> QueryResult:
    rows: list[list[Any]] = []
    size = 2
    truncated_by: str | None = None
    for raw in fetch(limit + 1):
        if len(rows) >= limit:
            truncated_by = "limit"
            break
        row = [jsonable(v) for v in raw]
        size += len(json.dumps(row, ensure_ascii=False)) + 1
        if size > MAX_RESULT_BYTES:
            truncated_by = "bytes"
            break
        rows.append(row)
    return QueryResult(
        columns=columns,
        rows=rows,
        truncated=truncated_by is not None,
        truncated_by=truncated_by,
        limit=limit,
        dialect=dialect,
        elapsed_ms=round((time.monotonic() - started) * 1000, 1),
    )


def _authorizer(action: int, arg1: str | None, arg2: str | None, *_: Any) -> int:
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        table = (arg1 or "").lower()
        if (table, (arg2 or "").lower()) in _SQLITE_DENIED_COLUMNS:
            return sqlite3.SQLITE_DENY
        if table in sqlguard.DENIED_TABLES or table in _SQLITE_RAW_TABLES:
            return sqlite3.SQLITE_DENY
        if table.startswith("pragma_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        if (arg2 or "").lower() in _SQLITE_DENIED_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_sqlite(path: str, sql: str, limit: int) -> QueryResult:
    started = time.monotonic()
    uri = f"file:{quote(path, safe='/')}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=2.0, isolation_level=None)
    except sqlite3.Error as exc:
        raise QueryFailed(f"cannot open the dev database: {clean_error(exc)}") from exc
    try:
        if hasattr(con, "enable_load_extension"):
            con.enable_load_extension(False)
        con.execute("PRAGMA query_only = ON")
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, _SQLITE_LIMIT_LENGTH)
        con.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, _SQLITE_LIMIT_COMPOUND)
        con.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, _SQLITE_LIMIT_SQL)
        deadline = started + TIMEOUT_S
        con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        con.set_authorizer(_authorizer)
        try:
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description or []]
            return _collect(columns, cursor.fetchmany, limit, started, "sqlite")
        except sqlite3.ProgrammingError as exc:  # "You can only execute one statement at a time."
            if "one statement" in str(exc):
                raise DevGuardError("exactly one statement is allowed") from exc
            raise QueryFailed(clean_error(exc)) from exc
        except sqlite3.DatabaseError as exc:
            if "not authorized" in str(exc) or "prohibited" in str(exc):
                raise DevGuardError(
                    "refused: the statement uses something the read-only authoriser denies"
                ) from exc
            if "interrupted" in str(exc):
                raise QueryFailed(f"the statement ran longer than {TIMEOUT_S:.0f} s") from exc
            raise QueryFailed(clean_error(exc)) from exc
    finally:
        con.close()


def run_postgres(url: str, sql: str, limit: int) -> QueryResult:
    """Run ``sql`` through a server-side cursor and fetch at most ``limit + 1`` rows.

    A cursor keeps a ``SELECT`` that would return millions of rows from being loaded into this
    process: the server sends only what is fetched. ``DECLARE ... CURSOR FOR`` accepts exactly one
    ``SELECT`` or ``VALUES`` query, which is one more check on the statement.
    """
    from sqlalchemy.exc import DBAPIError, SQLAlchemyError
    from tl_adapters.db import make_engine, read_tx

    started = time.monotonic()
    statement = sql.strip().rstrip(";").rstrip()
    engine = make_engine(url)
    try:
        # A READ ONLY snapshot transaction; nothing in it can write, whatever the statement says.
        with read_tx(engine) as conn:
            conn.exec_driver_sql(f"SET LOCAL statement_timeout = '{int(TIMEOUT_S * 1000)}ms'")
            conn.exec_driver_sql("SET LOCAL lock_timeout = '2s'")
            conn.exec_driver_sql(f"DECLARE tl_dev_query NO SCROLL CURSOR FOR {statement}")
            result = conn.exec_driver_sql(f"FETCH FORWARD {limit + 1} FROM tl_dev_query")
            columns = [str(k) for k in result.keys()]
            return _collect(columns, result.fetchmany, limit, started, "postgres")
    except DBAPIError as exc:
        raise QueryFailed(clean_error(exc.orig or exc)) from exc
    except SQLAlchemyError as exc:
        raise QueryFailed(clean_error(exc)) from exc
    finally:
        engine.dispose()


def run_query(target: DevTarget, sql: str, limit: int = DEFAULT_LIMIT) -> QueryResult:
    """Guard, then run, ``sql`` on ``target``; raises :class:`DevGuardError` or ``QueryFailed``."""
    if not 1 <= limit <= MAX_LIMIT:
        raise DevGuardError(f"limit must be between 1 and {MAX_LIMIT}")
    sqlguard.check_select(sql, target.dialect)
    if target.kind == "sqlite":
        assert target.path is not None
        if not target.path.is_file():
            raise QueryFailed("the dev database does not exist yet: run `tl init` or the seed tool")
        return run_sqlite(str(target.path), sql, limit)
    assert target.url is not None
    return run_postgres(target.url, sql, limit)
