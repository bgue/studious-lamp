# P2-I5-T04 — CLI `tl awp look-ahead` and `tl awp week open|ls|show|commit|outcome|close|ppc|reasons`

Status: ready (S4a, T03 merged; needs T09 merged: `week ppc` calls its tile)
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: T03, S4a, T09
Branch: `p2/i5-t04-week-cli`
Worktree: harness-created under `/home/user/wt/i5/t04` (from `p2/i5` head)

## Goal
The planner's weekly cycle at the terminal: the look-ahead of the next weeks with IWPs and readiness, and the week plan: open, commit IWPs, record outcomes, close with PPC. Verbs build the S4a commands and call the S4a reads; the handlers decide.

## Brief references (pasted)
- Commands (S4a, `tl_mod_awp.commands`): `OpenWeeklyPlan(week_start: date)`, `CommitIwpToWeek(plan_id, iwp_id, committed_hours: str, foreman: str|None, expected_version)`, `RecordWeekOutcome(plan_id, iwp_id, outcome "done"|"missed", miss_reason: str|None, expected_version)`, `CloseWeek(plan_id, expected_version)`. Reads: `week_views.list_weeks(conn, scope, viewer, limit=60)` -> `WeekRow(id, key, week "2026-W45", week_start, state, ppc|None, closed_at)`; `week_detail(conn, plan_id, viewer)` -> `WeekDetail(... version, commitments: list[CommitmentRow(iwp_id, iwp_key, iwp_state, foreman, committed_hours, outcome, miss_reason)], notes)`; `miss_reasons(conn, scope)` -> keys.
- Verbs (`--project`, `--actor` as in `awp_iwp_write.py`; a plan is named by `YYYY-Www`, resolved with `list_weeks(limit=520)`; an IWP by its number as `awp_iwp_write._iwp_id`):
  - `look-ahead --schedule CODE [--snapshot N] [--weeks N]` (top level of `tl awp`; read as `xer_compare.look_ahead`: `schedule_views.find_schedule`, `find_snapshot(conn, schedule, N, built=True)`, errors through `service_errors`): `look_ahead_view(conn, scope, snapshot_row, session_viewer(db), weeks=N)`. Prints `window <start> to <end>  weeks <n>  need-by lead <lead>w`, `activities: <n>`, then per item `<activity_id>  <phase>  <early_start|->  <critical *|->  <name cut 40>` and per IWP `  <number>  <state>  need-by <date|->  ready <ok>/<total>|-  blocking <n>` (`ready -` when `evaluated` is false).
  - `week open [--date YYYY-MM-DD]` (default today; the command picks the Monday) prints `open <week>  version <v>`.
  - `week ls` prints `weeks: <n>` then `<week>  <state>  <commitments>  ppc <x|->` (commitments from `week_detail`); `week show WEEK` prints `week <week>`, `state <s>`, `ppc <x|->`, `commitments <n>`, then `  <number>  <state>  <hours>  <foreman|->  <outcome|->  <reason|->`, then `note: <text>` lines. Unknown or hidden: `error: no week <week>` (exit 1).
  - `week commit WEEK NUMBER --hours H [--foreman user:X]`, `week outcome WEEK NUMBER done|missed [--reason KEY]`, `week close WEEK` print `<verb> <week>  version <v>`. `--expected-version N` on each; default is the plan's version read in the same unit of work.
  - `week ppc [--weeks N]` (default 4) prints `ppc <x|->  weeks <k>`: `x` is `kpis.ppc_tile(conn, scope, viewer, weeks=N).value`, `k` is the number of Closed plans among `list_weeks` capped at N.
  - `week reasons` prints one miss-reason key per line (keys, never labels: L-P2-I3-3).
- Reads need no word beyond what the views check; writes go through `_execute` (word gate, handler). Never print a URL or a traceback.

## Interfaces (verbatim from repo)
```python
# tl_cli/awp_write.py
def _execute(db: DbTarget, build: Callable[[UnitOfWork], Command]) -> CommandResult
def _line(verb: str, number: str, result: CommandResult) -> None      # "<verb> <number>  version <v>"
# tl_mod_awp/kpis.py (T09)
def ppc_tile(conn, scope, viewer, *, weeks=4) -> KpiTile              # .value Decimal|None
# tl_cli/session.py
def session_viewer(db: DbTarget) -> Viewer
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/{awp_progress.py (the T04b pattern, whole), awp_write.py (100-132), xer_compare.py (115-150)}`
- `packages/tl-modules/awp/src/tl_mod_awp/{look_ahead_view.py (27-60, 131-end), week_views.py (33-62)}`
- the provided test `docs/tickets/P2-I5/provided/T04_test_awp_week.py`

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_week.py` (create): `register(app: typer.Typer) -> None` adds `look-ahead` and the `week` group
- `packages/tl-cli/src/tl_cli/awp.py`: one import and one `awp_week.register(app)` line after `awp_export.register(app)`
- `packages/tl-cli/tests/test_awp_week.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-I5/T04.md` (create); consequential pins: none expected; list any

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_awp_week.py packages/tl-cli/tests/test_cli_awp.py
```
Expected: 7 passed in the first file; `cmp` of the test and the provided copy identical.

## Tests to add
The provided test (copied). Nothing else.

## Escalation triggers
- A name here differs from merged S4a, T03 or T09 code (supervisor re-specs).
- The provided test fails on a line this ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T04: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
