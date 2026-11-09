# P2-I5-T04 — CLI `tl awp look-ahead` and `tl awp week open|ls|show|commit|outcome|close|ppc|reasons`

Status: draft (needs S4a and T03 merged; its provided test is written in the round after S4a merges, against the merged names)
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: T03 (`look_ahead_view`), S4a (week commands and `week_views`)
Branch: `p2/i5-t04-week-cli`
Worktree: harness-created under `/home/user/wt/i5/t04` (from `p2/i5` head)

## Goal
The planner's weekly cycle at the terminal: the look-ahead of the next weeks with IWPs and readiness, and the week plan: open, commit IWPs, record outcomes, close with PPC. Verbs build the S4a commands and call the S4a reads; the handlers decide.

## Brief references (pasted; S4a spec `S4a-weekly-plan.md` is the source of names)
- Commands (S4a): `OpenWeeklyPlan(week_start)`, `CommitIwpToWeek(plan_id, iwp_id, committed_hours, foreman|None, expected_version)`, `RecordWeekOutcome(plan_id, iwp_id, outcome done|missed, miss_reason|None, expected_version)`, `CloseWeek(plan_id, expected_version)`. Reads: `week_views.list_weeks(conn, scope, viewer, limit)`, `week_detail(conn, plan_id, viewer)`, `miss_reasons(conn, scope)`. Week key `<project>-WK-<year>W<ww>`; PPC is a count, one decimal.
- Verbs (group `week` of `tl awp`; `--project`, `--actor` as in `awp_iwp_write.py`; a plan is named by `YYYY-Www`, resolved to its id through `list_weeks`; an IWP by its number):
  - `look-ahead [--weeks N] [--snapshot KEY]` (top level of `tl awp`): the latest published snapshot of the project's schedule unless `--snapshot`; `look_ahead_view(conn, scope, snapshot, session_viewer(db), weeks=N)`. Prints `window <start> to <end>  weeks <n>  need-by lead <lead_weeks>w`, `activities: <n>` then per activity `<activity_id>  <phase>  <early_start|->  <critical *|->  <name cut 40>` and per linked IWP `  <number>  <state>  need-by <date|->  ready <ok>/<total>  blocking <n>` (`ready -` when not evaluated).
  - `week open [--date YYYY-MM-DD]` (default: today's Monday via the command's own normalisation) prints `open <week>  version <v>`.
  - `week ls` prints `weeks: <n>` then `<week>  <state>  <commitments>  ppc <x|->`; `week show WEEK` prints `week`, `state`, `ppc`, `commitments <n>` then `  <number>  <state>  <hours>  <foreman|->  <outcome|->  <miss reason|->`, then notes; an unknown or hidden plan is `error: no week <week>` (exit 1).
  - `week commit WEEK NUMBER --hours H [--foreman user:X]`, `week outcome WEEK NUMBER done|missed [--reason KEY]`, `week close WEEK`: print `<verb> <week>  version <v>`. `--expected-version N` on each (default: the plan's current version, read in the same unit of work).
  - `week ppc` prints `ppc <x>  weeks <n>` over the Closed plans (mean of their stored `ppc`, one decimal, half-up via `progress.engine.round_half_up`; `-` when none).
  - `week reasons` prints one miss-reason key per line from `miss_reasons` (keys, never labels: L-P2-I3-3).
- Reads need no word beyond what the views check; writes go through `_execute` (word gate, handler).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/{awp_iwp_write.py (1-80, register), awp_write.py (100-132), awp_iwp_read.py, awp.py, xer_read.py (find the latest published snapshot; copy its lookup)}`
- `packages/tl-modules/awp/src/tl_mod_awp/{look_ahead_view.py, week_views.py, commands.py (the four week models)}`
- `docs/reports/P2-I5/S4a.md`, `docs/reports/P2-I5/T03.md`

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_week.py` (create): `register(app: typer.Typer) -> None` adds `look-ahead` and the `week` group
- `packages/tl-cli/src/tl_cli/awp.py`: one import and one register line
- `packages/tl-cli/tests/test_awp_week.py` (create: byte-identical copy of the provided test once it exists, else the tests below)
- `docs/reports/P2-I5/T04.md` (create)
- consequential pins: none expected; list any

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_awp_week.py packages/tl-cli/tests/test_cli_awp.py
```

## Tests to add
`test_awp_week.py` over the seed ledger with `awp_world` (see `test_awp_progress.py` for the pattern): open twice refused; commit, outcome, close of three IWPs gives `ppc 66.7`; `week ls` and `week show` lines; `week reasons` keys; `look-ahead` lists a linked IWP under its activity with `ready 2/3`; a plain user refused `close`; no `Traceback` in any output.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I5-T04: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- A name in this ticket differs from the merged S4a or T03 code: the supervisor re-specs; do not guess.
- No published snapshot lookup exists for the CLI without a new query.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
