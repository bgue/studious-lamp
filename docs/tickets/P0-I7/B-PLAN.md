# Increment plan — P0-I7 workstream B (DuckLake v0 and `lake_query`)

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §28.1–§28.4, §11.3 (`lake_query`), §24.3 (Parquet segments, for the bronze column contract)
Branch: `p0/i7b` (base `p0/i7`)
Fanout: `docs/tickets/P0-I7/FANOUT.md` (decisions D1–D6 are binding)

## Objective
A new `tl-lake` package copies the ledger into a DuckLake lake incrementally by `seq`. Each sync is one DuckLake snapshot, and a `_tl_sync` row naming that snapshot and the seq range
commits in the same transaction. Bronze is `events`; silver is `cur_core_record`, `links` and `pset_values`, mapped from the generated schema with promoted pset columns. A guarded,
logged, row-limited `lake_query` service answers read-only SQL and states the seq it reflects. `tl lake sync|status|query` expose them.

## Demo
```
just demo P0-I7-lake        # dev/demos/P0-I7-lake.sh, included by the final P0-I7 demo
```
It seeds a small ledger, runs `tl lake sync`, `tl lake status`, the queries in `dev/lake/queries/`, a time-travel query, and a refused `DROP TABLE`. Each result ends with `as of seq N`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | DuckLake bootstrap (`duck.py`), sync engine, watermark and transaction boundary (`sync.py`, `ingest.py`), silver mapping (`schema.py`) | Sync/merge-class engine; the transaction boundary defines correctness (§28.3) | orchestrator or human | merged on `p0/i7b` |
| S2 | `lake_query` guard (`guard.py`) | Security-sensitive, open to agents (FANOUT D6) | orchestrator or human | merged on `p0/i7b` |
| S3 | `lake_query` service (`query.py`): sandbox, row limit, timeout, audit log | Same | orchestrator or human | merged on `p0/i7b` |
| S4 | Property test: incremental equals full rebuild; test scaffolds; CLI stub and provided test | Test scaffolds first | — | merged on `p0/i7b` |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I7-T20 | `tl lake` commands | haiku | S1–S3 | ready | |
| P0-I7-T21 | Lake demo queries and their test | haiku | S1–S3 | ready | |
| P0-I7-T22 | Runbook: lake sync and `lake_query` | haiku | — | ready | |
| P0-I7-T23 | `lake_query` MCP tool registration | haiku | P0-I4 on the trunk | draft (deferred) | |

Haiku-ability checklist (`01-tiers.md` §6), each ticket: files to read ≤ 6, interfaces already in the repo, a test or acceptance commands, diff ≤ 400 lines over ≤ 5 files, none of
the Sonnet-authored rows, no `schema/**`, migration, dependency or public-interface change, verifiable from the diff and commands. T20: 3 files read, stub and provided test in the
repo; T21: SQL plus one test file with the expected rows pinned; T22: documentation from pasted facts. All yes. The sync engine, the silver mapping and the guard failed row 5, so the
supervisor built them. The `tl-cli` dependency on `tl-lake` (and `uv.lock`) is added by the supervisor before dispatch (row 6).

## Order of work
1. S1 to S4 (done), then T20, T21 and T22 in parallel (disjoint paths).
2. After they merge: `dev/demos/P0-I7-lake.sh`, `tl-lake` README, learnings.
3. After P0-I4 is on the trunk and merged here: T23 (MCP registration), then the final demo and report after WS-A merges.

## Risks and escalation triggers
- DuckLake is young (R13). The extension version is pinned to the `duckdb` wheel; the fallback is plain Parquet plus views.
- One writer at a time per catalog file; the lock file serialises sync and query. Postgres as the catalog (prod) removes this.
- Postgres support (P0-I5): `read_snapshot` sets REPEATABLE READ and all ledger reads are portable SQLAlchemy, but it is untested on Postgres until P0-I5 lands.
- Bronze `events` columns must match WS-A's `events.parquet`: names and order of the ledger `events` table, `recorded_at`/`effective_at`/`payload` as text. Raised in the relay NOTE.

## Blocked / Decision
(none)
