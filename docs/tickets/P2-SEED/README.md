# P2-SEED — Industrial demo project generator

Owner, 2026-11-07: "Write a generator script, kept in the repository (dev/seed/ or similar) with its own just recipe,
so we can extend it later. It builds one deterministic industrial project: seeded, the same every run, on SQLite or
Postgres." The screenshot tour, the demos and both clients use this project. Roadmap item 1
(`docs/build-spec/roadmap-2026-11-07.md`). Side quests go to `docs/build-spec/DEFERRED.md`.

## The project
**P200 — North Refinery, Hydrotreater Unit 2 expansion (brownfield).** Areas (CWAs and drawing areas): 100 pipe rack,
200 process unit (reactor and fractionation), 300 tank farm, 400 utilities (cooling water, steam, nitrogen), 500
substation and control room, 600 tie-ins to the live plant. Disciplines: piping, structural, civil, electrical,
instrumentation, mechanical, insulation, painting. Contractors: Meridian Mechanical (piping), Northline Civil, Bayfield
Electrical, Kestrel Insulation. People: an admin, a document controller, a project engineer, a materials coordinator,
two foremen, a quality inspector, an RFI author, read-only client rep; passwords documented in the runbook.

## Volumes (every log fills past one page)
| Module | Volume |
|---|---|
| Engineering | 300+ tags over the areas (line numbers, valves, instruments, equipment) |
| Documents | 80+ documents with revisions (P&IDs, isometrics, GAs, datasheets), some superseded |
| Correspondence | 30+ RFIs plus letters and transmittals, mixed states, some overdue |
| Work packaging | 40–60 CWPs, a WBS of about 100 nodes over 4–5 levels, 12 CWAs, a path of construction with two versions |
| Materials | 150+ items, 150–250 stock lots over several locations, 300+ movements of every kind, 40–60 receipts (some without MTR), 150 take-off lines with real shortages |
| Quality | punch items open, cleared and verified, by area and system, some overdue — switched on when the record type exists |

## Shape
- `dev/seed/demo_project/` package: `__main__.py` (argparse: `--db`, `--seed`, `--sections`), `world.py` (one
  in-process writer through the real command handlers, like the acceptance World helpers), `rng.py` (one
  `random.Random(seed)` per section, so a section's output does not change when another section changes), and one
  module per section: `core.py`, `engineering.py`, `documents.py`, `correspondence.py`, `awp.py`, `materials.py`,
  `quality.py`. A section registers itself in `SECTIONS` with the record types it needs; a section whose types are
  not installed is skipped with one line (`quality: skipped, quality.PunchItem not installed`).
- Deterministic: fixed seed, fixed clock (a project calendar starting 2026-09-01 with "today" 2026-11-06), ids from the
  normal allocators; two runs on fresh ledgers give identical rows (a test compares row counts and a hash of keys).
- `just demo-project [db]` (SQLite path or postgresql:// URL; default `dev/data/demo-project.db`).

## Pieces and tickets
| Id | What | Tier | Depends on |
|---|---|---|---|
| S1 | framework + core, engineering, documents, correspondence sections + the recipe + determinism test | builder (full) | trunk |
| T01 | awp section (CWPs, WBS, CWAs, path v1 and v2, packages, allocations) | Haiku (full) | S1 |
| T02 | materials section (items, locations, receipts with and without MTR, lots, movements, MTO lines with shortages, reservations) | Haiku (full) | S1 |
| T03 | the tour and demos use the project: `dev/tour/wave1.py` seeds from it (the M4 terminal screens join the tour) | Haiku (full) | T01, T02 |
| T04 | runbook `docs/runbooks/demo-project.md` and README line | Haiku (lite) | T03 |
| T06 | constraint seeds on IWPs and CWPs (core.Constraint, ADR-0024); STAGED until wave 2 and a trunk with the type are merged | Haiku (full) | T01, wave 2 on trunk |
| T05 | fixed anchors for other features (viewer plan check F4): pin tags `200-V-1027`, `300-T-101`, documents `P200-200-PID-4701` (restricted) and `P200-200-PID-4702` (with a superseded revision), so fixtures can key on them | Haiku (lite) | S1 |
| (later) | quality section, on when `quality.PunchItem` exists (roadmap 4a) | Haiku | punch slice |

## Phase 2 modules (round 3 of this increment, 2026-11-14)
Owner: "make test fixtures for new modules". Audit by grep of record types against the seed: requisitions (5 types incl.
WorkOrder), schedule (3 types) and the weekly plan and progress of awp (`awp.WeeklyPlan`, earned progress) have no seed data.
IWPs are never Issued, so weekly and progress screens would stay empty. Cost is NOT a gap (cost codes and a snapshot come
from `ImportCostSnapshot` in the awp and materials sections); quality is seeded. P2-I6 T03 confirmed requisitions and work orders.
Stubs and registry lines are committed by the supervisor. Rules: real command handlers only, no direct inserts; rng per section; tens of records; existing demo WPs, IWPs, items;
default confidentiality; one section file, one test file per ticket. Each ticket's gate: its own test plus `tests/tools/test_demo_project.py`.
| Id | What | Review | Depends on |
|---|---|---|---|
| T07 | schedule: one schedule, 4 weekly XER snapshots, activity links | full | none |
| T08 | requisitions (24, four kinds) and the work order lifecycle | full | none |
| T09 | release: sign off and issue IWPs, start some | full | constraints section |
| T10 | weekly plans, commitments, outcomes (after T09) | full | T09 |
| T11 | IWP progress and KPI figures (after T09) | full | T09 |
