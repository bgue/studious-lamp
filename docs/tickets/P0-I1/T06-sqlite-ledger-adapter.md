# P0-I1-T06 — SQLite ledger adapter

Status: ready
Tier: haiku
Labels: adapter
Depends on: P0-I1-T05
Branch: `p0/i1/t06-sqlite-ledger`

## Goal
`tl_adapters.sqlite.ledger.SqliteLedger` implements the `Ledger` Protocol on a SQLite file (WAL mode): an
append-only `events` table, optimistic concurrency on `stream_version`, a per-scope hash chain, and reads by stream
and by global `seq`. UPDATE and DELETE on `events` are rejected by triggers.

## Brief references (pasted)
> No updates, no deletes on the event table (enforced by DB triggers/permissions in Postgres; by convention + checks in SQLite). (§5.2) — this ticket uses triggers on SQLite too.
> `seq` global monotonic sequence (bigint), the ordering backbone. `stream_version` per-record; optimistic concurrency check. `prev_hash`/`hash` hash chain per scope. (§5.1)
> Dev: SQLite (WAL, JSON1, FTS5). (§14)

## Interfaces (verbatim)
`Ledger`, `NewEvent`, `Event`, `AppendResult`, `ConcurrencyError` from `packages/tl-core/src/tl_core/ledger/types.py`;
`event_hash`, `canonical_json` from `packages/tl-core/src/tl_core/ledger/hashing.py`. Do not modify them.

Constructor: `SqliteLedger(engine: sqlalchemy.Engine, *, clock: Callable[[], datetime] = utcnow, id_gen: Callable[[], str] = new_ulid)`.
`SqliteLedger.create_schema()` executes `schema.sql` idempotently.

`schema.sql` (exact):
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

Append semantics:
1. In one transaction (`BEGIN IMMEDIATE`): read current `stream_version` (0 if absent); if `!= expected_version` raise `ConcurrencyError`.
2. Read the last `hash` in the same `scope` (by max `seq`) as `prev_hash` for the first new event; chain within the batch.
3. For each `NewEvent` in order: `stream_version += 1`, `event_id = id_gen()`, `recorded_at = clock()`, `effective_at = ev.effective_at or recorded_at`, compute `hash`, insert.
4. Return `AppendResult(events=[...with seq filled...], new_version, last_seq)`.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/ledger/types.py`
- `packages/tl-core/src/tl_core/ledger/hashing.py`
- `packages/tl-adapters/tests/test_sqlite_ledger.py` (provided by the supervisor; make it pass, do not edit)
- `tests/conftest.py`

## Allowed paths
- `packages/tl-adapters/src/tl_adapters/sqlite/__init__.py` (create)
- `packages/tl-adapters/src/tl_adapters/sqlite/ledger.py` (create)
- `packages/tl-adapters/src/tl_adapters/sqlite/schema.sql` (create, exact content above)
- `packages/tl-adapters/src/tl_adapters/sqlite/engine.py` (create: `make_engine(path) -> Engine` setting `journal_mode=WAL`, `foreign_keys=ON`)
- `packages/tl-adapters/pyproject.toml` (add `python-ulid` only)

## Acceptance
```
just check
uv run pytest packages/tl-adapters/tests/test_sqlite_ledger.py -q
```
Expected: the provided test file passes in full. It covers: new stream append; version increments; `ConcurrencyError`
on stale `expected_version`; chain continuity across two scopes (`prev_hash` of the 2nd event in scope A equals hash
of the 1st in scope A, not scope B); `read_after` ordering and `limit`; `read_stream(from_version)`; `head_seq`;
UPDATE and DELETE raise `IntegrityError`; a batch of 3 events in one append chains internally.

## Tests to add
None beyond the provided file. If you believe a case is missing, say so under *Open questions*; do not add it.

## Report requirements
Standard report. State the SQLite version from `sqlite3.sqlite_version`.

## Escalation triggers
- Stop if the provided test expects behaviour the pasted append semantics cannot satisfy.
- Stop if WAL mode cannot be set in the test environment.

## Blocked

## Decision
