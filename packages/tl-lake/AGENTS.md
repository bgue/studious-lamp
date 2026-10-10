# AGENTS.md — tl-lake

Read the root `AGENTS.md` first. These rules add to it.

- The lake is an analytics copy, never a source of truth (§28.1). Nothing reads it to decide a command, and nothing writes the ledger from it.
- Load DuckLake only through `tl_lake.duck.connect()`. Never call `INSTALL` or `LOAD` from anywhere else, and never enable extension autoinstall or autoload: the extension comes from the `duckdb-extension-ducklake` wheel (L-P0-I5-O2).
- A sync is one DuckLake transaction: the data and its `_tl_sync` row commit together or not at all. Do not add a second commit, an autocommit write, or a write outside `sync_lake`. Only `sync_lake` writes the lake.
- The ledger connection given to `sync_lake` must be a consistent snapshot (`read_snapshot`). Keep every ledger read in `sync.py` on that one connection and portable SQLAlchemy; no dialect SQL here.
- Never use `sqlalchemy.inspect` or `Table(autoload_with=...)` on a ledger connection: on Postgres the adapter returns JSON as text and reflection fails. Read column names with `tl_core.projection.promoted.table_columns`; the ledger is read through `tl_adapters.db`, never a dialect module.
- Tests that need a ledger use the `ledger` / `new_ledger` fixtures (they follow `--adapters`), so they run on SQLite and, under `just test-parity`, on Postgres.
- Silver columns come from the generated DDL (`tl_schema.ddl_loader`) plus reflected promoted columns. Do not hand-write a silver table. A column that appears in the ledger reloads its table in full, because the ledger back-fills it without touching `last_seq`.
- Bulk loads go through NDJSON and `read_json`; never `executemany` into DuckDB (about 50 times slower).
- Fetching a `TIMESTAMPTZ` in Python needs `pytz`, which is not a dependency: store `TIMESTAMP` (UTC) and cast zone-aware query columns to text.
- `lake_query` has three layers (guard, READ_ONLY attach, sandbox with external access off and the configuration locked). Do not remove one because another exists. A new allowed table function or a looser guard rule needs a test that names the file-reading case it must still refuse.
- Every `lake_query` call, accepted or refused, writes one audit line. A result is withheld if the line cannot be written.
- Lake files live under `TL_LAKE_DIR` (default `dev/data/lake`, git-ignored). Tests use `tmp_path` and never the default.
- A DuckDB catalog file has one writer or many readers across processes. Go through `open_lake`, which holds the lock file; never open `catalog.ducklake` directly.
