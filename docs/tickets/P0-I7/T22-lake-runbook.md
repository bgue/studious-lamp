# P0-I7-T22 — Runbook: lake sync and lake_query

Status: ready
Tier: haiku
Labels: docs
Depends on: —
Branch: `p0/i7b-t22-lake-runbook`

## Goal
`docs/runbooks/lake-sync.md` tells an operator how to run, check and repair the DuckLake copy, and what to do when `lake_query` refuses a statement or the lake is stale, using the
runbook template and only the facts pasted below.

## Brief references (pasted)
> **28.1:** The lakehouse is the analytics copy of the system: never a source of truth, always rebuildable from the ledger archive and current-state tables.
> **28.3:** `tl lake sync` runs incrementally. It reads events after the last synced `seq`, updates silver, and commits as one DuckLake snapshot. Every lake snapshot records the ledger `seq` range it covers. Full rebuild = replay the ledger archive into a new lake.
> **11.3 / 28.4:** agents get a read-only `lake_query` MCP tool (SQL with row limits, allowed catalogs only, logged).

### Facts to use (verified by the supervisor; do not add others)
- Commands (from the repo root; the ledger is `TL_DB`, default `./dev/data/tl.db`; the lake directory is `TL_LAKE_DIR`, default `./dev/data/lake`, git-ignored):
  - `uv run tl lake sync`: copies new events and changed records, one DuckLake snapshot per sync. Prints `synced seq A..B (N events) in snapshot S` or `lake is up to date as of seq N`.
  - `uv run tl lake status`: prints `as of seq N (snapshot S, synced <time>)`, `syncs N` and a row count per table; `lake not initialised: run `tl lake sync`` before the first sync.
  - `uv run tl lake tables`: tables and columns. `uv run tl lake query "SELECT ..." [--limit N] [--json]`: runs one SELECT and ends with `as of seq N (snapshot S)`.
  - `uv run tl lake rebuild --yes`: deletes the lake's catalog and Parquet files and loads everything again from the ledger. The audit log is kept.
- Files under the lake directory: `catalog.ducklake` (DuckDB catalog), `data/` (Parquet), `lake_query.log.jsonl` (one JSON line per `lake_query` call: `ts`, `caller`, `sql`, `limit`, `outcome` = `ok`/`refused`/`error`, `detail`, `rows`, `as_of_seq`), `.lake.lock`, `tmp/`.
- A sync is one transaction: if it fails nothing is committed and the next sync starts from the same place. The watermark is the greatest `last_seq` in the lake table `_tl_sync`.
- Time travel: `SELECT ... FROM cur_core_record AT (VERSION => <snapshot_id>)`; snapshot ids are in `_tl_sync`.
- Errors and what they mean:
  - `the lake is busy: could not take the sync lock in 60 s` (or `query lock`): another sync or query holds the lock file; wait and retry. A DuckDB catalog file allows one writer or many readers, so the lock serialises them.
  - `the lake is at seq N but the ledger head is M`, or `the lake and the ledger disagree about the event at seq N`: the lake was built from a different ledger (for example the ledger was restored from an older backup). Run `uv run tl lake rebuild --yes`.
  - `the ledger has a gap in seq`: the ledger violates its gap-free contract; stop and escalate, do not rebuild.
  - `refused: ...` from `tl lake query` or the MCP tool: the guard allows one SELECT over lake tables. DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET, stacked statements, file-reading functions (`read_csv`, `read_parquet`, `read_text`, `glob`) and other catalogs are refused by design. Rewrite as a SELECT over the tables from `tl lake tables`.
  - `the query ran longer than 30 s`: narrow the query; the limit is 100 rows by default and 10 000 at most.
- Stale lake: the lake only changes when `tl lake sync` runs; a query states the seq it saw. If the number is behind `tl events tail`, run a sync.
- Recovery after a crash during a sync needs nothing: rerun `tl lake sync`.
- The lake is never a backup: restoring the ledger (see the restore runbooks of this increment) is separate; after a restore run `tl lake sync`, and `tl lake rebuild --yes` if it reports a disagreement.

## Interfaces (verbatim from the repo at the branch point)
Not applicable (documentation only).

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/templates/runbook.md`
- `docs/runbooks/` (look at one existing runbook for tone; read at most one)
may explore: (none)

## Allowed paths
- `docs/runbooks/lake-sync.md` (create)
- `docs/reports/P0-I7/P0-I7-T22.md` (create: your report; commit it)

## Steps
1. Copy the structure of `docs/templates/runbook.md`; delete guidance lines; leave no placeholders.
2. Fill it from the facts above. Commands must be copy-pasteable from the repo root. No model names, no secrets.
3. Commit the runbook and the report.

## Acceptance
```
test -f docs/runbooks/lake-sync.md
grep -c '<' docs/runbooks/lake-sync.md
just check
```
Expected: the file exists; `just check` exits 0. (The `grep` count is only for you to confirm that any `<...>` left is a deliberate placeholder in a command, such as `<snapshot_id>`.)

## Tests to add
None.

## Report requirements
Standard report. List every fact you used and confirm you added none.

## Escalation triggers
- Stop and report *Blocked* if the template needs a fact that is not above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
