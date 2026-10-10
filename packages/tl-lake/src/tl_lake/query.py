"""``lake_query``: read-only SQL over the lake with a row limit, a timeout and an audit trail.

Brief 11.3 and 28.4: "SQL with row limits, allowed catalogs only, logged". Three layers keep a
query from doing anything but read lake tables:

1. :mod:`tl_lake.guard` accepts one SELECT over lake tables and nothing else;
2. the catalog is attached READ_ONLY;
3. before the statement runs, external file access is switched off (only the lake's data
   directory stays readable) and the configuration is locked, so no setting can be changed back.

Every call, accepted or not, appends one JSON line to ``lake_query.log.jsonl`` in the lake
directory and writes a log record on the ``tl_lake.query`` logger. Every result states the ledger
``seq`` the lake reflected when the query ran.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from decimal import Decimal
from typing import Any
from uuid import UUID

import duckdb

from tl_lake.config import LakeConfig
from tl_lake.duck import Duck, ident, lake_tables, open_lake, sql_str
from tl_lake.errors import LakeError
from tl_lake.guard import MAX_SQL_CHARS, GuardError, check_sql
from tl_lake.status import as_of

log = logging.getLogger("tl_lake.query")
log.addHandler(logging.NullHandler())  # a library prints nothing until the application opts in

DEFAULT_LIMIT = 100
MAX_LIMIT = 10_000
TIMEOUT_S = 30.0
MEMORY_LIMIT = "1GB"
THREADS = 2


MAX_RESULT_BYTES = 8 * 1024 * 1024
"""Default cap on the JSON size of the rows one call returns."""
ERROR_TEXT_CHARS = 200
BATCH_ROWS = 256

_ABSOLUTE_PATH = re.compile(r"(?<![\w>])(?:/[^/\s'\"]+){2,}/?")


class QueryError(LakeError):
    """The statement passed the guard but failed or ran too long.

    ``error_class`` names the underlying exception type (for example ``ConversionException``).
    The message is short and carries no filesystem path.
    """

    def __init__(self, message: str, error_class: str = "QueryError") -> None:
        super().__init__(message)
        self.error_class = error_class


@dataclass(frozen=True)
class LakeQueryResult:
    """Rows are JSON-safe values. ``truncated`` means more rows existed than were returned.

    ``truncated_by`` says why: ``"limit"`` (more rows than ``limit``) or ``"bytes"`` (the result
    reached the byte cap, so fewer than ``limit`` rows are returned).
    """

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    limit: int
    as_of_seq: int
    snapshot_id: int | None
    elapsed_ms: float
    truncated_by: str | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def as_of_line(self) -> str:
        """The line reports print under a result (brief 28.3)."""
        snapshot = "no snapshot" if self.snapshot_id is None else f"snapshot {self.snapshot_id}"
        return f"as of seq {self.as_of_seq} ({snapshot})"


def jsonable(value: Any) -> Any:
    """``value`` as something ``json.dumps`` accepts."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else str(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, timedelta)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return str(value)


def _sandbox(con: Duck, config: LakeConfig) -> None:
    """Layer 3: no file access beyond the data directory, then freeze the settings."""
    con.execute(f"SET allowed_directories = [{sql_str(str(config.data_path) + '/')}]")
    con.execute("SET enable_external_access = false")
    con.execute(f"SET memory_limit = {sql_str(MEMORY_LIMIT)}")
    con.execute(f"SET threads = {THREADS}")
    con.execute("SET lock_configuration = true")


def _tz_safe(rel: Any) -> Any:
    """Cast zone-aware time columns to text: reading them in Python would need pytz."""
    kinds = [str(t) for t in rel.types]
    if not any("WITH TIME ZONE" in k for k in kinds):
        return rel
    view = "lake_query_result"
    items = [
        f"CAST({ident(c)} AS VARCHAR) AS {ident(c)}" if "WITH TIME ZONE" in k else ident(c)
        for c, k in zip(rel.columns, kinds, strict=True)
    ]
    return rel.query(view, f"SELECT {', '.join(items)} FROM {view}")


class LakeQueryService:
    """Runs guarded queries against one lake.

    ``timeout_s`` is best effort: the statement is interrupted when it expires, but DuckDB checks
    for interruption between chunks of work, so a single long scalar computation can overrun it.
    The memory limit (1 GB) and ``max_bytes`` bound the damage. ``max_bytes`` caps the JSON size
    of the returned rows; a result that reaches it comes back with ``truncated_by == "bytes"``.

    Time travel (``FROM events AT (VERSION => n)``) is allowed on purpose: reports are
    reproducible as of an earlier snapshot (brief 28.3).
    """

    def __init__(
        self,
        config: LakeConfig,
        *,
        default_limit: int = DEFAULT_LIMIT,
        max_limit: int = MAX_LIMIT,
        timeout_s: float = TIMEOUT_S,
        lock_timeout_s: float = 30.0,
        max_bytes: int = MAX_RESULT_BYTES,
    ) -> None:
        self.config = config
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.timeout_s = timeout_s
        self.lock_timeout_s = lock_timeout_s
        self.max_bytes = max_bytes

    def query(
        self, sql: str, *, limit: int | None = None, caller: str = "unknown"
    ) -> LakeQueryResult:
        """Run ``sql`` and return at most ``limit`` rows plus the as-of seq.

        Raises :class:`GuardError` when the statement is refused, :class:`QueryError` when it
        fails or times out, and :class:`LakeNotInitialisedError` when nothing was synced yet.
        Every call writes exactly one audit line, whatever it raises.
        """
        started = time.monotonic()
        wanted = self.default_limit if limit is None else limit
        entry: dict[str, Any] = {
            "caller": str(caller),
            "sql": _audited_sql(sql),
            "limit": wanted if isinstance(wanted, int) else repr(wanted)[:40],
            "outcome": "error",
            "detail": None,
            "error_class": None,
            "rows": 0,
            "truncated": False,
            "as_of_seq": None,
            "snapshot_id": None,
        }
        try:
            if not isinstance(sql, str):
                raise GuardError("the statement must be text")
            if isinstance(wanted, bool) or not isinstance(wanted, int):
                raise GuardError("limit must be an integer")
            if not 1 <= wanted <= self.max_limit:
                raise GuardError(f"limit must be between 1 and {self.max_limit}")
            result = self._run(sql, wanted, started, entry)
        except GuardError as exc:
            message = self._scrub(str(exc))
            self._record(entry, started, outcome="refused", detail=message)
            raise GuardError(message) from None
        except BaseException as exc:
            error_class = getattr(exc, "error_class", type(exc).__name__)
            self._record(
                entry,
                started,
                outcome="error",
                detail=self._scrub(str(exc))[:ERROR_TEXT_CHARS],
                error_class=error_class,
            )
            raise
        self._record(
            entry,
            started,
            outcome="ok",
            rows=result.row_count,
            truncated=result.truncated,
            as_of_seq=result.as_of_seq,
            snapshot_id=result.snapshot_id,
        )
        return result

    def _run(self, sql: str, limit: int, started: float, entry: dict[str, Any]) -> LakeQueryResult:
        with open_lake(self.config, write=False, timeout_s=self.lock_timeout_s) as con:
            tables = list(lake_tables(con))
            seq, snapshot = as_of(con)
            entry["as_of_seq"], entry["snapshot_id"] = seq, snapshot
            _sandbox(con, self.config)
            check_sql(con, sql, tables)
            timer = threading.Timer(self.timeout_s, con.interrupt)
            timer.start()
            try:
                rel = _tz_safe(con.sql(sql)).limit(limit + 1)
                columns = [str(c) for c in rel.columns]
                rows, truncated_by = self._collect(rel, limit)
            except duckdb.InterruptException:
                raise QueryError(
                    f"the query ran longer than {self.timeout_s:g} s", "InterruptException"
                ) from None
            except duckdb.Error as exc:
                raise self._query_error(exc) from None
            finally:
                timer.cancel()
        return LakeQueryResult(
            columns=columns,
            rows=rows,
            truncated=truncated_by is not None,
            limit=limit,
            as_of_seq=seq,
            snapshot_id=snapshot,
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
            truncated_by=truncated_by,
        )

    def _collect(self, rel: Any, limit: int) -> tuple[list[list[Any]], str | None]:
        """Fetch rows in batches until ``limit`` rows or ``max_bytes`` of JSON is reached."""
        rows: list[list[Any]] = []
        used = 0
        while True:
            batch = rel.fetchmany(BATCH_ROWS)
            if not batch:
                return rows, None
            for raw in batch:
                if len(rows) >= limit:
                    return rows, "limit"
                row = [jsonable(v) for v in raw]
                size = len(json.dumps(row, ensure_ascii=False).encode("utf-8"))
                if used + size > self.max_bytes:
                    return rows, "bytes"
                used += size
                rows.append(row)

    def _query_error(self, exc: duckdb.Error) -> QueryError:
        """A short message and the exception class; paths in DuckDB's text are removed."""
        first = (str(exc).splitlines() or [""])[0]
        text = self._scrub(first)[:ERROR_TEXT_CHARS]
        name = type(exc).__name__
        return QueryError(f"{name}: {text}" if text else name, name)

    def _scrub(self, text: str) -> str:
        """Replace the lake directory, then any other absolute path, in text shown to a caller."""
        text = text.replace(str(self.config.lake_dir), "<lake>")
        return _ABSOLUTE_PATH.sub("<path>", text)

    def _record(
        self, entry: dict[str, Any], started: float, *, outcome: str, **fields: Any
    ) -> None:
        """Write the audit line. Every line has the same keys."""
        line_data = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **entry,
            **fields,
            "outcome": outcome,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
        # ensure_ascii escapes U+2028, U+0085 and lone surrogates, so one call stays one line.
        line = json.dumps(line_data, ensure_ascii=True, default=str)
        log.log(logging.INFO if outcome == "ok" else logging.WARNING, "lake_query %s", line)
        try:
            self.config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config.audit_log_path.open("a", encoding="ascii") as handle:
                handle.write(line + "\n")
        except OSError as exc:
            log.error("lake_query audit log not written: %s", exc)
            if outcome == "ok":
                raise LakeError(
                    f"the query was not logged, so its result is withheld: {exc}"
                ) from exc


def _audited_sql(sql: Any) -> str:
    text = sql if isinstance(sql, str) else f"<{type(sql).__name__}> {sql!r}"
    if len(text) > MAX_SQL_CHARS:
        return text[:MAX_SQL_CHARS] + f"...[{len(text)} characters]"
    return text


def lake_query(
    sql: str,
    *,
    limit: int | None = None,
    lake_dir: str | None = None,
    caller: str = "unknown",
) -> LakeQueryResult:
    """The ``lake_query`` tool body: guarded read-only SQL over the lake at ``lake_dir``.

    Returns the rows (at most ``limit``) and the ledger seq the lake reflects. The MCP tool wraps
    this function.
    """
    return LakeQueryService(LakeConfig.at(lake_dir)).query(sql, limit=limit, caller=caller)
