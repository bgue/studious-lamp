# AGENTS.md — tl-adapters

Read the root `AGENTS.md` first. These rules add to it.

- Dialect-specific SQL lives only here (and, as generated DDL text, in `tl_schema`).
- Never UPDATE or DELETE rows of `events`; the triggers reject it and no code may route around them.
- SQLite transactions go through `write_tx` / `read_tx`. Do not reintroduce pysqlite's implicit transaction handling.
- `append_in` needs a connection from `write_tx`. Commit and bus enqueue happen under one lock; subscribers run after it is released.
- Parity: every behaviour of a ledger or unit of work is tested through the `new_db` fixture so it runs on both adapters (`just test-parity`). A test that only makes sense on one dialect says so in its name and uses `pg_db` or the SQLite engine directly.
- Postgres write transactions must go through `postgres.engine.write_tx`: it takes the ledger advisory lock before the first read. Never append from a connection that skipped it, and never add `FOR UPDATE` as a substitute.
- Postgres results are shaped like SQLite's by the loaders in `postgres/engine.py` (canonical JSON text, ISO UTC timestamp strings, 0/1 booleans). Do not change a loader without running the whole parity suite; do not call `sqlalchemy.inspect(...).get_columns` (use `tl_core.projection.promoted.table_columns`).
- `events.payload` stays TEXT (the hash covers the canonical text) and `seq` stays `MAX(seq)+1` under the lock (gap-free). Both are decisions, see `docs/tickets/P0-I5/README-A.md`.
- Hand-written SQL in tests: booleans are `TRUE`/`FALSE` or a bound bool, timestamps are full ISO strings, binds are `text(...)` with `:name`.
- pyright strict applies to `src/`. No ignores.
- Object stores: a `sha256/` key is written only by `put`, after size and SHA-256 are verified, and is never replaced. Presigned uploads (`presign_put`, `put_via_url`) accept staging keys only. Every key goes through `tl_core.files.keys.check_key` first.
- Tests use `FsObjectStore` or moto's in-process `mock_aws`; never a live MinIO, never the network. `s3.py` starts with `# pyright: basic` because boto3 has no stubs; keep that to the one file.
- `object_secret()` fails closed. Never add a default secret or log one.
- `FsObjectStore` writes objects with mode 0600 (temp files come from `mkstemp`). Keep it: widening access is an operator decision, not a code default.
- `restore_events` is the only way events enter a database without `Ledger.append`, and only into an empty `events` table inside `write_tx`; it never recomputes anything. A restore is one transaction (events, promoted columns, replay, verification), so a failure leaves an empty database; keep it that way.
- `FsArchiveStore` never replaces a key (`os.link` fails if it exists; never use `rename` or `replace`) and a snapshot or archive file is never written in place. A drill touches only scratch clusters or databases it creates itself; never `tl_test`, never the cluster on 5432 beyond creating and dropping its own scratch database.
- A restore sets the webhook dispatcher cursor (`wh_cursor`, name `outbox`) to the restored head inside its transaction; never leave it at 0, which would queue every historical event again.
