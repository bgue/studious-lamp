# tl-adapters (`tl_adapters`)

Storage adapters that implement the `tl_core` Protocols: SQLite, PostgreSQL 16 and the object store (`fs` and `s3` backends, ADR-0002). One test suite runs on both databases (§14, §15, §20).

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
| `tl_adapters.db` (`open_uow`, `create_schema`, `rebuild_projections`, `make_engine`, `make_ledger`, `DbTarget`) | module | Picks the adapter from the target: a SQLite path or a `postgresql://` URL. Callers and tests are written once |
| `tl_adapters.postgres.engine.make_engine(url, pooled=False)`, `write_tx`, `read_tx` | function, context managers | Engine with SQLite-shaped result loaders; a write transaction takes the ledger advisory lock first, a read transaction is a read-only snapshot |
| `tl_adapters.postgres.ledger.PostgresLedger` | class | Same behaviour and hash chain as `SqliteLedger`; `events` is append-only (triggers reject UPDATE, DELETE, TRUNCATE); each append sends `NOTIFY tl_events` |
| `tl_adapters.postgres.uow.PostgresUnitOfWork`, `open_uow(url)`, `create_schema(url)`, `rebuild_projections(url)` | class, functions | Same registry order and bus publish as the SQLite unit of work (contract C2) |
| `tl_adapters.postgres.factory.PostgresUowFactory(url)` | class | One pooled engine; `factory()` write unit of work, `factory(readonly=True)` snapshot, `dispose()` |
| `tl_adapters.postgres.notify.NotifyListener(url, wake)` | class | Sets a `threading.Event` after each commit in its schema; pass it to `ChangePoller(wake=...)` |
| `tl_adapters.postgres.admin` | module | `schema_url`, `create_schema_namespace`, `drop_schema_namespace`, `create_database`, `reachable`: isolate ledgers and tests inside one server |
| `tl_adapters._unit.BaseUnitOfWork` | class | The transaction logic both units of work share |
| `tl_adapters.objectstore.fs.FsObjectStore(root, secret=...)` | class | `ObjectStore` on a directory: atomic, fsynced, verified writes; never replaces a `sha256/` key; `file://` presigned URLs with an HMAC token and expiry (`redeem`, `put_via_url`, `get_via_url`); `iter_keys()` |
| `tl_adapters.objectstore.s3.S3ObjectStore(client, bucket, prefix=...)` | class | `ObjectStore` on S3/MinIO through a boto3 client: verify while spooling, then upload; `iter_keys()`; single `put_object` (no multipart in Phase 0) |
| `tl_adapters.objectstore.make_object_store(env=None)` | function | Build the store named by `TL_OBJECT_STORE` (`fs` default, or `s3`) |
| `tl_adapters.objectstore.object_secret(env=None)` | function | Signing secret for upload ids and fs URLs; fails closed (see Configuration) |

## Depends on / used by
- Depends on: `tl_core`, `sqlalchemy`, `pg8000` (Postgres driver, BSD-3-Clause), `python-ulid`, `boto3` (s3 backend; tests use `moto`, no MinIO).
- Used by: `tl_cli`, tests, later the API and TUI embedded mode.

## Commands
```
just test packages/tl-adapters
just test tests/property
just test-parity                     # parity-marked tests on SQLite and Postgres, plus the Postgres-only tests
```
Local Postgres: `docs/runbooks/postgres-local-setup.md`.

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| Database target | passed by the caller (`TL_DB` in the CLI, SQLite only for now) | A SQLite file (WAL sidecar files are git-ignored) or a `postgresql://` URL for `tl_adapters.db` |
| `TL_PG_URL` | `postgresql://postgres:postgres@localhost:5432/tl_test` | The Postgres server the tests use; they create a throw-away database on it |
| `TL_REQUIRE_POSTGRES` | unset (`just test-parity` sets `1`) | `1` turns "Postgres unreachable" from a skip into a failure |
| `--adapters` (pytest) | `sqlite` | `sqlite,postgres` runs every test that uses the `new_db` / `db` / `adapter` fixtures on both |
| `TL_OBJECT_STORE` | `fs` | `fs` or `s3` |
| `TL_OBJECT_ROOT` | `./dev/data/objects` | Root of the `fs` store (git-ignored under `dev/data/`) |
| `TL_OBJECT_SECRET` | none | Required outside dev. Signs upload ids and fs presigned URLs; rotating it invalidates open uploads |
| `TL_ENV` | unset (`just` exports `dev`) | `dev` allows the public dev secret when `TL_OBJECT_SECRET` is unset; anything else fails closed |
| `TL_S3_BUCKET`, `TL_S3_PREFIX`, `TL_S3_ENDPOINT` | none | `s3` only; `TL_S3_ENDPOINT` points at MinIO. Credentials come from the usual AWS variables |

## Postgres behaviour worth knowing
- Writers queue on one advisory lock (like SQLite's write lock) and fail with a lock timeout after 10 s; readers never wait; `seq` has no gaps.
- Rows come back SQLite-shaped (canonical JSON text, ISO UTC timestamps, 0/1 booleans). Text columns are byte-ordered (`COLLATE "C"`).
- `LOWER()` folds by the server's ctype on Postgres and only ASCII on SQLite, so a case-insensitive search for a non-ASCII letter can differ.
- Not done yet: the `tl` CLI, TUI and API still open SQLite paths; `tl migrate` is filed as `docs/tickets/P0-I5/T99-migrate-sqlite-to-postgres.md` (needs a human).

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Postgres adapter and parity suite: P0-I5 workstream A (decisions in `docs/tickets/P0-I5/README-A.md`). Previous interface change: P0-I4 workstream B (object store backends; decisions in `docs/tickets/P0-I4/README-B.md`). Recovery: `docs/runbooks/object-store-reconciliation.md`.
