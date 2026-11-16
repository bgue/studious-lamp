# P2-INSP-T03 — Generator: checklists and inspections in the `quality` section of the demo project

kind: piece
review: full
branch: p2/insp-t03-seed
worktree: /home/user/wt/insp/t03
Base: `p2/ip-r3` (INSP-S2 and T01 merged). Merge note: **waits for X4 on trunk** (D8) like every merge into `p2/ip`; build, gate and review may start now. Independent of every other open item (disjoint files: `dev/seed/**`, `tests/tools/**`).
Tier note (r4): written as a piece, not an implementer ticket: the section is about 150 new lines that must reproduce the existing roster-driven shape of `quality.py` (294 lines), and it moves golden counts in four test files; the ability checklist (`01-tiers.md` section 6) fails items 1 and 4 (more than six files of context, pins across files). A `builder` runs it from this spec. Labels: seed, tests.

## Why
The punch section of `dev/seed/demo_project/quality.py` builds 29 punch items through the real commands (read it first: `FINAL`, `_run`, `world.on(day)`, `register("quality", build, needs=("quality.PunchItem",))`). The demo project has no checklist and no inspection, so the INSP demo, the tour and the QR card clause have nothing to show on P200.

## Goal (decided here; the builder does not re-decide)
1. **People.** `hsato` (quality superuser) plans, schedules and records; the verifier must differ from the recorder, so `lhartmann` gains `("quality", "superuser")` in `PEOPLE` (`dev/seed/demo_project/core.py`, the one roster change; she is the QA lead who publishes checklists and verifies). The punch positions do not change: they are by `FINAL` position, not by who holds a word. A roster pin that counts grants moves by union and is listed.
2. **Checklists.** The three fixtures `schema/fixtures/quality/checklists/{flange-makeup,hydrotest-precheck,scaffold-handover}.yaml` are read with `yaml.safe_load` (title, discipline, questions) and created by `CreateChecklist` then `PublishChecklist`, as `lhartmann`. `flange-makeup` is then revised once (`ReviseChecklist`, an edit of one question text on the new draft, publish): four checklist records, flange version 1 Retired, version 2 Published.
3. **Inspections, 18, final states fixed by position** (a `FINAL_INSP` tuple like `FINAL`): 3 Planned (`planned_on` in the future, no checklist), 4 Scheduled (one of them a hold point on an IWP; `scheduled_for` in the next 14 days), 3 Done (one accept, one reject, one conditional, awaiting verify), 6 Verified (4 accept, 1 reject, 1 conditional), 2 Cancelled (one from Planned, one from Scheduled). Two of the Verified accepts are `ReinspectInspection` children of the Verified reject and the Verified conditional (so `reinspection_of` chains exist and the parents stay as they were). Points: 5 hold, 4 witness, 5 review, 4 surveillance in position order. Subjects: 12 IWPs and 6 CWPs from the earlier sections (a subject that itself names no subject, so no chain is longer than two hops); `for_iwp_id` set for the IWP-subject ones; areas the six `AREAS` codes; titles from a fixed tuple like `SUBJECTS`. Every record is made by the S2 handlers (`tl_mod_quality.handlers`, one unit of work per command, actor's own viewer as `_run` does), never by a projection write.
4. **Answers.** Each recorded answer set is built from the pinned checklist's questions: accepts answer every required question in range; the reject fails one required yes/no question (`fails_when: no`) and one number out of range; the conditional fails exactly one. The failed questions raise punch items in the same step (S2 does this): the section does not raise them itself. Expected extra punch items: 1 + 2 (the reject, if both fail) + 1 (conditional) for each of the Done and Verified ones as the S2 rule yields; the test asserts the number the run printed, read from the ledger, not a literal copied from here.
5. **Clock.** Days come from the project calendar through `world.on(day)`; `scheduled_for`, `planned_on` and `at` are derived from `TODAY` (`dev/seed/demo_project/world.py`); do not pass `at` unless the S2 handler refuses the default (it may not be before the day the inspection was scheduled: record on a day on or after it). Nothing reads the real clock; draws come from the section's `rng`.
6. **Order and sections.** The new code runs after the punch items in the same `build`; the section keeps `needs=("quality.PunchItem",)` and additionally skips the inspection part with one printed line (`quality: inspections skipped (quality.Inspection not installed)`) when `quality.Inspection` is missing, and the IWP/CWP subjects it cannot find are replaced by the other kind; with `--sections core,quality` (no IWPs, no CWPs) the section builds the punch items and the checklists and prints `quality: no subjects for inspections`.

## Pins (the builder finds each by running the gates below; list every one in the report as old to new)
The punch counts in `tests/tools/test_demo_project_quality.py` (29 items, 12 Open, ...): inspections raise more punch items, so the existing assertions are narrowed to punch items with no `raised_against` link to an inspection (the seed's own 29) and a new test counts the inspection-raised ones. The runbook totals and the section row in `docs/runbooks/demo-project.md`; the total counts in `tests/tools/test_demo_project.py`; `tests/tools/test_demo_project_anchors.py` only if it fails. The golden for anything that hashes the project (grep `tests/tools` and `dev/accept` for the P200 record total before changing a number).

## Own tests (new file `tests/tools/test_demo_project_inspections.py`, child process on a fresh SQLite ledger as `test_demo_project_quality.py` does, `--sections core,engineering,awp,constraints,quality`)
Counts by state (3, 4, 3, 6, 2) and by point; keys `P200-INS-nnnn` and `P200-CHK-nnnn` without gap; one Published and one Retired flange checklist version; every Verified inspection has `verified_by` different from `recorded_by`; two inspections have a `reinspection_of`; every Done or Verified reject or conditional has at least one punch item linked `raised_against` it and the Verified accept has none; two runs with one seed give the same keys and states; a run without `quality` leaves the other types' counts as before; `--sections core,quality` prints the no-subjects line and builds the punch list and the checklists; the section runs on both adapters if the generator supports Postgres (check the punch test; if it is SQLite only, say so, L-P2-WEB1-3).

## Allowed paths
- `dev/seed/demo_project/quality.py`, `dev/seed/demo_project/core.py` (the one grant line)
- `tests/tools/test_demo_project_inspections.py` (create); the pins above in `tests/tools/test_demo_project_quality.py`, `tests/tools/test_demo_project.py`, `tests/tools/test_demo_project_anchors.py` (only the numbers)
- `docs/runbooks/demo-project.md` (the `quality` row, the totals, the INSP line)
- `docs/reports/P2-INSP/T03.md`
Read-only: everything else (`tl_mod_quality`, schema, fixtures, other sections).

## Acceptance (once each, one at a time; the demo-project gates take minutes: background, no polling)
```
uv run ruff format --check dev/seed tests/tools/test_demo_project_inspections.py tests/tools/test_demo_project_quality.py
uv run ruff check dev/seed tests/tools/test_demo_project_inspections.py tests/tools/test_demo_project_quality.py
uv run pyright dev/seed/demo_project/quality.py dev/seed/demo_project/core.py tests/tools/test_demo_project_inspections.py
just gate tests/tools/test_demo_project_inspections.py
just gate tests/tools/test_demo_project_quality.py
just gate tests/tools/test_demo_project.py
just gate tests/tools/test_demo_project_anchors.py tests/tools/test_demo_project_awp.py
```
Whole-repo pyright is OOM-killed on this box: scoped pyright only; the orchestrator runs `just check` at DONE.

## Escalation triggers
A handler refuses a legitimate command in the seed's world (stop: it is an S2 finding); the punch pins cannot be narrowed without deleting an assertion (never delete: narrow and add); the roster change breaks a test outside Allowed paths in a way that is not a count.

## Report
`docs/reports/P2-INSP/T03.md` (<= 60 lines): deviations first; every pin old to new; the run's printed line (`quality: <n> records, <m> events, <t>s`); the punch items the inspections raised (read from the ledger); gate output (<= 5 lines per command). Builder return <= 15 lines. Commit `P2-INSP-T03: ...` with the trailers the dispatch message names; no model names.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
