# Increment plan — P1-I4 Cost snapshots (M11) and P6 XER schedule snapshots

Status: in-progress
Supervisor session: 2026-10-17
Brief sections: §9 M11, §7.2 and §7.3 (links by stable id, orphans), §9 M1 (derivation path, shared with ADR-0014), §28 (lake bronze and silver), §8 and §18 (access; agents propose), §24.6 (runbooks)
Branch: `p1/i4`

Decisions are in [ADR-0015](../../adr/0015-cost-and-schedule-snapshots.md) (proposed; the orchestrator accepts it under ADR-0008 decision 6). Phase plan rows: `docs/build-spec/07-phase1-plan.md`, Increment 4.

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
| S6b | Views for both modules (`views.py`), `registry.activity_page` | Public read shapes | — | done (c01047f) |
| S7 | API: command table entries (both modules), error rows, read routes, `ApiClient` methods, OpenAPI document | Public interface; access table | security pass | done (c01047f) |
| S8 | CLI operations: `tl xer upload/worker/reconcile/publish/void/link`, `tl cost import` (preview/apply) | Writes; roles; the actor hook | security pass | todo |
| S9 | TUI client interface (embedded and remote methods) for the schedule and cost reads | Interface the Haiku TUI ticket codes against | — | todo |
| S10 | MCP read tools and the proposable `PublishScheduleSnapshot` | Agents propose only | security pass | todo |
| S11 | `reconcile` (typed rows from the source file after a restore) and the runbook | Recovery path | — | todo |
| S12 | Demo script, gates, module pages, package READMEs and AGENTS.md, report with the Showcase | — | — | todo |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | LinkML schema of both modules | S | — | done (S2) | built by supervisor |
| T02a | Cost snapshot CSV reader | H | S6 | merged (4fa7e18) | passed review first time; 84 provided tests; diff to the reference is cosmetic |
| T02b | `tl cost` read commands (codes, snapshots, the matrix of a code) | H | S7, S8 | draft | — |
| T03 | XER parser (all tables raw, typed activities, WBS, relationships, calendars, codes, UDFs) | S | T01 | done (S1) | built by supervisor |
| T04 | XER `DocumentSchema` validation | S (taken over) | T03 | done (S1) | the plan had this as H; the check list is one security-reviewed table inside `tl_xer.typed`, so it was built with T03 (L-P1-I3-5) |
| T05 | Snapshot build: operational tables, `Schedule.SnapshotPublished` | S (taken over) | T04 | done (S4) | job, projectors and publish are core-engine work |
| T06 | Snapshot compare | S | T05 | done (S4) | built by supervisor |
| T07 | Activity-id link resolution, as-of, orphans | H | S6 | merged (ef3baa2) | passed review first time; 22 tests on SQLite, 44 on both adapters |
| T08 | Look-ahead query | H | S6 | merged (1c5056b) | passed review first time; the reviewer's mutation spot-check was caught |
| T09a | TUI: schedule list, snapshot compare view, activity record | H | S9 | draft | — |
| T09b | `tl xer` read commands (`ls`, `show`, `compare`, `look-ahead`, `resolve`, `health`) | H | S8 | draft | — |
| T10 | Reports: quantities by cost code vs budget, records without cost code, IWP-vs-activity stub | H | S7, T07 | draft | — |
| T11 | Lake: `xer_*` bronze, `schedule_activity` silver, float-trend mart | H | S4 | draft | — |
| T12 | Simulator planner actor (XER with slips), demo support | H | T11, S8 | draft | — |

Haiku-ability (`01-tiers.md` §6) for the ready tickets: T02a reads 6 files, T07 reads 6, T08 reads 4; every interface is in the tree; each has a provided test that fails on the stub and passes on the reference; each diff is one source file plus a report; none touches `schema/**`, a dependency or a public interface; a reviewer verifies from the diff and the three commands. The reader and resolver are security-sensitive, so their merged code also goes through the security pass.

## Order of work
1. Done: S1 to S6. Dispatch T02a, T07, T08 (disjoint paths; at most three at once).
2. The relay returns to the orchestrator, which runs the implementers and reviewers; the supervisor resumes on their results.
3. S7 to S11 (plumbing), then write and dispatch T02b, T09a, T09b, T10 (their interfaces now exist), then T11 and T12 once the bronze path is built.
4. Merge only reviewed tickets with green `just check && just test`. Two failed reviews: the supervisor finishes the ticket.
5. S12: demo on SQLite and Postgres, `just test-parity` alone in the background, docs, report.

## Risks and escalation triggers
- **XER reader resource use.** Measured: 20 MB / 60 000 activities in 9 s and 330 MB; the largest legal file (47.5 MB, 5.9 million cells) 12 s and 550 MB; envelope 60 s and 1 GiB. A bound that cannot be met is an escalation.
- **Writer lock during settle.** Writing 60 000 activities in one transaction holds the SQLite writer lock for seconds. Measured in the report; chunking would change the settle contract (escalate before changing it).
- **Operational tables.** The typed rows are not rebuilt by a projection rebuild; `reconcile` is the recovery path. If the orchestrator wants them as projections, ADR-0015 section 4 is the point to reopen.
- **Roles.** Publishing needs the controller role, importing cost figures needs admin (ADR-0015 section 7). A different rule is a decision for the owner.
- **Parquet.** The ledger path writes no Parquet (`pyarrow` is not locked); bronze Parquet is the lake loader (T11).
- **Haiku fit.** T02a is a parser of untrusted input: a pass of the provided tests plus the security pass is the bar. If it fails review twice the supervisor finishes it from the reference (`git checkout 27b2170 -- <file>`).
- Escalate for: a change to a `tl_core` contract, a link relation outside the thirteen, anything that needs a new dependency.

## Blocked / Decision
(none yet)
