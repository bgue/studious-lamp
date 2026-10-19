# Increment plan — P1-I4 Cost snapshots (M11) and P6 XER schedule snapshots

Status: done
Supervisor session: 2026-10-17
Brief sections: §9 M11, §7.2 and §7.3 (links by stable id, orphans), §9 M1 (derivation path, shared with ADR-0014), §28 (lake bronze and silver), §8 and §18 (access; agents propose), §24.6 (runbooks)
Branch: `p1/i4`

Decisions are in [ADR-0015](../../adr/0015-cost-and-schedule-snapshots.md) (accepted 2026-10-17). Phase plan rows: `docs/build-spec/07-phase1-plan.md`, Increment 4.

## Objective
M11 gives the suite a mirror of the cost system (cost codes with a measure matrix and one snapshot per period) and P6 schedules read from XER files: each upload is an immutable snapshot, validated, compared with the one before, published as the current schedule, and linked to by stable activity id. An XER file is untrusted input, so it is read by a bounded, deterministic reader inside the derivation resource envelope (ADR-0014), and the typed rows of a snapshot are written by a queued job into operational tables, not by events.

## Demo
`just demo P1-I4` (SQLite; the same script runs on Postgres with `TL_PG_URL`). It creates two synthetic XER files whose data dates are one week apart (`tl_xer.synth`, checked-in script, no real project data), then:

1. defines schedule `MAIN` and uploads both files; the worker builds both snapshots (`Valid`);
2. publishes snapshot 1, links one record to activity `A1230` and another to `A1990`, publishes snapshot 2;
3. `compare` shows the date shifts (A1230's early finish moves a week), the float erosion (A1230: 9 days to 4 days; two activities go critical), the added activity (A2500), the removed one (A1990), the logic change and the progress movement;
4. the record's link resolves to snapshot 2 now and to snapshot 1 as of 2026-10-08; the link to the removed A1990 is flagged orphaned at publication and shows in the link health view;
5. the look-ahead lists what starts in the next four weeks;
6. a cost snapshot CSV is imported (preview, then apply) for two periods and the second period's change is shown.

The exact commands are fixed when the CLI lands and are copied from `dev/demos/P1-I4.sh` into the report.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `packages/tl-xer`: bounded reader, typed analysis, `DocumentSchema` validation (plan T03 and T04), bundle, child entry, wire checks, synthetic generator | Parser of untrusted input; the security boundary | security pass | done (c709ebe) |
| S2 | T01 schema: `schema/modules/cost/**`, `schema/modules/schedule/**`, workflow and file-slot fixtures, generated files, pinned lists | Schema | human approver via orchestrator (SCHEMA_APPROVALS) | done (9e2357e) |
| S3 | Module `cost`: records, projectors, `ImportCostSnapshot` (admin), plan and apply as one correlated batch (plan T02 handler side) | Core handler; money; correlated batch | security pass | done (096ca84) |
| S4 | Module `schedule`: records, operational tables, build job and worker, publish (supersede, orphan flagging), `LinkActivity`, compare (plan T05 and T06) | Core engine, job, access | security pass; orchestrator review (core engine) | done (2ba0104) |
| S5 | References for the Haiku tickets (CSV reader, resolver, look-ahead), ADR-0015, learnings L-P1-I4-1 to 7 | Reference implementations, mutation-checked | — | done (27b2170) |
| S6 | Stubs, provided tests (`provided/`), tickets T02a, T07, T08 | — | — | done (9495b1d) |
| F1 | Security review fixes in tl-xer and the shared text check | Security | re-review | done (1a47cba) |
| F2 | Security review fixes in the schedule module, API, CLI, MCP | Security | re-review | done (2b10c42) |
| S6b | Views for both modules (`views.py`), `registry.activity_page` | Public read shapes | — | done (c01047f) |
| S7 | API: command table entries (both modules), error rows, read routes, `ApiClient` methods, OpenAPI document | Public interface; access table | security pass | done (c01047f) |
| S8 | CLI operations: `tl xer define/upload/start/publish/void/link/worker/reconcile`, `tl cost import` (preview/apply) | Writes; roles; the actor hook | security pass | done (532cbeb, F2 2b10c42) |
| S9 | TUI client interface (embedded and remote methods) for the schedule and cost reads | Interface the Haiku TUI ticket codes against | — | done (532cbeb) |
| S10 | MCP proposable `PublishScheduleSnapshot` (read tools are T13) | Agents propose only | security pass | done (532cbeb) |
| S11 | `reconcile` (typed rows from the source file after a restore) and the runbook | Recovery path | — | done (532cbeb, runbook F3) |
| S12 | Reports of both modules (`tl_mod_cost.reports`, `tl_mod_schedule.reports`) and the TUI text helpers (`schedule_text.py`) the tickets use | Reads that decide (variance, over budget, which records have no cost code or activity) | — | done |
| S13 | Lake loader for schedule snapshots (bronze `xer_*`, silver `schedule_snapshot` and `schedule_activity`, mart `mart_float_trend`), the weekly series generator `tl_xer.synth.series`, reads that refuse while the typed rows are missing | Core engine: sync, transaction, rebuild equality | orchestrator review | done |
| S15 | Simulator: `ScheduleDesk` and the client calls (open, attach, start, link), `Recorder.schedules/activities/send_update/link_activity`, the `snapshot.queued` intent, `Scenario.operators` and the rules of `sim_assert` for them and for file events, `FakeWorld.define_schedule` and the schedule calls (held to the real suite call by call), the actor `schedule_updater` (the T12 actor, taken over), the scenario `schedule-weeks` | Changes what `sim_assert` excuses | orchestrator review | done |
| S14 | Demo script `dev/demos/P1-I4.sh`, module pages, package READMEs and AGENTS.md, runbook | — | — | done |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | LinkML schema of both modules | S | — | done (S2) | built by supervisor |
| T02a | Cost snapshot CSV reader | H | S6 | merged (4fa7e18) | passed review first time; 84 provided tests; diff to the reference is cosmetic |
| T02b | `tl cost snapshots\|codes\|show` (reads) | H | S8 | merged (a1a7490) | 9 tests on SQLite, 18 on both adapters; `show` cuts parent and uom at 40 characters with `cell()` (disclosed) |
| T03 | XER parser (all tables raw, typed activities, WBS, relationships, calendars, codes, UDFs) | S | T01 | done (S1) | built by supervisor |
| T04 | XER `DocumentSchema` validation | S (taken over) | T03 | done (S1) | the plan had this as H; the check list is one security-reviewed table inside `tl_xer.typed`, so it was built with T03 (L-P1-I3-5) |
| T05 | Snapshot build: operational tables, `Schedule.SnapshotPublished` | S (taken over) | T04 | done (S4) | job, projectors and publish are core-engine work |
| T06 | Snapshot compare | S | T05 | done (S4) | built by supervisor |
| T07 | Activity-id link resolution, as-of, orphans | H | S6 | merged (ef3baa2) | passed review first time; 22 tests on SQLite, 44 on both adapters |
| T08 | Look-ahead query | H | S6 | merged (1c5056b) | passed review first time; the reviewer's mutation spot-check was caught |
| T09a1 | TUI: the schedules and their snapshots (F12), look-ahead, orphans, publish | H | S9 | merged (7e93e13) | 15 tests; the full tl-tui suite passed (912) in the implementer's run; the blank-line order in `_describe` differs from the reference with the same output |
| T09a2 | TUI: the comparison of two snapshots | H | S9 | merged (f32d17f) | 9 tests |
| T09a3 | TUI: the activities of a snapshot and one activity | H | S9 | merged (6d3a917) | passed review first time |
| T09b | `tl xer ls\|show\|activities\|activity\|resolve\|health` | H | S8 | merged (6371aa4) | 18 tests on SQLite, 36 on both adapters; no cut on the show title or the resolve name (disclosed) |
| T09c | `tl xer compare\|look-ahead\|trend` (split from T09b: two files) | H | S8 | merged (1151bb4) | 12 tests on SQLite, 24 on both adapters; a `None` in a critical or duration row prints `-` (supervisor decision, same rule as float rows) |
| T10a | `tl cost report budget\|uncoded` (the report functions are S12) | H | S12 | merged (1bcd90d) | passed review first time |
| T10b | `tl xer unscheduled` (the report function is S12; the IWP-vs-activity report takes the record type as an option until Phase 2) | H | S12 | merged (f8f5767) | 5 tests on SQLite, 10 on both adapters |
| T11 | Lake: `xer_*` bronze, `schedule_activity` silver, float-trend mart | S (taken over) | S13 | done (S13) | the typed rows are not events, so the seq-driven sync cannot carry them: a second pass loads whole snapshots (core engine, rebuild equality, a transaction); the mart is one query inside it |
| T13 | MCP read tools for schedules and cost (13 tools) | H | S10 | merged (de986b6) | 13 tests, plus 35 in the pinned, identity and tool suites |
| T12 | Simulator planner actor (XER with slips), demo support | S (taken over) | T11, S8 | done (S15) | the actor is small and its interface (desk, recorder, fake world, what `sim_assert` excuses) was designed with it; 38 actor tests, 8 end-to-end tests on the real suite (the fake world held to it call by call), 17 mutations of the actor, 18 of the recorder, 11 of `sim_assert` and 14 of the fake world, no survivor |

Haiku-ability (`01-tiers.md` §6) for the ready tickets: T02a reads 6 files, T07 reads 6, T08 reads 4; every interface is in the tree; each has a provided test that fails on the stub and passes on the reference; each diff is one source file plus a report; none touches `schema/**`, a dependency or a public interface; a reviewer verifies from the diff and the three commands. The reader and resolver are security-sensitive, so their merged code also goes through the security pass.

## Order of work
1. Done: S1 to S6; batch 1 (T02a, T07, T08) merged; the security review of c709ebe..27b2170 fixed (F1 to F3); the plumbing S7 to S11.
2. Done: S12 to S14 (reports, TUI text helpers, lake loader, the weekly series, the demo, docs). Round 2 ran in three batches (2a: T02b, T09b, T09c, T10a; 2b and 2c: T10b, T13, T09a1, T09a2, T09a3); every ticket passed review on the first attempt and was merged with a merge commit.
3. Done: S15 and T12 (the simulator schedule updater), the demo on both adapters, the gates, the report with the Showcase (`docs/reports/P1-I4.md`).
4. Open: the owner's full `just test-parity` on the final commit; the security re-review (S13 and S15 included).

## Risks and escalation triggers
- **XER reader resource use.** Measured after the security review (ADR-0015 §2, §4): the worst legal file (the typed maximum: 60 000 activities, 200 000 relationships, 300 000 codes, 300 000 user fields; 42.6 MB) reads in 16.8 s with 582 MB in the child; the hostile shapes of the review are refused in about 3 s. Settle of the maximum snapshot: 25 s on Postgres (JSON per chunk; 535 s with `executemany`) and about 13 s on SQLite; the worker's claim is 600 s. Envelope 60 s and 1 GiB. A bound that cannot be met is an escalation.
- **Writer lock during settle.** Writing 60 000 activities in one transaction holds the SQLite writer lock for seconds. Measured in the report; chunking would change the settle contract (escalate before changing it).
- **Operational tables.** The typed rows are not rebuilt by a projection rebuild; `reconcile` is the recovery path. If the orchestrator wants them as projections, ADR-0015 section 4 is the point to reopen.
- **Roles.** Publishing needs the controller role, importing cost figures needs admin (ADR-0015 section 7). A different rule is a decision for the owner.
- **Parquet.** The ledger path writes no Parquet (`pyarrow` is not locked); bronze Parquet is the lake loader (T11).
- **Haiku fit.** T02a is a parser of untrusted input: a pass of the provided tests plus the security pass is the bar. If it fails review twice the supervisor finishes it from the reference (`git checkout 27b2170 -- <file>`).
- Escalate for: a change to a `tl_core` contract, a link relation outside the thirteen, anything that needs a new dependency.

## Blocked / Decision
(none yet)
