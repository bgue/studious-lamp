# P0-I7-T23 — Runbook section: `lake_query` over MCP

Status: ready
Tier: haiku
Labels: docs
Depends on: the supervisor's `lake_query` MCP tool (S8, merged into the base of this branch)
Branch: `p0/i7b-t23-lake-query-docs`

## Goal
`docs/runbooks/api-and-mcp-dev.md` gets a section that tells a developer how to give an agent the `lake_query` tool: start the MCP server with a lake, sync the lake, what the tool
answers, how it refuses, and where the audit log is. `docs/runbooks/lake-sync.md` gets one pointer line to that section.

Why this was not a code ticket: the original plan listed "T23: `lake_query` MCP registration" for an implementer. The Haiku-ability checklist (`01-tiers.md` §6) row 6 fails for it, because it adds a parameter to the public `build_server` of `tl_mcp` and a tool to the MCP surface, so the supervisor built it (S8) and this ticket documents it.

## Brief references (pasted)
> **11.3 / 28.4:** agents get a read-only `lake_query` MCP tool (SQL with row limits, allowed catalogs only, logged).
> **Build spec:** runbooks follow `docs/templates/runbook.md`; commands are copy-pasteable from the repo root; no model names, no secrets.

### Facts to use (verified by the supervisor; add no others)
- Start the MCP server on stdio with a lake: `uv run python -m tl_mcp --actor agent:analyst --lake-dir ./dev/data/lake` (`--lake-dir` defaults to `TL_LAKE_DIR`, else `./dev/data/lake`; `--db` defaults to `TL_DB`). The server is read-only; the lake is opened for each call and may not exist yet.
- Fill the lake first: `uv run tl lake sync` (see `docs/runbooks/lake-sync.md`). Before the first sync the tool answers with a tool error that says to run `tl lake sync`.
- Tool `lake_query(sql, limit=100)`: one SELECT (or WITH ... SELECT) over the tables `events`, `cur_core_record`, `links`, `pset_values`, `_tl_sync`. `sql` is 1 to 20 000 characters; `limit` is 1 to 1000, default 100. The answer is `{columns, rows, row_count, truncated, truncated_by, limit, as_of_seq, snapshot_id, as_of}`; `truncated_by` is `limit` (more rows existed) or `bytes` (the answer reached 1 MiB). `as_of_seq` is the ledger seq the lake reflected, and the lake can be behind the ledger until the next sync. Time travel: `SELECT ... FROM cur_core_record AT (VERSION => <snapshot_id>)`; snapshot ids are in `_tl_sync`.
- Resource `tl://lake/schema` lists the tables and their columns as JSON.
- Refusals are tool errors whose text starts with `refused:`. Refused by design: DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET, EXPLAIN, stacked statements, file functions (`read_csv`, `read_parquet`, `read_text`, `glob`), table names that look like paths, and other catalogs. A failing statement is a tool error with the DuckDB error class and a short message. A query longer than 30 s is interrupted.
- Every call, accepted or refused, appends one JSON line to `<lake dir>/lake_query.log.jsonl` with `ts`, `caller` (the server's `--actor`), `sql`, `limit`, `outcome` (`ok`, `refused` or `error`), `detail`, `error_class`, `rows`, `truncated`, `as_of_seq`, `snapshot_id`, `elapsed_ms`.
- Identity is the Phase 0 dev stub of ADR-0005: the actor is fixed per server and every actor may call the tool; there is no permission model yet.

## Interfaces (verbatim from the repo at the branch point)
Not applicable (documentation only).

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/runbooks/api-and-mcp-dev.md`
- `docs/runbooks/lake-sync.md`
- `docs/templates/runbook.md`
may explore: (none)

## Allowed paths
- `docs/runbooks/api-and-mcp-dev.md` (edit: add one section; keep the existing structure and headings)
- `docs/runbooks/lake-sync.md` (edit: one pointer line under *Related*)
- `docs/reports/P0-I7/P0-I7-T23.md` (create: your report; commit it)

## Steps
1. Read `api-and-mcp-dev.md` and follow its heading style. Add a section "Give an agent `lake_query`" with numbered steps from the facts above (start the server, sync, call the tool, read a refusal, read the audit log), each with a copy-pasteable command and its expected result.
2. Add the pointer line to `lake-sync.md`.
3. Run the acceptance commands, write the report, commit everything.

## Acceptance
```
grep -n "lake_query" docs/runbooks/api-and-mcp-dev.md docs/runbooks/lake-sync.md
just check
```
Expected: the section and the pointer exist; `just check` exits 0.

## Tests to add
None.

## Report requirements
Standard report. List every fact you used and confirm you added none.

## Escalation triggers
- Stop and report *Blocked* if the existing runbook structure cannot take a new section without rewriting it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
