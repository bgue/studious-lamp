# Increment plan — P0-I8 workstream D: performance pass

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §15 (non-functional targets), §17 risks R1 (rebuild time) and R2 (pset query performance), §5.4 (current-state tables), §10.2 (query language)
Branch: `p0/i8d` (base `p0/i8`); ticket ids `P0-I8-T60` to `T79`, supervisor pieces `P0-I8-S60` onwards

## Objective
Measure the §15 targets on a seeded 100k-record project on SQLite and Postgres, find the hot spots with `EXPLAIN` and profiling, fix them through the schema, the generators, the query compiler and the projectors, and report every number with its machine and its before and after. The targets: grid scroll and filter under 150 ms (p95) at up to 100k rows; a change visible to another client in under 2 s; a full projection rebuild and a per-projector rebuild that fit a maintenance window (hours, not days). A miss that cannot be fixed here is recorded as a deviation with its cause and a proposed fix. Settings (workstream A) and extension types (workstream B) are not touched.

## Demo
`just demo P0-I8-D` (script `dev/demos/P0-I8-D.sh`): seeds a small project (a few thousand records) on SQLite and, when reachable, Postgres; runs the same bench suite at that scale; prints the table of the §15 targets with median, p95 and the verdict. Under three minutes. The 100k run is `just bench-seed` once, then `just bench`; the runbook is `docs/runbooks/performance-benches.md`.

## Decisions taken in this workstream
| # | Decision | Why |
|---|---|---|
| D1 | The bench is a pytest suite under `tests/bench/` with the marker `bench`. The root `conftest.py` deselects it unless `-m` names `bench`, so `just test` and `just test-parity` never run it. | D13 of the fanout. The deselect also covers a bench that is mistakenly marked `parity`. |
| D2 | The generator writes `Record.Created` (with its psets), `Workflow.Transitioned` and `Link.Added` through `BaseUnitOfWork.append`, 500 records per transaction, with a counter clock and counter ids. Both dialects end with the same ledger head hash. | Not the simulator, not the API (minutes, not hours). The equal hash proves the dataset and both adapters. |
| D3 | Datasets are cached: `dev/data/bench/sqlite-<n>.db` and the Postgres database `tl_test_bench_<n>`, each with a `tl_bench_meta` row written last. The query benches are read-only; the realtime bench works on a private copy; rebuilds are idempotent and check the table row counts. | Seeding takes about 8 minutes (SQLite) and about an hour (Postgres) at 100k records. |
| D4 | The 100k full rebuild is measured once per dialect (`just bench-rebuild`); the repeated rebuild measurements run on a 10k-record dataset. | One full rebuild on Postgres exceeds the 15-minute budget of a bench run. The 10k runs give the spread and the events per second. |
| D5 | Index definitions go through a class annotation `tl:ix_<name>` read by the DDL generator (composite columns, `desc`, and `empty_last(col)`). | `tl:indexed` could only index one column, and the record queries order by an expression no plain index serves. |
| D6 | Pset and link predicates that must hold compile to `id IN (set)`; negations stay correlated `NOT EXISTS`. | `IN (set)` is built once from a covering index; `NOT IN (big set)` plans badly on Postgres. |
| D7 | `cur_link_counts` is not used to answer `count(linked)`. | The query language is documented over `cur_links`, and the query tests seed `cur_links` alone. Recorded as the proposed fix of a deviation. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S60 | Bench harness, 100k generator, measurement method, `just bench*` recipes | The method and the dataset decide what every number means | self | done |
| S61 | `tl:ix_` annotations in the DDL generator and the index definitions in `schema/core` | Generator logic and `schema/**` | orchestrator | done |
| S62 | Query compiler: sets instead of per-record probes; ordering an index can serve | Query compiler (Sonnet-authored list) | orchestrator | done |
| S63 | Per-target measurements, before and after, both dialects | The report depends on them | self | in progress |
| S64 | Runbook, package README notes, demo script, perf report, workstream report | Closes the workstream | self | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T60 | Bench report renderer (results files to markdown tables) | haiku | S60 | ready | |
| T61 | PsetProjector: one insert per record, no reads for a new record | haiku | S62 | ready | |
| T62 | LinkProjector: refresh link counts with one upsert | haiku | S62 | ready | |

## Order of work
1. S60 harness and generator, seed 100k on both dialects (in the background).
2. Baseline on SQLite; EXPLAIN on both dialects.
3. S61, S62 (fixes with before and after).
4. T61, T62 in the first batch; T60 in the second.
5. Baseline and after on Postgres once its seed is done; merge `p0/i8` again before the final measurement.
6. Runbook, demo, reports.

## Risks and escalation triggers
- The container is shared: load average was 3 to 10 during measurements. Every result carries the load before each round and the spread between rounds.
- The Postgres seed takes about an hour; the Postgres numbers come last.
- The query compiler and the DDL generator are Sonnet-authored areas: S61 and S62 are marked for orchestrator review before merge into the trunk.

## Blocked / Decision
(none)
