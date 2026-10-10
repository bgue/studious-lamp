# Report — P0-I7 workstream B (DuckLake v0 and `lake_query`)

Status: interim. T23 (MCP registration) waits for P0-I4 on the trunk; the final demo and `docs/reports/P0-I7.md` wait for workstream A.

## Outcome
Objective met for everything that does not depend on P0-I4 or workstream A: yes. Demo path (`just demo P0-I7-lake`) verified on a temporary ledger: yes. The lake tests also pass on a Postgres ledger (238 tests with `--adapters sqlite,postgres`); the CLI still opens SQLite only.

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
| P0-I7-T23 runbook section for `lake_query` over MCP | merged | 1 (pass) | the code part (register the tool) failed Haiku-ability row 6 (public interface of `tl_mcp`), so the supervisor built it as S8 |

## Gates
| Gate | Result |
|---|---|
| `just check` | green on `p0/i7b` (d1a1dd1) |
| `just test` | green, 3159 passed after merging p0/i7 (P0-I5 and P0-I4) |
| `uv run pytest packages/tl-lake --adapters sqlite,postgres` (`TL_REQUIRE_POSTGRES=1`) | green, 238 passed |
| `just demo P0-I7-lake` | passes |

## Deviations from plan
- Bronze `events` keeps `recorded_at`, `effective_at` and `payload` as text (exactly as hashed) instead of typed timestamps and JSON, so hashes re-verify from the lake. WS-A's `events.parquet` must use the same names and text types.
- `tl-cli` gained a dependency on `tl-lake` and `uv.lock` changed; both were done by the supervisor before dispatch.
- Silver timestamps are `TIMESTAMP` holding UTC (not `TIMESTAMPTZ`), because fetching zone-aware values in Python needs pytz, which is not a dependency.

## Review round (16d1828): changes applied
Sync (S1) passed with low items; the guard (S2/S3) needed changes. All applied in one round.
| # | Item | Change |
|---|---|---|
| 1 | CTE named like a data file got past the guard (PoC) | `guard.py`: CTE names are scoped as SQL scopes them (not in the CTE's own body; only the recursive term of a recursive CTE sees its name); any table or CTE name containing `/ \\ . * ? [` or a control character is refused. Tests: the PoC, a glob variant, scoping and recursion cases |
| 2 | Not every call audited | `query.py`: the whole call is wrapped; any exception writes one line with `outcome` and `error_class`; every line has the same keys including `rows` (0 when refused or errored). Test covers lock timeout, bad surrogate, non-text SQL, NUL |
| 3 | U+2028 / U+0085 could split a record | Audit lines are written with `ensure_ascii=True`; test with `str.splitlines()` |
| 4 | Timeout not a hard bound, no byte cap | Result byte cap, 8 MiB by default (`max_bytes`), `truncated_by` = `limit` or `bytes`; rows are fetched in batches; timeout documented as best effort. CLI prints the number of rows returned |
| 5 | NUL in SQL | `check_sql` refuses NUL |
| 6 | DuckDB errors and paths | `QueryError` carries a short `ClassName: message` and `error_class`; the lake directory becomes `<lake>` and other absolute paths `<path>` in refusal and error text and in the audit line. Time travel stays allowed and is documented |
| 7 | Property test used one scope and counts | Two scopes (`OTHER_SCOPE`); lake rows compared with the ledger's rows by content (sorted, values converted by the loader); mutation re-checked |
| 8 | Post-COMMIT error said "nothing was committed" | Reworded; `LakeSyncError` docstring fixed; test |
| 9 | Tip-only verification | Stated in the README: by design, full-chain integrity is `tl archive verify` (WS-A) |

## lake_query over MCP (S8, P0-I4 merged into p0/i7b, 17d714b)
`tl_mcp.build_server(..., lake_dir=None)` registers the read-only tool `lake_query(sql, limit=100)` and the resource `tl://lake/schema`. It forwards to `LakeQueryService` (limit at most 1000, answer cap 1 MiB, audit `caller` = the server's actor). `GuardError` becomes a `ToolError` starting `refused:`, any other `LakeError` a `ToolError`; the authorise hook is called first as `mcp.lake_query` on `lake:main`; inputs are bounded by the schema (SQL 1 to 20 000 characters). `python -m tl_mcp --lake-dir DIR` selects the lake. Existing tl-mcp tests were updated for the new tool and resource; `tests/test_mcp_lake_query.py` is new (refusals, limits, audit caller, unsynced lake, bounds, hook order).

## Postgres (P0-I5 merged into p0/i7b, bcaf5b6)
- `read_snapshot` now delegates to `tl_adapters.db.read_tx` (REPEATABLE READ READ ONLY on Postgres).
- SQLAlchemy reflection fails on the Postgres adapter (JSON returned as text). The sync reads column names with `table_columns`, selects with quoted explicit columns, and types promoted columns from the effective schema (inferred from the first value if no schema knows them). JSON columns are stored as canonical text on every adapter.
- Tests build their ledger from the `new_db` fixture and `tl_adapters.db`, so they carry the `parity` marker and run on both adapters; `tests/test_parity_sync.py` adds a scripted multi-scope history (promoted columns mid-history, retract, void, unset) compared with a single load and with the ledger, and re-verifies every bronze event hash from the lake. The Hypothesis property test stays on SQLite.
- Merge conflicts resolved by keeping both sides: `tl-cli` `main.py` and README (lake, file and webhook commands), `uv.lock` regenerated.

## Escalations and decisions
- T22: see the table above and `docs/tickets/P0-I7/B-PLAN.md` (*Blocked / Decision*).
- Guard: a leading `--` comment line is accepted; tests show comments cannot hide a second statement.

## Learnings
Appended: L-P0-I7-B1 to B8. T20 proposal "a rebuild resets the sync count" went into the package README; "truncated line uses `result.limit`" and the AGENTS.md question need no entry (the tl-cli rule was added to `packages/tl-cli/AGENTS.md`). T21's fixture-scope note is in B6.

## Docs
`packages/tl-lake/README.md`, `packages/tl-lake/AGENTS.md`, `packages/tl-cli/README.md` and `AGENTS.md`, `docs/runbooks/lake-sync.md` and its index line, `docs/tickets/P0-I7/B-PLAN.md`.

## Dependencies and licences (ADR-0006)
`duckdb==1.5.5` MIT, `duckdb-extensions` MIT, `duckdb-extension-ducklake` MIT (installed metadata).

## Follow-ups filed
- T23 `lake_query` MCP tool registration (after P0-I4).
- Gap-free seq on Postgres sequences after rolled-back transactions needs checking by the P0-I5 owner (the sync refuses a gap); the Hypothesis property test runs on SQLite only.
- `tl lake` opens the ledger as a SQLite path (`_ledger_snapshot`); switch it to `tl_adapters.db.make_engine` when the CLI takes a Postgres URL.
- Load bronze directly from archive Parquet segments; partition bronze by company, project and date; compaction and snapshot expiry; PostgreSQL catalog for production (one writer per DuckDB file today).
- The lake property test takes about a minute on an idle machine; consider a marker if the suite grows.

## Cost notes
Not measured.
