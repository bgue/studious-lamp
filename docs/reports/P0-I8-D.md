# Report — P0-I8 workstream D: performance pass

Written 2026-10-11 by the workstream supervisor. Plan: `docs/tickets/P0-I8/README-D.md`. Numbers: `docs/reports/P0-I8-perf.md`. Branch `p0/i8d`, merged with `p0/i8` (workstreams A, B and C) at 7c5383e before the final measurement.

## Outcome
Objective met: partially. The §15 targets were measured on SQLite and Postgres at 100,000 records, and the hot spots were found with `EXPLAIN`, per-statement timing and profiling, and fixed with before and after numbers. Grid scroll, the TUI grid render, realtime and rebuild meet their targets on both dialects. Grid sort meets it except one pset-property sort on SQLite; grid filter meets it except the `linked`, `count(linked)` and `missing(link)` filters on both dialects and a text search on SQLite. Each miss is a recorded deviation with its cause and a proposed fix (D1 to D6 in the perf report). Demo path verified: `just demo P0-I8-D` runs on both dialects in 1 m 10 s warm and 2 m 43 s with a cold seed.

## Deviations from plan
- The repeated rebuilds of the final run use a 5,000-record dataset (18,023 events), not the 10,000-record one the plan names, so that a full `just bench` on both dialects fits in 15 minutes (13 m 18 s and 12 m 14 s). The 100k rebuild ran once per dialect on its own (SQLite 332 s, Postgres 2,299 s). Before and after rebuild numbers at 10,000 records are in the perf report.
- Not in the plan: S65 changed `schema/core/feed.yaml` (the unique key on `open_scope` became an index) and the feed projector, after the rebuild measurement showed the feed taking 418 of 570 seconds on Postgres. The orchestrator accepted it (decision D-S65).
- Not in the plan: a defect fix in `services/queries.py` (`list_records` ordered by a timestamp failed on Postgres) and a hardening of `?sslmode=` in the Postgres URL (orchestrator ruling).
- Scope notes from the review of S62 (9f96286): that commit also carried T61's provided test (red until T61 merged) and a `bench_live.py` change (the SSE reader closes its response). Both are resolved; later commits carry complete messages.
- Existing tests changed because their contract changed: `packages/tl-schema/tests/test_ddl.py` (the build spec §9 comparison now ignores the extra performance indexes, as amended in 03 §9) and `test_ddl_loader.py` (six statements for `cur_core_record`), `tests/services/test_feed_projection.py` (the test that pinned a unique `open_scope` now pins the rule the projector keeps).

## Supervisor-built pieces
| # | Piece | Outcome |
|---|---|---|
| S60 | Bench harness (`tests/bench/`, `just bench-seed`, `just bench`, `just bench-rebuild`), deterministic generator, measurement method, results files | done (test tooling; no fresh-context review) |
| S61 | `tl:ix_*` index annotations in the DDL generator; indexes in `record.yaml`, `psets.yaml`, `links.yaml`; sslmode mapping | done; fresh-context review: changes requested (test gaps, name limits, sslmode), fixed (f579cea, 2c3f978), re-review passed |
| S62 | Query compiler: sets instead of per-record probes; ordering an index can serve | done; review: changes requested (a link to a missing record began to count), fixed (bc8229e), re-review passed with 0 differences over 16k queries; marked for orchestrator review as a Sonnet-authored area |
| S63 | Measurements and learnings | done |
| S64 | Runbook, demo, README and AGENTS notes, perf report, this report | done |
| S65 | Feed projector without a hot unique index (`feed.yaml`, `projection/feed.py`) | done; review passed; accepted by the orchestrator |

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T60 | merged (d3c51be) | 1 | bench results renderer; 10 tests |
| T61 | merged (0839c96) | 1 | PsetProjector: a new record with five values costs 2 statements, down from 9 |
| T62 | merged (9d545bf) | 1 | LinkProjector: `Link.Added` costs 3 statements, down from 7 to 9 |
No ticket was taken over or abandoned.

## Gates (on the tip of `p0/i8d`)
| Gate | Result |
|---|---|
| `just check` (lint, format, pyright, codegen drift, openapi, licences) | clean |
| `just test` | 5302 passed, 1 skipped, 16 deselected (the bench suite), 26 snapshots; 19 m 29 s |
| `just test-tui` | 608 passed, 26 snapshots; 3 m 48 s |
| `just test-parity` | 2166 passed, 4222 deselected; 31 m 37 s (the container was shared with workstream E's gates) |
| `just bench` (both dialects, 100k) | 14 passed, 2 skipped (the 100k rebuild), 13 m 18 s; repeated once, 12 m 14 s |
| `just bench-rebuild` (100k, once per dialect) | 2 passed, 43 m 52 s |
| `just demo P0-I8-D` | passes; 1 m 10 s warm |
Also run during the work: `tests/query` and `tests/services` on both adapters (1074 passed before the review fixes; the changed and new tests again on both adapters afterwards); the reviewer's differential run of about 16k queries and 2299 tests on both adapters.

## Escalations and decisions
- Ruled by the orchestrator: sslmode must map every mode explicitly (done); `count(linked)` stays a deviation (the proposed fix changes which table answers the query); the 03 §9 divergence is accepted and amended on `p0/i8`; the schema approvals for `record.yaml`, `psets.yaml`, `links.yaml`, `annotations.yaml` and `feed.yaml` are logged by the orchestrator; D-S65 accepted, with the migration filed as a follow-up under the data-migration gate.
- Needs a human, not built: dropping `ux_cur_feed_items_open_scope` on existing databases (or rebuilding into a fresh one) is a migration. Databases that keep the index stay correct but rebuild slowly.
- Two LOW review notes, as asked: (1) re-applying an applied event without a reset now hits the primary key of the card or tag row, where before it double-counted; neither is a supported path; (2) existing databases keep the old unique index (the follow-up above).

## Learnings
Appended to `docs/memory/LEARNINGS.md`: L-P0-I8D-1 (TLS and statements on Postgres), L-P0-I8D-2 (indexes for an ORDER BY with an expression), L-P0-I8D-3 (negations and `cur_link_counts`), L-P0-I8D-4 (a bench finds defects), L-P0-I8D-5 (timing on a shared container), L-P0-I8D-6 (a performance change must not change results), L-P0-I8D-7 (one hot key updated inside one transaction on Postgres), L-P0-I8D-8 (the column-list read in the pset projector; naming in tickets). Implementer proposals declined: T60's "write the blank-line layout in the ticket" (a one-ticket wording point) and "run `just check` before committing" (already L-P0-I8C-6); T62's two notes about tool behaviour (the `Edit` tool needs a `Read`; the `uv` deprecation warning), which are already visible to every agent.

## Docs
- New: `docs/runbooks/performance-benches.md` (indexed in `docs/runbooks/README.md`); `docs/reports/P0-I8-perf.md`; this report; `docs/tickets/P0-I8/README-D.md` and tickets T60 to T62; implementer reports `docs/reports/P0-I8/P0-I8-T60.md` to `T62.md`.
- Updated: `packages/tl-schema/README.md` and `AGENTS.md` (index annotations, 63-character names), `packages/tl-adapters/README.md` (`split_url` and `sslmode`), `packages/tl-core/AGENTS.md` (performance rules), `schema/core/annotations.yaml` (the `tl:ix_<name>` tag), the feed projector docstring (D-S65).
- Generated docs were regenerated by `just gen`, never edited by hand.

## Follow-ups filed
- Migration for existing databases: drop `ux_cur_feed_items_open_scope` (data-migration gate).
- D1: a decision on answering `count(linked)`, `linked` and `missing(link)` without joining the record table per link (the `cur_link_counts` route needs a contract change and a parity proof).
- D2: sort a pset property by its typed column using the form metadata; D3: full-text search (FTS5 on SQLite, a trigram or full-text index on Postgres); D5: a live update should re-read the changed rows, not the whole loaded page.
- Postgres rebuild is bound by statements (feed about 2.5 ms, links about 2.7 ms, outbox 1.2 ms per event): caching the open card and the tag existence checks inside a replay, or batching the replay's inserts, are the next steps.
- The API's feed hub does not use the Postgres `LISTEN/NOTIFY` wake-up the poller supports; not needed for the 2 s target.

## Cost notes
Three implementer tickets, each reviewed once with a pass. Two fresh-context reviews of the supervisor pieces (one changes-requested round). Seeding the 100k Postgres dataset takes 58 minutes; a full `just bench` takes about 13 minutes, the Postgres 100k rebuild 38 minutes. The container was shared; the final runs were taken at load averages of 1 to 2.
