# Runbook — performance benches (brief §15 targets at 100k records)

Purpose: seed a 100k-record project on SQLite and Postgres, measure the §15 targets (grid scroll and filter, realtime, rebuild), and read the result. Brief: §15, §17 (R1, R2); decision D13 of `docs/tickets/P0-I8/FANOUT.md`.

## When to use
- After a change to a projector, the query compiler, an index, an adapter, the change feed or the TUI grid: run the benches before and after and compare.
- Before a release candidate: the 100k run and the numbers in `docs/reports/P0-I8-perf.md`.
- Not for CI: a full run takes about 15 minutes, and seeding takes up to an hour. The marker `bench` keeps the suite out of `just test` and `just test-parity`.

## Before you start
- Access needed: the repository, `uv`, `just`. For Postgres, the native cluster of ADR-0002 (`sudo pg_ctlcluster 16 main start`) and `TL_PG_URL` (default `postgresql://postgres:postgres@localhost:5432/tl_test`).
- Disk: about 1.1 GB for the SQLite 100k file and about 1.5 GB for the Postgres database, under `dev/data/bench/` (git-ignored) and the cluster.
- Safe to run during business hours: yes on a dev machine; no on a shared server. Never run two benches at once, and expect noise on a shared machine: every result stores the load average before each round.
- `TL_BENCH_DIALECTS=sqlite` skips Postgres everywhere.

## Steps
1. Seed once (idempotent: it does nothing when the datasets exist). SQLite 100k takes about 8 minutes; Postgres 100k about an hour (about 29 records per second; statements, not data, dominate).
   ```
   just bench-seed
   ```
   Expected: `sqlite: 360455 events, generator v1` and the same for `postgres`, then the 10k datasets used for the repeated rebuilds. `uv run python tests/bench/bench_data.py status --records 100000` shows what exists; `drop` removes a dataset.
2. Run the benches (grid queries, headless TUI grid, realtime, rebuild at 10k):
   ```
   just bench
   ```
   Expected: `bench results: dev/data/bench/results/<time>-bench-100000.json`. Settings: `TL_BENCH_RECORDS`, `TL_BENCH_REBUILD_RECORDS`, `TL_BENCH_ROUNDS` (3), `TL_BENCH_SAMPLES` (20), `TL_BENCH_LABEL`, `TL_BENCH_DIALECTS`.
3. Render the tables of the report:
   ```
   uv run python tests/bench/bench_report.py dev/data/bench/results/<file>.json
   uv run python tests/bench/bench_report.py --compare <before>.json <after>.json
   ```
4. The full 100k rebuild, once per dialect (about 9 minutes on SQLite; tens of minutes on Postgres), run on its own:
   ```
   just bench-rebuild
   ```
5. The small demo (2000 records, about two and a half minutes the first time): `just demo P0-I8-D`.

## How a number is made
- A scenario is a function of the sample number, so pages, filter values and record keys vary between calls.
- 3 untimed warm-up calls, then `TL_BENCH_ROUNDS` rounds of `TL_BENCH_SAMPLES` timed calls. The median and p95 are over all timed calls (nearest rank); the p95 of each round and the load average before it are stored, so a round hit by another process shows.
- Grid: the same `EmbeddedClient` calls the TUI grid makes (`list_records`, `query_records` plus `count_records`, 200 rows per page). The filter figure is count plus first page, what the filter bar does. Paging beyond the grid's 5000-row cap and the 5000-row reload are shown but are not part of the verdict.
- TUI grid: `RecordGrid` in a headless Textual pilot at 120x45; wall-clock on the UI thread.
- Realtime: the real API under uvicorn on loopback with the seeded database behind it (a private copy). Client A writes, client B holds `GET /stream`. "API write" reaches the stream through the in-process bus; "other process write" commits through its own engine and reaches it only through the change-feed poller (0.25 s interval).
- Rebuild: `rebuild_projections` resets and replays the whole ledger in one transaction. It is idempotent, so it runs on the seed itself; the test checks the row counts of the projection tables afterwards. The breakdown is the time spent in each projector's `apply`.

## Verify
- Both dialects reach the same ledger head hash at the same scale (`status` prints it).
- `uv run pytest tests/query -q` and `just test-parity` still pass: a faster query must return the same rows.

## Roll back
- A dataset is disposable: `uv run python tests/bench/bench_data.py drop --dialect both --records 100000` and seed again. The realtime bench's private copies are removed by the test; a killed run can leave a `tl_test_benchcopy_*` database: `DROP DATABASE ... WITH (FORCE)`.
- Indexes added by a schema change are applied to an existing seed by `create_schema` (idempotent `CREATE INDEX IF NOT EXISTS`); `just bench` does not do it for you.

## Related
- `docs/reports/P0-I8-perf.md` (the numbers), `docs/reports/P0-I8-D.md` (the workstream report).
- `docs/runbooks/rebuild-projections.md`, `docs/runbooks/postgres-local-setup.md`.
- Learnings L-P0-I8D-1 to L-P0-I8D-6 in `docs/memory/LEARNINGS.md`.
