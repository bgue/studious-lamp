# tl-adapters (`tl_adapters`)

Storage adapters that implement the `tl_core` Protocols. Phase 0 has SQLite only; Postgres and the object store arrive in later increments (§14, §15).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_adapters.sqlite.engine.make_engine(path)` | function | SQLAlchemy engine: WAL, foreign keys, busy timeout, explicit `BEGIN` / `BEGIN IMMEDIATE` |
| `tl_adapters.sqlite.engine.write_tx`, `read_tx` | context managers | One write (immediate) or read transaction |
| `tl_adapters.sqlite.ledger.SqliteLedger` | class | Append-only `events` table, optimistic concurrency, per-scope hash chain, `append_in(conn, ...)` for a caller's transaction |
| `tl_adapters.sqlite.schema.sql` | resource | The `events` table, index, and triggers that reject UPDATE and DELETE |
| `tl_adapters.sqlite.uow.SqliteUnitOfWork`, `open_uow(path, readonly=False)` | class, context manager | Append plus inline projectors in one transaction; publish after commit |
| `tl_adapters.sqlite.uow.create_schema(path)` | function | Events table and every default projector's tables; idempotent |
| `tl_adapters.sqlite.uow.rebuild_projections(path, types=None)` | function | Reset projectors and replay the ledger in one transaction; returns events replayed |

## Depends on / used by
- Depends on: `tl_core`, `sqlalchemy`, `python-ulid`.
- Used by: `tl_cli`, tests, later the API and TUI embedded mode.

## Commands
```
just test packages/tl-adapters
just test tests/property
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| Database path | passed by the caller (`TL_DB` in the CLI) | A SQLite file; WAL sidecar files are git-ignored |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface change: P0-I1 (plan decisions D8, D13).
