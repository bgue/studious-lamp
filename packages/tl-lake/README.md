# tl-lake (`tl_lake`)

The DuckLake analytics copy of the ledger: an incremental sync by `seq`, a silver mapping from the generated schema, and a guarded read-only `lake_query` service (§28.1 to §28.4, §11.3). The lake is never a source of truth and can always be rebuilt.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `LakeConfig.at(dir=None)` | class | Lake paths: `dir`, else `$TL_LAKE_DIR`, else `dev/data/lake`. Holds `catalog.ducklake`, `data/` (Parquet), the lock file and the audit log |
| `read_snapshot(engine)` | context manager | The ledger as one consistent read snapshot: `tl_adapters.db.read_tx` (REPEATABLE READ READ ONLY on Postgres) |
| `sync_lake(config, conn, rebuild=False)` | function | One sync = one DuckLake snapshot: bronze `events`, silver `cur_core_record`, `links`, `pset_values`, and the `_tl_sync` row, in one transaction. Returns `SyncResult` |
| `sync_xer(config, conn, raw_reader=None)` | function | The second pass of `tl lake sync` (P1-I4, ADR-0015 section 4): loads the built P6 schedule snapshots whole (they are operational tables, not events): bronze `xer_<table>`, silver `schedule_snapshot` and `schedule_activity`, the mart `mart_float_trend` (`tl_lake.xer_marts`), and the control tables `_tl_xer` and `_tl_xer_state`. Returns `XerSyncResult`. `raw_reader` gives the bytes of a snapshot's raw bundle; without one the bronze tables wait |
| `lake_status(config)` | function | `LakeStatus`: as-of seq, snapshot id, sync count, rows per table |
| `describe_lake(config)` | function | Tables and columns |
| `LakeQueryService(config).query(sql, limit=, caller=)` | class | Guarded read-only SQL: row limit, timeout, audit line. Returns `LakeQueryResult` (rows, `truncated`, `as_of_seq`, `snapshot_id`) |
| `lake_query(sql, limit=, lake_dir=, caller=)` | function | The MCP tool body (the registration arrives with P0-I4) |
| `GuardError`, `QueryError`, `LakeError` and subclasses | exceptions | A refusal; a failed or timed-out statement; everything else |
| `tl_lake.errors` | module | The errors `tl_lake` raises; every one is a `LakeError`, so a caller can catch the family |
| `tl_lake.ingest` | module | Bulk loading into the lake through NDJSON files (never `executemany`; L-P0-I7-B1) |

Demo queries: `dev/lake/queries/*.sql` (events by type, records overview, links by relation, valve sizes, pset coverage, as-of seq), tested by `tests/test_demo_queries.py`. A rebuild resets the sync count (`syncs 1`).

CLI: `tl lake sync | rebuild --yes | status | tables | query SQL [--limit N] [--json]` (in `tl-cli`).

## How a sync works
1. Read the ledger head and the lake watermark (`max(_tl_sync.last_seq)`). Refuse if the lake is past the head, or if the event at the watermark differs (hash) between lake and ledger.
2. In one DuckLake transaction: create tables or add new columns (a new promoted pset column reloads its silver table in full, because the ledger back-fills it without touching `last_seq`); append events `watermark+1..head` to bronze, failing on a gap; for each silver table, replace the rows whose `last_seq` is past the watermark (`pset_values` is replaced per changed record); insert the `_tl_sync` row `(snapshot_id, first_seq, last_seq, synced_at)`.
3. COMMIT, then check that the committed snapshot is the one the row names.

A crash before COMMIT changes nothing. The lake and the ledger are compared by the hash of the one event at the watermark, by design: it catches a lake pointed at a different ledger cheaply. Integrity of the whole chain belongs to `tl archive verify` (WS-A), not to the sync. A full rebuild equals the incremental result (property test `test_rebuild_equals_incremental.py`).

## Tables
| Table | Layer | Source | Notes |
|---|---|---|---|
| `events` | bronze | ledger `events` | Same columns and order as the ledger table; `payload`, `recorded_at` and `effective_at` are text exactly as hashed, so `event_hash` re-verifies. An archive segment's `events.parquet` must use the same names |
| `cur_core_record` | silver | `cur_core_record` | Generated columns plus promoted `pset__<pset>__<property>` columns |
| `links` | silver | `cur_links` | |
| `pset_values` | silver | `cur_pset_values` | Long form |
| `cur_documents_document`, `cur_documents_revision` | silver | the same ledger tables | The documents and revisions the lowest reader may read (P1-I8); a restricted document and its revisions are in no row |
| `mart_document_status`, `mart_document_turnaround`, `mart_document_issues` | mart | the two document tables | Rebuilt by every sync from the silver above (`tl_lake.doc_marts`), so a mart holds nothing silver does not; no document means no mart |
| `mart_schedule_history` | mart | the two schedule tables | One row per published snapshot: counts, percent complete, project finish, slip against the snapshot before that has activity rows, activities added and removed (`tl_lake.xer_marts`) |
| `_tl_sync` | control | | `snapshot_id, first_seq, last_seq, synced_at`: one row per sync |
| `schedule_snapshot` | silver | `cur_schedule_schedule_snapshot` | One row per built snapshot (Valid, Published, Superseded): schedule code, number, state, `is_current`, data date, counts. Replaced as a whole when it differs |
| `schedule_activity` | silver | `sched_activity` | The typed activities of every built snapshot, with schedule code, snapshot number, data date and floats in days (`total_float_days`, `free_float_days`) of the activity's own calendar. Added once per snapshot |
| `xer_<table>` | bronze | raw bundle of the snapshot | The tables P6 defines (`P6_TABLES`), every field as text, plus `_snapshot_id` and `_row_no`; at most 300 columns |
| `xer_other` | bronze | raw bundle of the snapshot | Every other table of the file, in long format (`_snapshot_id`, `_table`, `_row_no`, `_column`, `value`; empty cells are not stored) |
| `_tl_xer_failed` | control | `sync_xer` | Snapshots whose bronze load failed on their own content, with a fixed reason; later passes skip them |
| `mart_float_trend` | mart | the two silver tables | Per activity and published snapshot: float, the float before, the change in days and `eroded` |
| `_tl_xer`, `_tl_xer_state` | control | | Which snapshots the lake holds (and whether their bronze tables are in), and the signature of the last `schedule_snapshot` written |

Types come from the generated Postgres DDL: `BOOLEAN`, `BIGINT`, `DOUBLE`, `VARCHAR`, and `TIMESTAMP` holding UTC. JSON columns (`events.payload`, `psets_json`, `value_json`) are stored as canonical JSON text on every adapter. A promoted pset column takes its type from the effective schema of the scopes in the ledger (the mapping that created it), so a boolean is `BOOLEAN` on SQLite and Postgres alike; a column no schema knows is typed from its first value.

## Who may be read in silver (ADR-0016)
Silver holds what the lowest reader may read. A record that is hidden is left out; when a document is reclassified its `last_seq` moves, but its revisions' do not, so each sync also (1) deletes from every silver table the rows that have a hidden record at one end, and (2) copies again the records of the confidential families that are readable now and missing from the lake. The lake stores nothing about a hidden record, not even its id. The events already copied stay in bronze `events` until `tl lake rebuild` (ADR-0016, accepted). `test_document_silver.py` walks a restricted document through sync, classification, declassification and rebuild.

## `lake_query` guard
Exactly one statement, parsed by DuckDB; SELECT only; tables must be lake tables or CTEs visible at that point; table functions limited to `range`, `generate_series`, `unnest`, `generate_subscripts`; no `getenv`, `current_setting`, `read_*`, `glob`, `duckdb_*` and similar. Refused: stacked statements, DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET, EXPLAIN, file-reading functions and other catalogs. Two more layers sit behind it: the catalog is attached READ_ONLY, and external file access is switched off and the configuration locked before the statement runs. Default limit 100, maximum 10 000, result size cap 8 MiB of JSON (`truncated_by` says `limit` or `bytes`), timeout 30 s (best effort: DuckDB checks for interruption between chunks of work, so a long scalar computation can overrun it; the 1 GB memory limit bounds the damage). Table and CTE names that look like paths or globs are refused, and a CTE is visible only where SQL scopes it. Time travel (`AT (VERSION => n)`) is allowed on purpose. Errors are a short message plus the DuckDB error class, with filesystem paths removed; every call writes one audit line with the same keys (`ts, caller, sql, limit, outcome, detail, error_class, rows, truncated, as_of_seq, snapshot_id, elapsed_ms`), ASCII-escaped so one call is one line. Every call, accepted or refused, appends a line to `lake_query.log.jsonl`.

## Depends on / used by
- Depends on: `tl_xer` (the raw bundle reader), `duckdb==1.5.5`, `duckdb-extensions`, `duckdb-extension-ducklake` (all MIT; the extension wheel's version must equal duckdb's), `sqlalchemy`, `tl_schema` (generated DDL), `tl_core`.
- Used by: `tl_cli` (`tl lake`), the `lake_query` MCP tool (P0-I4 and later), `just demo P0-I7-lake`. Runbook: `docs/runbooks/lake-sync.md`.

## Commands
```
just test packages/tl-lake
uv run pytest packages/tl-lake --adapters sqlite,postgres   # the same tests on Postgres
just demo P0-I7-lake
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_LAKE_DIR` / `--lake-dir` | `./dev/data/lake` | Git-ignored. Contains `catalog.ducklake`, `data/`, `lake_query.log.jsonl`, `.lake.lock`, `tmp/` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Known limits (follow-ups)
- Catalog is a DuckDB file: one writer or many readers across processes, serialised by a lock file. Production uses a PostgreSQL catalog (§28.1).
- Bronze is not yet partitioned by company, project and date; no compaction or snapshot expiry; `hist_*` tables are a later increment.
- Loading bronze from archive Parquet segments directly is not built; restore the ledger, then sync.

## Status
Introduced in P0-I7 (workstream B). Last interface change: P1-I8 (documents silver, document and schedule history marts, the readable-set rule).
