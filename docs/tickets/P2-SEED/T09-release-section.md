# P2-SEED-T09 — Issued IWPs: the release section

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: — (reads the constraints section's IWPs)
Branch: `p2/seed-t09-release`   (from p2/seed; worktree /home/user/wt/seed/p2-seed-t09)

## Goal
The constraints section leaves every IWP in the constraint check. Weekly plans, progress and the KPI tiles need IWPs that are
Issued or In progress. Fill `dev/seed/demo_project/release.py` (a stub, section `release`, runs after `constraints`): for the
IWPs that are Ready (readiness is a worker job: run the awp worker as `docs/runbooks/iwp-readiness.md` says, in process, see
how `tl_mod_awp` tests or `dev/accept/P2-I5` do it), sign off with two distinct people holding a role of the project setting
`awp.release.signoff_roles`, then issue to the foreman (`SignOffIwp`, `IssueIwp`, commands in `tl_mod_awp/commands.py`; the
sign-off and issue words are the controller's, so use `mokafor` and the roster people the setting names). Aim: 10–14 IWPs
Issued, 3–4 of them also started (`StartIwpWork`); the rest stay as they are (some stay not Ready on purpose). If too few IWPs
are Ready, clear the blocking constraints through the real constraint commands (`ClearConstraint`) of the ones raised by the
constraints section, as many as needed, and say which in the report. Dates through `world.on(day)` before TODAY; only the
section's `rng`; no raw SQL writes.

## Context (read these, nothing else)
- `dev/seed/demo_project/constraints.py` (IWP ids, constraints, how readiness is reached)
- `docs/runbooks/iwp-readiness.md`; `packages/tl-modules/awp/src/tl_mod_awp/commands.py` (SignOffIwp, IssueIwp, StartIwpWork)
- `dev/seed/demo_project/world.py`, `registry.py`; `tests/tools/test_demo_project_constraints.py` (test pattern)
may explore: `dev/accept/P2-I5/` (how an acceptance world gets Issued IWPs)

## Allowed paths
- `dev/seed/demo_project/release.py`
- `tests/tools/test_demo_project_release.py` (create)
- `docs/reports/P2-SEED/T09.md`

## Acceptance
```
just check
just gate tests/tools/test_demo_project_release.py tests/tools/test_demo_project_constraints.py tests/tools/test_demo_project.py
```

## Tests to add
`tests/tools/test_demo_project_release.py`: `--sections core,engineering,awp,constraints,release` on fresh SQLite: 10–14 IWPs
Issued or In progress, 3+ In progress, at least 4 IWPs not Ready; the constraint counts of the constraints test still hold or
the report says which moved; deterministic twice; a run without the section leaves other types unchanged.

## Escalation triggers
- Readiness will not compute in process, or the sign-off setting names a role no roster person holds: stop, name it (this may
  become a builder piece; do not add commands or edit `core.py`).

## Amendment (orchestrator, 2026-11-14, after attempt 1)
Decision on the sign-off role: option 2. The product default (`awp.release.signoff_roles = [superuser]`) stays; the demo roster gains a second awp superuser.
- Added allowed path: `dev/seed/demo_project/core.py`. Change only lhartmann (Project engineer) from `("awp", "user")` to `("awp", "superuser")`.
- The two sign-offs on each released IWP are by two distinct people: lhartmann and mokafor.
- If a roster pin in an existing test under `tests/tools/` fails because of this grant, update that pin (added allowed path for that one line) and name it in the report. No other roster change.
