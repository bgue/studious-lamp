# tl-lake (`tl_lake`)

The DuckLake analytics copy of the ledger: an incremental sync by `seq`, a silver mapping from the generated schema, and a guarded read-only `lake_query` service (§28.1 to §28.4, §11.3). The lake is never a source of truth and can always be rebuilt.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `LakeConfig.at(dir=None)` | class | Lake paths: `dir`, else `$TL_LAKE_DIR`, else `dev/data/lake`. Holds `catalog.ducklake`, `data/` (Parquet), the lock file and the audit log |
| `read_snapshot(engine)` | context manager | The ledger as one consistent read snapshot (REPEATABLE READ on Postgres) |
| `sync_lake(config, conn, rebuild=False)` | function | One sync = one DuckLake snapshot: bronze `events`, silver `cur_core_record`, `links`, `pset_values`, and the `_tl_sync` row, in one transaction. Returns `SyncResult` |
| `lake_status(config)` | function | `LakeStatus`: as-of seq, snapshot id, sync count, rows per table |
| `describe_lake(config)` | function | Tables and columns |
| `LakeQueryService(config).query(sql, limit=, caller=)` | class | Guarded read-only SQL: row limit, timeout, audit line. Returns `LakeQueryResult` (rows, `truncated`, `as_of_seq`, `snapshot_id`) |
| `lake_query(sql, limit=, lake_dir=, caller=)` | function | The MCP tool body (the registration arrives with P0-I4) |
| `GuardError`, `QueryError`, `LakeError` and subclasses | exceptions | A refusal; a failed or timed-out statement; everything else |

Demo queries: `dev/lake/queries/*.sql` (events by type, records overview, links by relation, valve sizes, pset coverage, as-of seq), tested by `tests/test_demo_queries.py`. A rebuild resets the sync count (`syncs 1`).

CLI: `tl lake sync | rebuild --yes | status | tables | query SQL [--limit N] [--json]` (in `tl-cli`).

## How a sync works
1. Read the ledger head and the lake watermark (`max(_tl_sync.last_seq)`). Refuse if the lake is past the head, or if the event at the watermark differs (hash) between lake and ledger.
2. In one DuckLake transaction: create tables or add new columns (a new promoted pset column reloads its silver table in full, because the ledger back-fills it without touching `last_seq`); append events `watermark+1..head` to bronze, failing on a gap; for each silver table, replace the rows whose `last_seq` is past the watermark (`pset_values` is replaced per changed record); insert the `_tl_sync` row `(snapshot_id, first_seq, last_seq, synced_at)`.
3. COMMIT, then check that the committed snapshot is the one the row names.

A crash before COMMIT changes nothing. A full rebuild equals the incremental result (property test `test_rebuild_equals_incremental.py`).

## Tables
| Table | Layer | Source | Notes |
|---|---|---|---|
| `events` | bronze | ledger `events` | Same columns and order as the ledger table; `payload`, `recorded_at` and `effective_at` are text exactly as hashed, so `event_hash` re-verifies. An archive segment's `events.parquet` must use the same names |
| `cur_core_record` | silver | `cur_core_record` | Generated columns plus promoted `pset__<pset>__<property>` columns |
| `links` | silver | `cur_links` | |
| `pset_values` | silver | `cur_pset_values` | Long form |
| `_tl_sync` | control | | `snapshot_id, first_seq, last_seq, synced_at`: one row per sync |

Types come from the generated Postgres DDL: `BOOLEAN`, `BIGINT`, `DOUBLE`, `VARCHAR`, and `TIMESTAMP` holding UTC. A promoted boolean column is `BIGINT` when the ledger is SQLite (SQLite stores 0 and 1).

## `lake_query` guard
Exactly one statement, parsed by DuckDB; SELECT only; tables must be lake tables or CTEs visible at that point; table functions limited to `range`, `generate_series`, `unnest`, `generate_subscripts`; no `getenv`, `current_setting`, `read_*`, `glob`, `duckdb_*` and similar. Refused: stacked statements, DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET, EXPLAIN, file-reading functions and other catalogs. Two more layers sit behind it: the catalog is attached READ_ONLY, and external file access is switched off and the configuration locked before the statement runs. Default limit 100, maximum 10 000, timeout 30 s. Every call, accepted or refused, appends a line to `lake_query.log.jsonl`.

## Depends on / used by
- Depends on: `duckdb==1.5.5`, `duckdb-extensions`, `duckdb-extension-ducklake` (all MIT; the extension wheel's version must equal duckdb's), `sqlalchemy`, `tl_schema` (generated DDL), `tl_core`.
- Used by: `tl_cli` (`tl lake`), the `lake_query` MCP tool (P0-I4 and later), `just demo P0-I7-lake`. Runbook: `docs/runbooks/lake-sync.md`.

## Commands
```
just test packages/tl-lake
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
- Bronze is not yet partitioned by company, project and date; no compaction or snapshot expiry; gold marts and `hist_*` tables are later increments.
- Not yet run against a Postgres ledger (P0-I5). Loading bronze from archive Parquet segments directly is not built; restore the ledger, then sync.

## Status
Introduced in P0-I7 (workstream B). Last interface change: P0-I7.
