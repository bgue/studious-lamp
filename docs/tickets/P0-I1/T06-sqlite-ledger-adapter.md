# P0-I1-T06 — SQLite ledger adapter

Status: ready
Tier: haiku
Labels: adapter
Depends on: P0-I1-T05
Branch: `p0/i1-t06-sqlite-ledger`

## Goal
`tl_adapters.sqlite.ledger.SqliteLedger` implements the `Ledger` Protocol on a SQLite file (WAL mode): an
append-only `events` table, optimistic concurrency on `stream_version`, a per-scope hash chain, and reads by stream
and by global `seq`. UPDATE and DELETE on `events` are rejected by triggers. It also exposes `append_in(conn, ...)`
so the unit of work (supervisor-built, P0-I1-T07) can append inside its own transaction.

## Brief references (pasted)
> No updates, no deletes on the event table (enforced by DB triggers/permissions in Postgres; by convention + checks in SQLite). (§5.2) — this ticket uses triggers on SQLite too.
> `seq` global monotonic sequence (bigint), the ordering backbone. `stream_version` per-record; optimistic concurrency check. `prev_hash`/`hash` hash chain per scope. (§5.1)
> Dev: SQLite (WAL, JSON1, FTS5). (§14)

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call.
- pyright runs in strict mode on `tl_adapters` source (tests are standard). Annotate everything; do not add ignores.
- Dialect-specific SQL belongs in `packages/tl-adapters/` only, which is where you are working.

## Interfaces (verbatim)
From the repo (merged in P0-I1-T05; do not modify): `NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`, `Ledger`
(`tl_core.ledger`), `canonical_json`, `event_hash`, `iso_utc` (`tl_core.ledger`), `utcnow`, `new_ulid` (`tl_core.util`).

`Ledger` Protocol methods to implement: `append`, `read_stream`, `read_after`, `head_seq`, `stream_version` (signatures in
`packages/tl-core/src/tl_core/ledger/types.py`).

### `packages/tl-adapters/src/tl_adapters/sqlite/engine.py` (exact)
```python
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
```
Why: pysqlite's own transaction handling breaks an explicit `BEGIN IMMEDIATE`. Write transactions (`write_tx`) take the
write lock first, so two writers cannot both pass the version check. `read_tx` is a deferred read snapshot.

### `packages/tl-adapters/src/tl_adapters/sqlite/schema.sql` (exact)
```sql
CREATE TABLE IF NOT EXISTS events (
  seq            INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id       TEXT NOT NULL UNIQUE,
  stream_id      TEXT NOT NULL,
  stream_type    TEXT NOT NULL,
  stream_version INTEGER NOT NULL,
  event_type     TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  scope          TEXT NOT NULL,
  payload        TEXT NOT NULL,
  actor          TEXT NOT NULL,
  recorded_at    TEXT NOT NULL,
  effective_at   TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  causation_id   TEXT,
  source         TEXT NOT NULL,
  prev_hash      TEXT,
  hash           TEXT NOT NULL,
  UNIQUE (stream_id, stream_version)
);
CREATE INDEX IF NOT EXISTS ix_events_scope_seq ON events(scope, seq);
CREATE TRIGGER IF NOT EXISTS trg_events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
```

### `SqliteLedger` (`ledger.py`)
```python
class SqliteLedger:
    def __init__(self, engine: Engine, *, clock: Callable[[], datetime] = utcnow,
                 id_gen: Callable[[], str] = new_ulid) -> None: ...
    def create_schema(self) -> None: ...            # idempotent; runs schema.sql
    def append(self, *, stream_id, stream_type, scope, expected_version, events, actor, source,
               correlation_id, causation_id=None) -> AppendResult: ...      # opens write_tx(self._engine), calls append_in
    def append_in(self, conn: Connection, *, <the same keyword arguments as append>) -> AppendResult: ...
    def read_stream(self, stream_id: str, *, from_version: int = 1) -> list[Event]: ...
    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]: ...
    def head_seq(self) -> int: ...                  # 0 when empty
    def stream_version(self, stream_id: str) -> int: ...   # 0 when absent
```
Give every method the full typed signature from the `Ledger` Protocol; the sketch above abbreviates the keyword list.

`create_schema`: read `schema.sql` with `importlib.resources.files("tl_adapters.sqlite").joinpath("schema.sql").read_text(encoding="utf-8")`
and run it with the raw driver connection, because the trigger bodies contain semicolons:
```python
raw = self._engine.raw_connection()
try:
    cast(sqlite3.Connection, raw.driver_connection).executescript(script)
finally:
    raw.close()
```
(Include `schema.sql` in the package: it sits in the package directory, so hatch ships it.)

`append_in(conn, ...)` semantics, inside the caller's write transaction:
1. If `not is_write_connection(conn)` raise `RuntimeError("append_in needs a connection from write_tx")`. If `events` is empty raise `ValueError`.
2. Read the stream's current version: `SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s`. If it differs from `expected_version` raise `ConcurrencyError` (message names the stream, expected, and found).
3. Read the last `hash` in the same `scope` (`ORDER BY seq DESC LIMIT 1`, `None` if none) as `prev_hash` of the first new event; each later event in the batch chains to the one before it.
4. For each `NewEvent`, in order: `stream_version += 1`; `event_id = id_gen()`; `recorded_at = clock()`; `effective_at = ev.effective_at or recorded_at`;
   `payload_json = canonical_json(ev.payload)` (this exact text is what is stored); `hash = event_hash(prev_hash, event_id, stream_id, stream_version, ev.event_type, payload_json, iso_utc(recorded_at))`;
   insert a row (timestamps stored as `iso_utc(...)` text); the new `seq` is `result.lastrowid`.
5. Return `AppendResult(events=[stored Event objects, seq filled], new_version=<last stream_version>, last_seq=<last seq>)`.

Reads: build `Event` objects from rows (`payload` via `json.loads`, timestamps via `datetime.fromisoformat`). `read_stream` orders by
`stream_version`; `read_after` orders by `seq`, applies `scope` when given, and `LIMIT :limit`. Use `read_tx(self._engine)` for reads. Use bound
parameters everywhere; never format values into SQL.

## Step 1: install the provided test file
The supervisor-written test file is stored outside the test tree so it cannot break other tickets' checks. Copy it byte for byte:
```
cp docs/tickets/P0-I1/provided/test_sqlite_ledger.py.txt packages/tl-adapters/tests/test_sqlite_ledger.py
```
Never edit the copy. A reviewer will run `diff` between the two files; any difference is a finding.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/ledger/types.py`
- `packages/tl-core/src/tl_core/ledger/hashing.py`
- `packages/tl-core/src/tl_core/util.py`
- `docs/tickets/P0-I1/provided/test_sqlite_ledger.py.txt` (the provided test; make the installed copy pass, do not edit it)

## Allowed paths
- `packages/tl-adapters/tests/test_sqlite_ledger.py` (create by `cp` from the provided file, unchanged)
- `packages/tl-adapters/src/tl_adapters/sqlite/__init__.py` (create, docstring only)
- `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py` (create)
- `packages/tl-adapters/src/tl_adapters/sqlite/schema.sql` (create, exact content above)
- `packages/tl-adapters/src/tl_adapters/sqlite/engine.py` (create, exact content above)

No dependency changes: `sqlalchemy` and `python-ulid` are already declared in `packages/tl-adapters/pyproject.toml`.

## Acceptance
```
just check
diff docs/tickets/P0-I1/provided/test_sqlite_ledger.py.txt packages/tl-adapters/tests/test_sqlite_ledger.py
uv run pytest packages/tl-adapters/tests/test_sqlite_ledger.py -q
```
Expected: the provided file passes in full (17 tests). It covers: new stream append and field filling; explicit `effective_at`; version
increments; `ConcurrencyError` on stale or wrong `expected_version` with nothing written; empty batch rejected; chain continuity per scope
(`prev_hash` of the 2nd event in scope A equals the hash of the 1st in scope A, not scope B); a batch of 3 chains internally; stored hash
recomputes from the row; `read_after` ordering, `limit`, `scope`; `read_stream(from_version)`; `head_seq`/`stream_version` on an empty
ledger; UPDATE and DELETE raise `IntegrityError`; idempotent `create_schema`; `append_in` rolls back with the caller's transaction and
rejects a read connection; two threads racing on one new stream give exactly one winner.

## Tests to add
None beyond the provided file. If you believe a case is missing, say so under *Open questions*; do not add it.

## Report requirements
Standard report. State the SQLite version from `python -c "import sqlite3; print(sqlite3.sqlite_version)"`.

## Escalation triggers
- Stop if the provided test expects behaviour the semantics above cannot satisfy.
- Stop if WAL mode cannot be set in the test environment.
- Stop if pyright strict rejects code that follows this ticket exactly; do not add ignores.

## Blocked

## Decision
