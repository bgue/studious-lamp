# P2-I5-T06b — TUI weekly cycle, steps 4 and 5: commitments, progress and PPC; the two `actions.RULES` rows

Status: staged (needs T06a merged: same files)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, awp
Depends on: T06a, T11b
Branch: `p2/i5-t06b-weekly-steps`
Worktree: harness-created under `/home/user/wt/i5/t06b` (from `p2/i5` head)

## Goal
Step 4 shows the open week's commitments and lets the planner commit an Issued IWP, record an outcome and close the week. Step 5 shows each IWP's earned progress with the KPI tiles (PPC, constraint-free) and starts and completes field work. Closeout is not here (roadmap 3c). The module gains the two `actions.RULES` rows (Q-o2) so a record screen offers Start work and Complete field work.

## Brief references (pasted)
- Rows (module, `tl_mod_awp/actions.py`, after the `ReleaseHold` row): `Rule("StartIwpWork", "Start work", "awp.iwp.edit", (IWP,), states=(IWP_ISSUED,))` and `Rule("CompleteIwpField", "Complete field work", "awp.iwp.edit", (IWP,), states=(IWP_IN_PROGRESS,))` (words equal the `AWP_COMMANDS` access of both; the handlers' states are `IWP_ISSUED` and `IWP_IN_PROGRESS`, `handlers/progress.py` 258, 272). A test holds every row's word equal to its command's access and counts the rows: update both in union form (`tests/test_actions.py`).
- Step 4 (`CommitmentsScreen`, rows `WeekRow` then its commitments): `list_weekly_plans`, `get_weekly_plan(week)`; the open plan is the latest not Closed; none: a one-line `o` Open this week (`OpenWeeklyPlan(week_start=today)` through `awp_command`). Keys `c` Commit (`ActionFormScreen`: IWP number choice among `list_iwps(project, state="Issued")` and `"In progress"`, hours line, foreman line optional) -> `CommitIwpToWeek(plan_id, iwp_id, committed_hours, foreman, expected_version=detail.version)`; `d` Done / `m` Missed on a commitment row -> `RecordWeekOutcome(plan_id, iwp_id, outcome, miss_reason, expected_version)` (Missed asks a `Reason` choice from `list_miss_reasons`, shown humanized); `z` Close the week -> `CloseWeek(plan_id, expected_version)` after a confirm; the PPC of a Closed plan shows in its summary. Refusals (stale version, word, rule) go to the status line.
- Step 5 (`ProgressScreen`, rows IWPs in states Issued, In progress, Field complete from `list_iwps`): cells number, subject, state, earned % from `get_iwp_progress` per visible row is NOT allowed (one call per row): read `list_iwp_counts` for the page and `get_iwp_progress` only for the highlighted row's panel (items, steps, edition, notes). The summary line is `kpi_line` of both tiles (`list_kpis`). Keys `w` Start work and `f` Complete field work: `StartIwpWork(iwp_id, expected_version)` / `CompleteIwpField(...)` through `awp_command` (`expected_version` from `client.get_record(f"project:{project}", number)["version"]`, as `tl_cli/awp_progress.py` reads it; `IwpRow` has no version).
- Text: add pure functions to `weekly_text.py` for the new cells and panel lines (`commitment_cells` and `kpi_line` exist from T06a); a test per function in `test_weekly_text.py`'s sibling `test_weekly_text2.py`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/{weekly_text.py, widgets/weekly_screen.py}` (T06a), `docs/reports/P2-I5/T06a.md`, `docs/tickets/P2-I5/T06a-weekly-cycle-steps-1-3.md` (the action pattern)
- `packages/tl-modules/awp/src/tl_mod_awp/actions.py` (100-190), `packages/tl-modules/awp/tests/test_actions.py` (the row-count and word tests), `handlers/progress.py` (250-280)
- `packages/tl-tui/tests/fakes_week.py`, `docs/reports/P2-I5/S4a.md`

## Allowed paths
- `packages/tl-tui/src/tl_tui/{weekly_text.py, widgets/weekly_screen.py}`
- `packages/tl-modules/awp/src/tl_mod_awp/actions.py` (the two rows only), `packages/tl-modules/awp/tests/test_actions.py` (union pins)
- `packages/tl-tui/tests/test_weekly_text2.py`, `packages/tl-tui/tests/test_weekly_screen2.py` (create)
- `docs/reports/P2-I5/T06b.md`; consequential pins (union): tests that list `RULES` commands or offers per state (the gate names them); list each

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_weekly_text2.py packages/tl-tui/tests/test_weekly_screen2.py packages/tl-tui/tests/test_weekly_screen.py packages/tl-modules/awp/tests/test_actions.py packages/tl-modules/awp/tests/test_iwp_signoff.py
```

## Tests to add
`test_weekly_screen2.py` (pilot over `FakeClient` with `seed_week`): `4` shows the Committed plan and its commitments; `c` sends one `CommitIwpToWeek` with `expected_version` of the plan; `m` asks a reason and sends `RecordWeekOutcome`; `z` asks to confirm then sends `CloseWeek`; `5` shows the KPI line and no per-row `get_iwp_progress` call (count calls on the fake); `w` on an Issued row sends `StartIwpWork`. `test_actions.py`: `states_for("StartIwpWork", IWP) == ("Issued",)`, an Issued IWP is offered Start work to `awp.iwp.edit` holders and not a Draft.

## Escalation triggers
- `get_record` answers None for an IWP the person can open; a `RULES` test pins something this ticket cannot extend in union form.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T06b: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
