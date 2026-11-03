# P2-I3-T11 — The increment's tests and the mutants of S2-S6 (tests piece, C3)

Status: ready (dispatch after S6, T06i and T08 are merged; this is the last item before C4)
Tier: sonnet
Kind: piece
Review: full
Labels: tests
Depends on: S1-S6, T01a-b, T03, T04a-b, T05a-d, T06a-i, T07, T08 (merged)
Branch: `p2/i3-t11-tests`  (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
Policy D1 deferred every test to here. This piece writes the tests the spec section 9 lists, plus the pins the reports asked for, and the gate RUNS them (unlike every earlier item): `just gate <touched test dirs>` and `just gate-pg packages/tl-modules/materials`. Tests are new files under the test paths below only; no source file changes. A test that fails because the source is wrong is not fixed here: write it down under *Blocked* with the smallest reproduction and keep the test (never skip, xfail or weaken it, AGENTS.md "Never").

## Brief references
> Spec `docs/build-spec/specs/m4-materials.md` section 9 test list (by origin) and section 10 (demo clauses = what the tests also cover on the unit level).
> Policy: tests run on SQLite and, under `--adapters` (parity), on Postgres, with the `new_db` fixture as `packages/tl-modules/cost/tests/conftest.py`. Five-reader walks: the viewer defaults to the lowest clearance; a hidden record answers as one that never existed (ADR-0016); walking tests are written as five kinds of reader (as `packages/tl-api/tests/test_confidentiality_walk.py`).
> Acceptance scripts under `dev/accept/P2-I3/*.py` already prove most behaviours once; port their checks into pytest, reusing their World helpers where a fixture is needed (copy into `testing` code under the tests dir; do not import from `dev/`).

## Test files (create; part A to D are committed separately, each green before the next)
A. Module and schema (`just gate` + `gate-pg`)
- `packages/tl-schema/tests/test_materials_schema.py` (S1: code lists StockUom 9 codes, ItemCategory 15, LocationKind 5, ConditionCode 4, MovementReason 7; `tl:offline`; samples paste the same lists).
- `packages/tl-modules/materials/tests/{conftest.py,test_items.py,test_locations.py,test_targets.py,test_projection_rebuild.py}` (S2; a `MaterialsWorld` fixture; rebuild gives identical rows, property test with hypothesis if the repo already uses it, else a seeded loop; the `limits` bounds).
- `test_receipts.py`, `test_movements.py` (incl. two concurrent issues on Postgres: one wins, one refused; barrier before the `with`, see TRAPS: SQLite open_uow takes BEGIN IMMEDIATE on entry), `test_actions.py`, `test_api_surface.py` (S3), `test_mto.py` (S4), `test_samples.py`, `test_loaders.py` (T01), `test_materials_reserved.py` (T03, calls `check_readiness_contract`), `test_view_keys.py` (S5).
- Pins from decisions: D29 (a republished take-off key is `-2`; `takes_provenance` False), Q5 (reserve check is literal `reserved + qty <= line qty`; Adopt is a project word at company scope), Q7 (no `planned_start` is blocked; a fully received PO line still promises its item), D35 (`movements --kind` unknown returns zero rows).
B. API, MCP (`just gate`)
- `packages/tl-api/tests/test_api_materials.py` (T04a routes, 401/403/404, openapi names unique; S5 routes `mto-line?key=` and `item-projects?code=`); five-reader walk over every materials GET route and the S5 views (class-filtered records; `MIN_ROUTES`), `packages/tl-mcp/tests/test_materials_tools.py` (T07: nine reads, `propose_reservation` waits for a person; five-reader walk over the tools).
C. TUI and CLI (`just gate`)
- `packages/tl-tui/tests/test_{materials,receipt,mto,item,location,receipt_entry}_text.py` (pure text: columns, drop order, summary lines, refusals/messages, no `None` or bare dash; `import` leaves `textual` out of `sys.modules` in a subprocess); `test_client_materials.py` (T04b, fake and embedded agree; S6 `attach_record_file`: hidden = missing, no event on refusal); `test_materials_screens.py` (80 and 170 columns plain walk of Stock, Movement log, Receipts, Items, Locations, MTO lines, Receipt entry on `TlApp` with the fake; receipt entry: `Delete` removes a line and the cursor stays; a refused `CreateReceipt` keeps the form open with the typed values and says why; the amber `Note` for the MTR line).
- `packages/tl-cli/tests/test_cli_mat_*.py` (read verbs, the `ls` aliases, write verbs incl. `move adjust --direction`, `mto show`, `item-projects`; refusal texts `error: forbidden: ...`; a bad line exits 1 and the event count is unchanged), `test_reports.py` (six reports, CSV, `heat_trace` MTR = last mtr-slot file D30).
D. Mutants (own worktree only; report 3 lines, see below).
Not in this piece: sim `MaterialsDesk` tests (the sim ticket is not scheduled), demo.

## Interfaces and guards the mutants must cover
Sentinel: one mutant that must be killed (proves the baseline passes and the harness kills). Targeted, at most 5, chosen from (file:line as of the S2-S5 reports; re-find them by the guard text):
`handlers/receipts.py:850` (Accept needs the MTR), `handlers/movements.py:389` (negative balance), `:449` (reserve over line qty), `:385` (consumable cost code), `handlers/mto.py:489` (assign refused with a reservation), `views.py:756` (received_by class filter), `views_detail.py:177` (hidden-project filter), `projectors/stock.py:216`/`:211`, `handlers/locations.py:172`/`:244`, `limits.py:27`. Pick the five whose tests were hardest to write; each surviving mutant is a missing test: add it before reporting.

## Context (read these, nothing else)
- the reports `docs/reports/P2-I3/{S1,S2,S3,S4,S5,S6,T04a,T04b,T05a,T05b,T05c,T05d,T07}.md` (guards, pins, shapes), `docs/tickets/P2-I3/STATE.md` REFS and TRAPS, `text-contracts.md`
- `packages/tl-modules/cost/tests/conftest.py` (module test fixture pattern), `packages/tl-api/tests/test_confidentiality_walk.py`, `packages/tl-mcp/tests/test_confidentiality_walk.py`, `packages/tl-tui/tests/fakes_materials.py`, `dev/accept/P2-I3/*.py` (checks to port)
may explore: the source under test, read only.

## Allowed paths
- `packages/tl-schema/tests/test_materials_schema.py`
- `packages/tl-modules/materials/tests/**` (create, with a `conftest.py`), `packages/tl-api/tests/test_api_materials.py`, `packages/tl-mcp/tests/test_materials_tools.py`
- `packages/tl-tui/tests/test_*_text.py` named above, `test_client_materials.py`, `test_materials_screens.py`; `packages/tl-cli/tests/test_cli_mat_*.py`, `test_reports.py`
- `packages/tl-api/tests/test_confidentiality_walk.py`, `packages/tl-mcp/tests/test_confidentiality_walk.py` (add the materials routes/tools to their lists only)
- `docs/reports/P2-I3/T11.md` (create)
No source file. A pin elsewhere that breaks only because a new test file exists is updated and listed.

## Acceptance (the gate runs the tests; once per part, then once for all)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
just gate packages/tl-schema/tests/test_materials_schema.py packages/tl-modules/materials packages/tl-api/tests packages/tl-mcp/tests packages/tl-tui/tests packages/tl-cli/tests 2>&1 | tee .gate/summary.txt
just gate-pg packages/tl-modules/materials 2>&1 | tee .gate/summary-pg.txt
```
Expected: `gate: PASS` on both (last line of each summary); `just check` clean. `gate-pg` exit 3 means the cluster is down: report it, do not skip. Heavy runs: one pytest session at a time, never `pkill`, never delete `/tmp/pytest-of-root`. Mutation: sentinel + up to 5 targeted, each run as `just gate <the one test file that should fail>`, restored with `git checkout -- <file>`; report 3 lines (`killed n/6`, which survived and the test added).

## Tests to add
This piece is the tests.

## Report requirements
Piece report (≤ 60 lines): deviations first; part A-D commit shas; both `gate:` lines and the counts (`n passed`); the 3 mutation lines; any source bug found (Blocked, with the failing test name); candidate learnings; builder return ≤ 15 lines in Code 92.
Commit subjects `P2-I3-T11: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
Stop and write *Blocked* if: a test finds a source defect that needs a source change (list it, keep the red test, do not merge it as green); a pin needs a decision (Q5, Q7, D29 are ratified defaults: pin them, do not reopen); the gate is red for the environment (OOM, /tmp full, Postgres down: say which, do not retry more than once); the suite for part A-C would exceed the gate's time budget (split by part and say where you stopped).

## Blocked
(builder writes here)

## Decision
(supervisor writes here)
