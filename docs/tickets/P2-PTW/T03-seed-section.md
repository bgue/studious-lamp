# P2-PTW-T03 - Generator: a `permits` section in the demo project

kind: piece
review: full
branch: p2/ptw-t03-seed
worktree: /home/user/wt/ptw/t03
Base: `p2/ip-r3` (PTW-S2, S3, T01 merged; T02 not required). Merge note: **waits for X4 on trunk** (D8) like every merge into `p2/ip`; build, gate and review may start now. Disjoint files from every other open item (`dev/seed/**`, `tests/tools/**`, `docs/runbooks/demo-project.md`).
Tier note (r5): a piece, like INSP-T03 (D23): a new roster-driven section of about 200 lines over seven record kinds that moves golden counts in several files; the ability checklist (`01-tiers.md` section 6) fails items 1 and 4. Labels: seed, tests, safety.

## Why
The demo project has no permit, isolation or gas test, so the PTW demo, the tour and the QR permit-card clause have nothing to show on P200.

## Goal (decided here; the builder does not re-decide)
New file `dev/seed/demo_project/permits.py`, registered `register("permits", build, needs=("permits.Permit", "awp.IWP"))`, built after `quality` (read `quality.py` first for the shape: `FINAL`, `_run`, `world.on(day)`, the `rng` draws, the printed `<section>: n records, m events` line and the "not installed" skip line the registry prints).
1. **People.** No roster change: `ipetrov` (user + document_controller) approves and issues; `cbrooks` and `pnair` (foremen) request, apply isolations, record gas tests and are holders; `lhartmann` (quality superuser) is the second isolation verifier where `ipetrov` applied. Verifier is always a different person from the applier; approver never the requester. If a word the section needs is held by nobody in the roster, stop (escalation), do not widen the roster silently.
2. **Permits, 20, final states fixed by position** (a `FINAL` tuple like `quality.py`'s): 2 Requested, 3 Approved, 5 Active (two of them hot work with a passing gas test, one confined space with a Verified isolation linked), 2 Lapsed shown (Active whose `valid_until` is before `TODAY`: issue on earlier days through `world.on(day)`, no job run, no clock read: the Lapsed state is derived), 2 Suspended (one by a failing gas test through `RecordGasTest`, one by `SuspendPermit` with a reason; one of them is resumed back to Active in a third position so a Resume event exists), 3 Handed back / Closed (two Closed, one Handed back), 2 Rejected, 1 Cancelled. Types in position order cycle over the six `PERMIT_TYPES` so every type occurs; areas the six `AREAS` codes; holders `cbrooks`/`pnair`; descriptions from a fixed tuple; 12 permits carry `for_record_id` of an IWP from the awp section, 2 of an awp CWP, the rest none. Every record is made by the S2 and S3 handlers, one unit of work per command, as `_run` does; never a projection write.
3. **Isolations, 8**: 3 Verified (two linked to Active permits), 3 Applied (one linked to an Approved permit), 2 Removed (after their permits closed, so the removal guard passes). Energies cycle over the four kinds; lock and tag numbers `L-nn`/`T-nn`; one has a `point_record_id` of a core record from the engineering section (a tag), none of a restricted one.
4. **Gas tests, 14**: for the hot work and confined space permits; mostly passing, three failing (one suspends its Active permit, per the S3 rule), readings inside the setting ranges; `taken_at` derived from `TODAY` and the permit's issue day (never the real clock; before `valid_until`; a passing test within the type's valid minutes of the issue day).
5. **Clock and draws.** All days through `world.on(day)` derived from `TODAY`; draws from the section's `rng`; two runs with one seed give identical keys and states.
6. **Skips.** With `permits.Permit` not installed the registry's skip line applies; with `--sections core,permits` (no IWPs) the section prints `permits: no subjects for permits` and builds permits with no `for_record_id`, isolations and gas tests.

## Pins (the builder finds each by running the gates below; list every one old to new in the report)
Totals of the default build and the section row in `docs/runbooks/demo-project.md` (read the measured line printed by the run; do not copy a number from here); the total counts in `tests/tools/test_demo_project.py`; `tests/tools/test_demo_project_anchors.py` and any test that counts records by type across the whole project, only if they fail; grep `tests/tools` and `dev/accept` for the P200 record total before changing a number. Existing assertions are narrowed or extended, never deleted.

## Own tests (new file `tests/tools/test_demo_project_permits.py`, child process on a fresh SQLite ledger as `test_demo_project_inspections.py` does, `--sections core,engineering,awp,constraints,permits`)
Counts by shown state (2, 3, 5, 2 Lapsed, 2 Suspended minus the resumed, ...: assert the `FINAL` shape read from the ledger) and by type (all six present); keys `P200-PTW-nnnn`, `P200-ISL-nnnn`, `P200-GAS-nnnn` without gap; no Active permit has an isolation that is not Verified when its type requires one; every Verified isolation has `verified_by` different from `applied_by`; no approved permit has `approved_by` equal to its requester; at least one gas test fails and its permit was suspended; a Removed isolation has no live linked permit; two runs with one seed agree; `--sections core,permits` prints the no-subjects line; a run without `permits` leaves the other counts as before. SQLite only (the generator is; say so, L-P2-WEB1-3).

## Allowed paths
- `dev/seed/demo_project/permits.py` (create); `dev/seed/demo_project/__init__.py` or `registry.py` only for the one import line the other sections need (look at how `quality` is imported)
- `tests/tools/test_demo_project_permits.py` (create); the pins above in `tests/tools/test_demo_project.py`, `tests/tools/test_demo_project_anchors.py`, `tests/tools/test_demo_project_quality.py` (only numbers)
- `docs/runbooks/demo-project.md` (the `permits` row, the totals, the PTW line)
- `docs/reports/P2-PTW/T03.md`
Read-only: everything else (`tl_mod_permits`, schema, other sections).

## Acceptance (once each, one at a time; the demo-project gates take minutes: background, no polling)
```
uv run ruff format --check dev/seed tests/tools/test_demo_project_permits.py
uv run ruff check dev/seed tests/tools/test_demo_project_permits.py
uv run pyright dev/seed/demo_project/permits.py tests/tools/test_demo_project_permits.py
just gate tests/tools/test_demo_project_permits.py
just gate tests/tools/test_demo_project.py
just gate tests/tools/test_demo_project_anchors.py tests/tools/test_demo_project_quality.py
```
Whole-repo pyright is OOM-killed on this box: scoped pyright only; the orchestrator runs `just check` at DONE. Mutation: sentinel plus at most 3 mutants on the guard-shaped assertions (verifier equals applier, approver equals requester), run once, 3 lines.

## Escalation triggers
A handler refuses a legitimate command in the seed's world (stop: it is an S2 or S3 finding); a count pin cannot be extended without deleting an assertion; the section needs a roster or schema change; a Lapsed permit needs a job run or a clock read to show.

## Report
`docs/reports/P2-PTW/T03.md` (<= 60 lines): deviations first; every pin old to new; the run's printed line (`permits: <n> records, <m> events, <t>s`); gate output (<= 5 lines per command). Builder return <= 15 lines. Commit `P2-PTW-T03: ...` with the trailers the dispatch message names; no model names.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
