# P2-I5-T06a — TUI weekly cycle, steps 1 to 3: look-ahead, constraint review, release

Status: staged (needs T11b merged; stub `weekly_text.py` and its provided test are in the tree)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T11b, S4b, T09
Branch: `p2/i5-t06a-weekly-steps`
Worktree: harness-created under `/home/user/wt/i5/t06a` (from `p2/i5` head)

## Goal
A planner opens the palette entry "Weekly cycle" and works the first three steps on three log screens that share a steps line `1 Look-ahead  2 Constraints  3 Release  4 Commitments  5 Progress` (keys `1` to `5` switch; 4 and 5 arrive in T06b and say "Not available yet" until then). Step 1 lists the next weeks' activities with their IWPs and readiness. Step 2 lists the open blocking constraints and offers Waive on a check-raised one. Step 3 lists the Ready IWPs with sign-offs and offers Sign off and Issue. Screens call client methods only; the handlers decide.

## Brief references (pasted; skills `tui-layout`; packages/tl-tui/README.md "Log screens")
- Text first: `tl_tui/weekly_text.py` (Textual-free; replace the stub; the provided test pins every cell). Screens read through `ClientInterface` (T11b): step 1 `get_look_ahead(project, schedule, weeks=4)` where `schedule` is the first of `list_schedules(project)` with a current snapshot (read `ScheduleView`); no schedule or no published snapshot reads "No published schedule yet." ; the summary line is `look_ahead_summary`. Step 2 `list_constraints(project, blocking=True, state="Open")` plus `state="Assigned"` (two reads, merged by key); row cells: key, subject key, phase, state (humanized), source, owner, age; the panel shows the description. Step 3 `list_iwps(project, state="Ready")` with `list_iwp_counts`; cells: number, subject, foreman, `signoffs n of 2`, ready `ok/total`.
- Actions are `LogAction(key, label, run)` run inside `self.attempt(...)` so a refusal reaches the status line: step 2 `x` Waive on a row whose `source == "check"` and state is Open or Assigned: `ActionFormScreen` asks one required line `Reason` (cap 300), then `client.constraint_command("ClearConstraint", ClearConstraint(constraint=row.id, reason=..., **stamp))`; a cleared row shows `waived` (the row's `waived` field, S4b). Step 3 `s` Sign off: `h = client.get_iwp_hash(project, number)` then `client.awp_command("SignOffIwp", SignOffIwp(iwp=id, record_hash=h.record_hash))`; `i` Issue: `IssueIwp(iwp=id, foreman=row.foreman, record_hash=...)`. Commands are stamped with `tl_tui.action_ui.stamp(cmd, actor=..., scope=...)` as `log_actions.screen_runner` does (the placeholder `ENVELOPE`).
- No new key, no new F-key; the palette entry is `AppCommand("week", "Weekly cycle: look-ahead, constraint review, release", "", "week")` and `TlApp.action_week` opens step 1 through `_push_awp("week")` (add `"week": LookAheadScreen` to its table). Esc closes. After a write the screen reloads (`self.reload()`); F5 reloads. Hidden or refused: the status line text of `describe_error`, never an id.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/log_screen.py
class LogAction: key: str; label: str; run: Callable[[], None]
class LogScreen(Generic[Row]): log_project, columns, drop_order, load_rows, row_key, row_cells, row_record, panel_text, actions_for, summary_text, open_row; attempt(run) -> bool; say(text, error=False)
# tl_core.constraints.commands
class ClearConstraint: constraint: str; reason: str (1..300); cleared_at: str|None; resolved_by: str|None
# tl_mod_awp.commands
class SignOffIwp: iwp: str; record_hash: str          class IssueIwp: iwp: str; foreman: str|None; record_hash: str
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/{weekly_text.py (stub), iwp_text.py (60-112), widgets/iwp_register.py (1-130: a LogScreen host), widgets/constraint_screen.py, widgets/action_form.py, log_actions.py (60-140), action_ui.py (46-75)}`, `app.py` (700-760), `commands.py` (30-50)
- `packages/tl-tui/tests/{fakes_week.py (T11b), test_awp_nav.py (1-60)}`, `docs/tickets/P2-I5/provided/T06a_test_weekly_text.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/weekly_text.py` (replace the stub), `packages/tl-tui/src/tl_tui/widgets/weekly_screen.py` (create: `LookAheadScreen`, `ConstraintReviewScreen`, `ReleaseScreen`, `STEPS`)
- `packages/tl-tui/src/tl_tui/{app.py (action_week and the table entry), commands.py (one row)}`
- `packages/tl-tui/tests/test_weekly_text.py` (create: byte-identical copy of the provided test), `packages/tl-tui/tests/test_weekly_screen.py` (create: below)
- `docs/reports/P2-I5/T06a.md`; consequential pins (union): `packages/tl-tui/tests/test_awp_nav.py` (the palette ids), any test that counts `APP_COMMANDS`

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_weekly_text.py packages/tl-tui/tests/test_weekly_screen.py packages/tl-tui/tests/test_awp_nav.py packages/tl-tui/tests/test_palette.py
```
Expected: 5 passed in `test_weekly_text.py`; `cmp` identical. No snapshot file changes (no existing screen changes); if one does, list it and update it with its old form pinned where it still exists.

## Tests to add
`test_weekly_screen.py` (Textual pilot over `FakeClient` with `seed_week`, pattern of `test_awp_nav.py`): the palette opens step 1 and Esc returns; step 1 shows an activity row and its IWP with `2/3`; `2` shows the blocking constraint, `x` on a check-raised row asks for a reason and sends one `ClearConstraint` (see `client.sent`); an empty reason is not sent; a refusal (`command_error`) lands on the status line; `3` lists Ready IWPs, `s` sends `SignOffIwp` with the hash; `4` says "Not available yet"; no screen text holds a record id.

## Escalation triggers
- A client method of T11b differs from this ticket; `LogScreen` cannot host a second row type per screen (one row type per step is intended).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T06a: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
