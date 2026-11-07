# P2-SEED-S1 — The demo project generator: framework and the first four sections

Status: ready
Tier: builder
Kind: piece
Review: full
Branch: `p2/seed-s1-generator`   (from claude/wizardly-allen-m2v96s)

## Goal
Read `docs/tickets/P2-SEED/README.md` (the project, volumes and shape). Build `dev/seed/demo_project/` with the
framework, the `core`, `engineering`, `documents` and `correspondence` sections, the `just demo-project` recipe, and a
determinism test. Write through the real command handlers in process (see the World helpers in
`dev/accept/P2-I3/S3.py` and `packages/tl-modules/awp/tests/awp_world.py` for how), never by raw SQL inserts; files
(document renditions) through the file service with small generated PDFs or text bodies.

## Requirements
1. `uv run python -m dev.seed.demo_project --db <path|url> [--seed 2026] [--sections a,b]` (or a script path if
   `dev` is not a package: say which). `just demo-project [db]` wraps it. A fresh ledger is created (`tl init`
   equivalent) unless `--db` already holds P200, which is refused with a clear message.
2. Sections as in the README; each section takes its own `random.Random(f"{seed}:{section}")`. `SECTIONS` order:
   core, engineering, documents, correspondence, awp, materials, quality. awp, materials and quality are stubs here
   that print "not built yet" (T01, T02 and the punch slice fill them).
3. Volumes for this piece's sections as in the README table (tags 300+, documents 80+ with revisions, correspondence
   30+ with some overdue relative to the fixed "today").
4. Realistic names: tag numbers like `200-P-1023A`, line numbers `6"-P-200-1045-A1A`, documents `P200-200-PID-0012`,
   people and contractors from the README. No real company names beyond those fictional ones.
5. Works on SQLite and Postgres (run both once).
6. Test `dev/tests/test_demo_project.py` (or under `tests/tools/`): two runs on fresh SQLite ledgers with the same
   seed give the same keys (hash of sorted record keys per type) and the README minimum counts per section.
7. Prints a summary at the end: per section, records written and seconds taken.

## Allowed paths
- `dev/seed/demo_project/**`, `justfile` (one recipe), `dev/tests/test_demo_project.py` or `tests/tools/test_demo_project.py`
- `docs/reports/P2-SEED/S1.md` (create)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate <the test file>` ends `gate: PASS`
- `just demo-project /tmp/<x>.db` and once against Postgres: the summary lines in the report
