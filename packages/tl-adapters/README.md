# tl-adapters (`tl_adapters`)

Storage adapters that implement the `tl_core` Protocols: SQLite and the object store (`fs` and `s3` backends, ADR-0002). Postgres arrives in P0-I5 (§14, §15, §20).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_adapters.sqlite.engine.make_engine(path)` | function | SQLAlchemy engine: WAL, foreign keys, busy timeout, explicit `BEGIN` / `BEGIN IMMEDIATE` |
| `tl_adapters.sqlite.engine.write_tx`, `read_tx` | context managers | One write (immediate) or read transaction |
| `tl_adapters.sqlite.ledger.SqliteLedger` | class | Append-only `events` table, optimistic concurrency, per-scope hash chain, `append_in(conn, ...)` for a caller's transaction |
| `tl_adapters.sqlite.schema.sql` | resource | The `events` table, index, and triggers that reject UPDATE and DELETE |
| `tl_adapters.sqlite.factory.SqliteUowFactory(path)` | class | One engine, many short units of work (`factory()`, `factory(readonly=True)`, `dispose()`); what long-running workers use |
| `tl_adapters.sqlite.uow.SqliteUnitOfWork`, `open_uow(path, readonly=False)` | class, context manager | Append plus inline projectors in one transaction; publish after commit |
| `tl_adapters.sqlite.uow.create_schema(path)` | function | Events table and every default projector's tables; idempotent |
| `tl_adapters.sqlite.uow.rebuild_projections(path, types=None)` | function | Reset projectors and replay the ledger in one transaction; returns events replayed |
| `tl_adapters.objectstore.fs.FsObjectStore(root, secret=...)` | class | `ObjectStore` on a directory: atomic, fsynced, verified writes; never replaces a `sha256/` key; `file://` presigned URLs with an HMAC token and expiry (`redeem`, `put_via_url`, `get_via_url`); `iter_keys()` |
| `tl_adapters.objectstore.s3.S3ObjectStore(client, bucket, prefix=...)` | class | `ObjectStore` on S3/MinIO through a boto3 client: verify while spooling, then upload; `iter_keys()`; single `put_object` (no multipart in Phase 0) |
| `tl_adapters.objectstore.make_object_store(env=None)` | function | Build the store named by `TL_OBJECT_STORE` (`fs` default, or `s3`) |
| `tl_adapters.objectstore.object_secret(env=None)` | function | Signing secret for upload ids and fs URLs; fails closed (see Configuration) |

## Depends on / used by
- Depends on: `tl_core`, `sqlalchemy`, `python-ulid`, `boto3` (s3 backend; tests use `moto`, no MinIO).
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
| `TL_OBJECT_STORE` | `fs` | `fs` or `s3` |
| `TL_OBJECT_ROOT` | `./dev/data/objects` | Root of the `fs` store (git-ignored under `dev/data/`) |
| `TL_OBJECT_SECRET` | none | Required outside dev. Signs upload ids and fs presigned URLs; rotating it invalidates open uploads |
| `TL_ENV` | unset (`just` exports `dev`) | `dev` allows the public dev secret when `TL_OBJECT_SECRET` is unset; anything else fails closed |
| `TL_S3_BUCKET`, `TL_S3_PREFIX`, `TL_S3_ENDPOINT` | none | `s3` only; `TL_S3_ENDPOINT` points at MinIO. Credentials come from the usual AWS variables |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface change: P0-I4 workstream B (object store backends; decisions in `docs/tickets/P0-I4/README-B.md`). Recovery: `docs/runbooks/object-store-reconciliation.md`.
