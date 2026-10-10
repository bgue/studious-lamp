# Report — P0-I7 workstream B (DuckLake v0 and `lake_query`)

Status: interim. T23 (MCP registration) waits for P0-I4 on the trunk; the final demo and `docs/reports/P0-I7.md` wait for workstream A.

## Outcome
Objective met for everything that does not depend on P0-I4, P0-I5 or workstream A: yes. Demo path (`just demo P0-I7-lake`) verified on a temporary ledger: yes. Not yet run against a Postgres ledger.

`tl-lake` copies the ledger into a DuckLake lake incrementally by seq. One sync is one DuckLake snapshot, with the `_tl_sync(snapshot_id, first_seq, last_seq, synced_at)` row written in the same transaction. Bronze is `events`; silver is `cur_core_record`, `links` and `pset_values`, mapped from the generated schema with promoted pset columns. A full rebuild equals the incremental result (property test, mutation-checked). `lake_query` is a guarded, row-limited, timed, logged function that states the seq it reflects. `tl lake sync|rebuild|status|tables|query` expose it.

## Supervisor-built pieces (awaiting orchestrator or human review)
| Piece | Files | Commit |
|---|---|---|
| S1 bootstrap, sync engine, watermark and transaction boundary, silver mapping | `packages/tl-lake/src/tl_lake/{duck,sync,ingest,schema,source,status,config,errors}.py` | 524acae |
| S2 guard | `packages/tl-lake/src/tl_lake/guard.py` | 530c8d5 |
| S3 query service | `packages/tl-lake/src/tl_lake/query.py` | 999a51f, d1a1dd1 |
| S4 property test and scaffolds | `tests/test_rebuild_equals_incremental.py`, `tests/builder.py` | 999a51f |
| S5 lake demo | `dev/demos/P0-I7-lake.sh` | d1a1dd1 |

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I7-T20 `tl lake` commands | merged | 1 (pass) | `status` also treats `synced_at is None` as uninitialised (type narrowing), accepted |
| P0-I7-T21 demo queries | merged | 1 (pass) | reviewer mutation-checked an ORDER BY |
| P0-I7-T22 runbook | taken over | 1 (escalate) | unanswered business-hours question and process wording; orchestrator ruled, supervisor finished (29a1242) |
| P0-I7-T23 `lake_query` MCP registration | deferred | | needs the `tl_mcp` server from P0-I4 |

## Gates
| Gate | Result |
|---|---|
| `just check` | green on `p0/i7b` (d1a1dd1) |
| `just test` | green, 1592 passed (d1a1dd1) |
| `just test-parity` | not applicable: no adapter changed; Postgres untested until P0-I5 |
| `just demo P0-I7-lake` | passes |

## Deviations from plan
- Bronze `events` keeps `recorded_at`, `effective_at` and `payload` as text (exactly as hashed) instead of typed timestamps and JSON, so hashes re-verify from the lake. WS-A's `events.parquet` must use the same names and text types.
- `tl-cli` gained a dependency on `tl-lake` and `uv.lock` changed; both were done by the supervisor before dispatch.
- Silver timestamps are `TIMESTAMP` holding UTC (not `TIMESTAMPTZ`), because fetching zone-aware values in Python needs pytz, which is not a dependency.

## Escalations and decisions
- T22: see the table above and `docs/tickets/P0-I7/B-PLAN.md` (*Blocked / Decision*).
- Guard: a leading `--` comment line is accepted; tests show comments cannot hide a second statement.

## Learnings
Appended: L-P0-I7-B1 to B6. T20 proposal "a rebuild resets the sync count" went into the package README; "truncated line uses `result.limit`" and the AGENTS.md question need no entry (the tl-cli rule was added to `packages/tl-cli/AGENTS.md`). T21's fixture-scope note is in B6.

## Docs
`packages/tl-lake/README.md`, `packages/tl-lake/AGENTS.md`, `packages/tl-cli/README.md` and `AGENTS.md`, `docs/runbooks/lake-sync.md` and its index line, `docs/tickets/P0-I7/B-PLAN.md`.

## Dependencies and licences (ADR-0006)
`duckdb==1.5.5` MIT, `duckdb-extensions` MIT, `duckdb-extension-ducklake` MIT (installed metadata).

## Follow-ups filed
- T23 `lake_query` MCP tool registration (after P0-I4).
- Run the sync property test and `read_snapshot` against Postgres (after P0-I5); gap-free seq on Postgres sequences needs checking.
- Load bronze directly from archive Parquet segments; partition bronze by company, project and date; compaction and snapshot expiry; PostgreSQL catalog for production (one writer per DuckDB file today).
- The lake property test takes about a minute on an idle machine; consider a marker if the suite grows.

## Cost notes
Not measured.
