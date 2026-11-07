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
| T03 | the tour and demos use the project: `dev/tour/wave1.py` seeds from it (the M4 terminal screens join the tour) | Haiku (lite) | T01, T02 |
| T04 | runbook `docs/runbooks/demo-project.md` and README line | Haiku (lite) | T03 |
| (later) | quality section, on when `quality.PunchItem` exists (roadmap 4a) | Haiku | punch slice |
