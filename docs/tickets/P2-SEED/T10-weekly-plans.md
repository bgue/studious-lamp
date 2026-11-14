# P2-SEED-T10 — Weekly plans: the weekly section

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: T09 (merged; reads its Issued and In progress IWPs)
Branch: `p2/seed-t10-weekly`   (from p2/seed; worktree /home/user/wt/seed/p2-seed-t10)

## Goal
Fill `dev/seed/demo_project/weekly.py` (a stub, section `weekly`, runs after `release`; needs `awp.IWP`). T09 leaves 8 IWPs
Issued and 4 In progress (12 released, foremen set). Build 5 weeks from Monday 2026-10-05 with the real handlers
(`tl_mod_awp.handlers.week`; commands in `tl_mod_awp/commands.py`): `OpenWeeklyPlan`; `CommitIwpToWeek` (hours text such as
"40", foreman from the IWP); `RecordWeekOutcome` (`done`, or `missed` with a `MissReason` code); `CloseWeek` for weeks 1-3.
Week 1-3 Closed (PPC written; one of them under 70%), week 4 Committed with some outcomes recorded, week 5 Draft: opened and
committed, no outcomes. Commit 4-8 of the 12 released IWPs per week (draws from the section's own `rng`); a second commit of
the same IWP in a later week is normal. Commit needs the IWP Issued or In progress, which is true for all 12 now; the dates
are cosmetic, run every command inside `world.on(<a day in or just before that week>)`, and never after TODAY (2026-11-06).
Words: plan and commit `user`, outcome by the same, close `controller` = `mokafor`. Use the roster person that holds each word
(`dev/seed/demo_project/core.py`); read as that person. No raw SQL writes. Read the released IWPs with `world.rows` (see how
`release.py` does).

DATA GAP, yours to fix: the demo awp standards have no `MissReason` code list, so `missed` is refused ("not a miss reason").
Add it to `dev/seed/demo_project/data/awp/standards.yaml` with the codes Constraint, Material, Labour, Weather, Rework,
Access, Equipment, Other (same shape as `GeneralRequisitionType` in that file; copy the list from
`schema/fixtures/packages/co.acme.awp@1.1.0.yaml`). Only this ticket edits that file. If an adopted edition does not take
the new list (version or checksum rules), stop and say so.

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/handlers/week.py` (rules and messages); `commands.py` lines 798-840
- `dev/seed/demo_project/release.py` (reading IWPs, `world.run`, `world.on`), `world.py`, `registry.py`
- `dev/seed/demo_project/data/awp/standards.yaml`; `tests/tools/test_demo_project_release.py` (test pattern)

## Allowed paths
- `dev/seed/demo_project/weekly.py`
- `dev/seed/demo_project/data/awp/standards.yaml` (MissReason only)
- `tests/tools/test_demo_project_weekly.py` (create)
- `docs/reports/P2-SEED/T10.md`

## Acceptance
```
just check
just gate tests/tools/test_demo_project_weekly.py tests/tools/test_demo_project.py
```

## Tests to add
`tests/tools/test_demo_project_weekly.py`, `--sections core,engineering,awp,constraints,scope,release,weekly` on fresh
SQLite (child process): 5 `awp.WeeklyPlan` records; states 3 Closed, 1 Committed, 1 Draft; every closed week carries a PPC and
at least one is under 70; week 4 has at least one outcome and one commitment without; at least one missed outcome with a
reason; deterministic twice (same plan keys and states); a run without the section leaves other types unchanged.

## Escalation triggers
- Commit or close is refused for a reason the ticket does not name, or the plan states cannot reach those counts: stop, name it.
- Do not edit `release.py`, `core.py` or any handler; do not add commands.

## Amendment (orchestrator, 2026-11-14, after attempt 1)
- Week 5: accepted as built, opened with no commitments (the only reachable Draft). The test pins 1 Draft.
- lhartmann (project engineer, awp superuser) plans, commits and records outcomes: accepted.
Nothing else changes; finish the report (status done) and run the gate.
