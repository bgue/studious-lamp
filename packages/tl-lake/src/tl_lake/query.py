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
from tl_lake.errors import LakeError, LakeNotInitialisedError
from tl_lake.guard import GuardError, check_sql
from tl_lake.status import as_of

log = logging.getLogger("tl_lake.query")
log.addHandler(logging.NullHandler())  # a library prints nothing until the application opts in

DEFAULT_LIMIT = 100
MAX_LIMIT = 10_000
TIMEOUT_S = 30.0
MEMORY_LIMIT = "1GB"
THREADS = 2


class QueryError(LakeError):
    """The statement passed the guard but failed or ran too long."""


@dataclass(frozen=True)
class LakeQueryResult:
    """Rows are JSON-safe values. ``truncated`` means more rows existed than ``limit``."""

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    limit: int
    as_of_seq: int
    snapshot_id: int | None
    elapsed_ms: float

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
    """Runs guarded queries against one lake."""

    def __init__(
        self,
        config: LakeConfig,
        *,
        default_limit: int = DEFAULT_LIMIT,
        max_limit: int = MAX_LIMIT,
        timeout_s: float = TIMEOUT_S,
        lock_timeout_s: float = 30.0,
    ) -> None:
        self.config = config
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.timeout_s = timeout_s
        self.lock_timeout_s = lock_timeout_s

    def query(
        self, sql: str, *, limit: int | None = None, caller: str = "unknown"
    ) -> LakeQueryResult:
        """Run ``sql`` and return at most ``limit`` rows plus the as-of seq.

        Raises :class:`GuardError` when the statement is refused, :class:`QueryError` when it
        fails or times out, and :class:`LakeNotInitialisedError` when nothing was synced yet.
        """
        started = time.monotonic()
        wanted = self.default_limit if limit is None else limit
        entry: dict[str, Any] = {"caller": caller, "sql": sql, "limit": wanted}
        try:
            if isinstance(wanted, bool) or not isinstance(wanted, int):
                raise GuardError("limit must be an integer")
            if not 1 <= wanted <= self.max_limit:
                raise GuardError(f"limit must be between 1 and {self.max_limit}")
            result = self._run(sql, wanted, started)
        except GuardError as exc:
            self._record(entry, "refused", started, detail=str(exc))
            raise
        except LakeNotInitialisedError as exc:
            self._record(entry, "error", started, detail=str(exc))
            raise
        except QueryError as exc:
            self._record(entry, "error", started, detail=str(exc))
            raise
        self._record(
            entry,
            "ok",
            started,
            rows=result.row_count,
            truncated=result.truncated,
            as_of_seq=result.as_of_seq,
            snapshot_id=result.snapshot_id,
        )
        return result

    def _run(self, sql: str, limit: int, started: float) -> LakeQueryResult:
        with open_lake(self.config, write=False, timeout_s=self.lock_timeout_s) as con:
            tables = [t for t in lake_tables(con)]
            seq, snapshot = as_of(con)
            _sandbox(con, self.config)
            check_sql(con, sql, tables)
            timer = threading.Timer(self.timeout_s, con.interrupt)
            timer.start()
            try:
                rel = _tz_safe(con.sql(sql)).limit(limit + 1)
                columns = [str(c) for c in rel.columns]
                fetched = rel.fetchall()
            except duckdb.InterruptException:
                raise QueryError(f"the query ran longer than {self.timeout_s:g} s") from None
            except duckdb.Error as exc:
                raise QueryError(str(exc).splitlines()[0]) from None
            finally:
                timer.cancel()
        truncated = len(fetched) > limit
        rows = [[jsonable(v) for v in row] for row in fetched[:limit]]
        return LakeQueryResult(
            columns=columns,
            rows=rows,
            truncated=truncated,
            limit=limit,
            as_of_seq=seq,
            snapshot_id=snapshot,
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
        )

    def _record(self, entry: dict[str, Any], outcome: str, started: float, **fields: Any) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **entry,
            "outcome": outcome,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            **fields,
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        level = logging.INFO if outcome == "ok" else logging.WARNING
        log.log(level, "lake_query %s", line)
        try:
            self.config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config.audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as exc:
            log.error("lake_query audit log not written: %s", exc)
            if outcome == "ok":
                raise LakeError(
                    f"the query was not logged, so its result is withheld: {exc}"
                ) from exc


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
