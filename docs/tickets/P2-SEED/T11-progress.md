# P2-SEED-T11 — IWP progress: scope items and the progress section

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: T09 (merged). Does NOT depend on T10: disjoint files; `progress` runs after `weekly` in ORDER, and its test runs
without `weekly`.
Branch: `p2/seed-t11-progress`   (from p2/seed; worktree /home/user/wt/seed/p2-seed-t11)

## Goal
Earned progress counts the steps of the scope items of an IWP, and the seed has NO scope items. `AddIwpScope` is refused on a
frozen IWP (Issued and later), so scope must exist before `release`. Two stubs are registered: `scope` (after `constraints`,
before `release`) and `progress` (after `weekly`, last). Fill both.

1. `dev/seed/demo_project/scope.py`: with `CreateScopeItem` (commodity from the demo list, qty, uom, est_hours, cwp_id of the
   IWP's CWP when easy) and `AddIwpScope`, give 3-6 scope items to each of the IWPs that are Ready (read them with `world.rows`
   as `release.py` does; use as few as needed, but at least 20 IWPs have items or all Ready ones, whichever is fewer). Choose
   commodities whose progress steps include a `manual` evidence step (look at `engine.rules_for` and the edition in force:
   `progress/engine.py`). Some items stay unstarted. This must not change release: the same 12 IWPs are still releasable.
2. `dev/seed/demo_project/progress.py`: on the In progress IWPs from release, `RecordManualProgress` (a different share of
   the manual steps per IWP) for all 4, and `CompleteIwpField` for 2 of them, so earned progress is non-zero and differs per
   IWP. Optionally `InstallScopeItem` on a few items so the non-manual steps move too. Dates through `world.on(day)` before
   TODAY (2026-11-06); `progress` runs after the weekly section, which may have committed IWPs to weeks, so do not return an
   IWP to Issued; a Field complete IWP is fine.
Words: progress `user` (foremen and the project engineer); scope edit by the IWP's editor word (check `access-words.yaml`;
admin `mokafor` holds all). Only the sections' own `rng`; no raw SQL writes.

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/handlers/{scope,progress}.py`, `progress/engine.py` (steps, rules), `commands.py` 567-625, 737-796
- `dev/seed/demo_project/release.py`, `awp.py` (CWPs and IWPs), `world.py`, `registry.py`
- `tests/tools/test_demo_project_release.py` (test pattern)

## Allowed paths
- `dev/seed/demo_project/scope.py`, `dev/seed/demo_project/progress.py`
- `tests/tools/test_demo_project_progress.py` (create)
- `docs/reports/P2-SEED/T11.md`
Do not touch `data/awp/standards.yaml` (T10 owns it), `release.py`, `core.py`, `weekly.py`.

## Acceptance
```
just check
just gate tests/tools/test_demo_project_progress.py tests/tools/test_demo_project.py
```

## Tests to add
`tests/tools/test_demo_project_progress.py`, `--sections core,engineering,awp,constraints,scope,release,progress` on fresh
SQLite (child process): scope items exist and every released IWP has some; 10-14 IWPs Issued or In progress or Field complete
and exactly 2 Field complete, as in the run with `scope` and `progress` left out (release is unchanged: compare the released
IWP keys); stored progress for the 4 started IWPs has at least 3 distinct earned percentages, none 0 except by design; deterministic twice;
a run without the two sections leaves other types unchanged.

## Escalation triggers
- No commodity of the demo list has a manual step, or the edition is not adopted: stop, name it (a standards edit is a decision).
- `AddIwpScope` or `CreateScopeItem` refused on Ready IWPs, or scope changes readiness so fewer than 12 are Ready: stop.

## Amendment (orchestrator, 2026-11-14, after attempt 1)
- Added allowed path: `dev/seed/demo_project/data/standards.yaml`. Add the `UnitOfMeasure` code list, copied entry for entry from `schema/fixtures/standards/co.acme.standards@1.0.0.yaml`, so `CreateScopeItem` accepts the demo units. Do not touch `data/awp/standards.yaml` (T10 owns it).
- Commodities without a `manual` step falling back to the piping steps is accepted; say so in the report.
Then finish `scope.py`, `progress.py` and the test as the ticket says.

## Amendment 2 (orchestrator, 2026-11-14, after attempt 2)
Decision: option 1. Scope is defined during planning, so the `scope` section runs before `constraints` (IWPs are still Draft or Planned there).
- Added allowed path: `dev/seed/demo_project/registry.py`, the `ORDER` tuple only: move `scope` to just before `constraints`. Keep `scope.py`'s `needs` consistent with the new place.
- Add scope to the IWPs that the constraints and release sections later carry forward (the same IWPs as before, chosen by id, not by Ready state).
- If adding scope changes which IWPs reach Ready or Issued, update the pins in `tests/tools/test_demo_project_release.py` and `tests/tools/test_demo_project_constraints.py` (added allowed paths, pins only) and explain each changed number in the report. Do not change the handler rule.
- Run the gate with the release and constraints tests included.
