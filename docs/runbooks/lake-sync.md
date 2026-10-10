# Runbook — lake sync, lake status and lake_query refusals

Purpose: run, check and repair the DuckLake analytics copy of the ledger, and handle a refused `lake_query` statement or a stale lake. Brief: §28.1, §28.3, §11.3, §28.4.

The lake is an analytics copy, never a source of truth, and never a backup. It can always be rebuilt from the ledger. All commands run from the repo root.

## When to use
- Trigger: `uv run tl lake status` reports `lake not initialised`, or a query reports an old seq (the lake is stale).
- Trigger: `the lake is busy: could not take the sync lock in 60 s` (or the same message with `query lock`).
- Trigger: `the lake is at seq N but the ledger head is M`, or `the lake and the ledger disagree about the event at seq N`.
- Trigger: `the ledger has a gap in seq`.
- Trigger: `refused: ...` from `uv run tl lake query` or from the `lake_query` MCP tool.
- Trigger: `the query ran longer than 30 s`.
- Trigger: a crash during a sync, or a ledger restore has finished.

## Before you start
- Access needed: read access to the ledger file (`TL_DB`, default `./dev/data/tl.db`), and read and write access to the lake directory (`TL_LAKE_DIR`, default `./dev/data/lake`, git-ignored).
- The lake directory holds `catalog.ducklake` (DuckDB catalog), `data/` (Parquet), `lake_query.log.jsonl` (one JSON line per `lake_query` call), `.lake.lock` and `tmp/`.
- Safe to run during business hours: `tl lake sync` yes (it is incremental and holds the lake lock only for the sync transaction; queries wait for the lock and then see the new snapshot). `tl lake rebuild --yes` no (it wipes and reloads, queries are blocked or return nothing until it finishes, and on a large ledger it runs for minutes): run it out of hours, or after telling users.

## Steps
1. Check the lake state. The output shows the seq the lake covers:
   ```
   uv run tl lake status
   ```
   Expected: `as of seq N (snapshot S, synced ...)`, where the last part is the time of the last sync; then `syncs N` and a row count per table. Before the first sync it prints `lake not initialised: run `tl lake sync`` instead.

2. Bring the lake up to date. A sync copies new events and changed records and commits them as one DuckLake snapshot. Each snapshot records the ledger seq range it covers:
   ```
   uv run tl lake sync
   ```
   Expected: `synced seq A..B (N events) in snapshot S`, or `lake is up to date as of seq N` when nothing is new.
   If a sync fails or the process crashes, nothing is committed. Run the same command again; it starts from the same place and needs no cleanup.

3. List the lake tables and their columns:
   ```
   uv run tl lake tables
   ```

4. Query the lake. A query accepts exactly one SELECT over the lake tables from step 3. Use `--limit` (default 100 rows, 10 000 at most) and `--json` if needed:
   ```
   uv run tl lake query "SELECT * FROM _tl_sync" --limit 20
   ```
   Expected: the rows, then a last line `as of seq N (snapshot S)`. The watermark is the greatest `last_seq` in `_tl_sync`.

5. Query the state as of an earlier snapshot. Snapshot ids are listed in `_tl_sync`:
   ```
   uv run tl lake query "SELECT * FROM cur_core_record AT (VERSION => <snapshot_id>)" --limit 20
   ```

6. Read the audit log of `lake_query` calls. Each line has `ts`, `caller`, `sql`, `limit`, `outcome` (`ok`, `refused` or `error`), `detail`, `rows` and `as_of_seq`:
   ```
   tail -n 20 "${TL_LAKE_DIR:-./dev/data/lake}/lake_query.log.jsonl"
   ```

7. If a query is `refused: ...`, rewrite it as one SELECT over the tables from step 3. These are refused by design: DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET, stacked statements, the file-reading functions `read_csv`, `read_parquet`, `read_text` and `glob`, and any other catalog.

8. If a query runs longer than 30 s, narrow it (fewer columns, a filter, a smaller `--limit`) and run it again.

9. If the sync or a query reports `the lake is busy: could not take the sync lock in 60 s` (or `query lock`), another sync or query holds the lock file. Wait and run the command again. The lock lets one writer or many readers use the DuckDB catalog file at a time.

10. If the sync reports `the lake is at seq N but the ledger head is M`, or `the lake and the ledger disagree about the event at seq N`, the lake was built from a different ledger, for example after the ledger was restored from an older backup. Rebuild the lake from the ledger (out of hours, or after telling users: queries are blocked while it runs):
    ```
    uv run tl lake rebuild --yes
    ```
    Expected: the lake's catalog and Parquet files are deleted and everything is loaded again from the ledger; the audit log is kept. Then run `uv run tl lake status` and check the seq.

11. If the sync reports `the ledger has a gap in seq`, stop. The ledger violates its gap-free contract. Do not rebuild. Stop and escalate to the platform on-call (see the runbook index).

12. After a ledger is restored, run a sync. Run step 10 only if the sync reports a disagreement:
    ```
    uv run tl lake sync
    ```

## Verify
- `uv run tl lake status` shows an `as of seq N` equal to the newest seq shown by `uv run tl events tail`. If the number is behind, run `uv run tl lake sync`.
- `uv run tl lake query "SELECT max(last_seq) FROM _tl_sync" --limit 1` returns the same N as the `as of seq N` line of that query.
- A second `uv run tl lake sync` prints `lake is up to date as of seq N`.

## Roll back
- A sync is one transaction. If it fails, nothing is committed, and the next sync starts from the same place. There is nothing to undo.
- The ledger is never modified by a sync or a rebuild.
- A rebuild deletes the lake's previous catalog and Parquet files. The previous lake cannot be restored; rebuild it from the ledger with `uv run tl lake rebuild --yes`.
- A lake query only reads. Refused and failed queries change nothing.

## Related
- Brief §28.1 (the lake is never a source of truth), §28.3 (incremental sync and snapshots), §11.3 and §28.4 (the read-only `lake_query` tool).
- `docs/runbooks/api-and-mcp-dev.md`, section "Give an agent `lake_query`": start the MCP server with a lake and let an agent call the `lake_query` tool.
- `docs/runbooks/rebuild-projections.md` rebuilds the ledger's current-state tables (`cur_*`). It is a different rebuild and does not rebuild the lake.
- `docs/runbooks/README.md` indexes the restore runbooks, which cover restoring the ledger.
