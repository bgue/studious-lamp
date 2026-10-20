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
- Schedule snapshots (P1-I4, `tl_lake.xer`): the typed rows (`sched_*`) are operational tables, not events, so they are loaded **whole per snapshot in a second pass** after `sync_lake`, never by `seq`. A built snapshot is immutable: load it once, take it out only when it stops being built (a Valid one that is voided). A change that makes the pass depend on the event watermark, or loads a snapshot twice, breaks "a rebuild equals the incremental lake" (`tests/test_xer.py`). A ledger with no schedule adds none of the schedule tables. The bronze tables come from the raw bundle through the `raw_reader` the caller passes: `tl_lake` imports no module (only `tl_xer.bundle`); the tests import `tl_mod_schedule` to build a world.
- A new mart is a function in `xer_marts.py` called by `build_marts` inside the loader's transaction; it reads the silver tables only and replaces its table whole. Its test checks the rows for the demo pair of files.
- A silver table that holds records of a confidential family needs its record-id columns in `_VISIBLE_ENDS` (`sync.py`): the purge of newly hidden records and the copy of newly readable ones work from that list. A table with children of a class-bearing record (revisions) is keyed by the child's own record id; the family's types are read from the modules' `ConfidentialSource`, never listed here.
- A document mart reads silver only and is rebuilt by every non-empty sync (`doc_marts.build_document_marts`); `tl lake mart ls|show` reads marts. The walking test (`test_document_silver.py`) must keep a restricted document in no silver row and no mart count.
