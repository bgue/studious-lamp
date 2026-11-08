# P2-I2-T08 — backlog weeks per foreman and the sizing surface

Status: staged (dispatch after T04c2 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, read
Depends on: T04c2, S4 (merged)
Branch: `p2/i2-t08-backlog-sizing`
Worktree: harness-created under `/home/user/wt/i2/t08` (from `p2/i2` head)

## Goal
`tl_tui/backlog_text.py` (Textual-free; TW3 reuses it) and `BacklogScreen(client, project)`: the dashboard tile of the brief as a small log, two views of the same IWP list: backlog weeks per foreman (`b`, default) and the sizing list (`z`): IWPs outside `awp.iwp.size_hours`. Models as T07b (`docs/tickets/P2-I2/T07b-iwp-screens.md`); skill `tui-layout`.

## Definitions (decided here, D34; pure, tested by the acceptance script)
- Backlog counts the IWPs in state `Ready` or `Issued` of a foreman (`-` row: no foreman). Weeks of one IWP = `ceil(((planned_finish - planned_start).days + 1) / 7)`, at least 1; an IWP without both dates adds 0 weeks and counts in `undated`. Foreman weeks = the sum. Status `below target` when weeks < `awp.backlog.target_weeks`, else `at or above target`. Nothing is refused; it is a view.
- Sizing: `size_flag(hours, low, high)` -> `""` (hours None or inside `[low, high]`), `"oversize"` (> high), `"undersize"` (< low). Same words as the handler's `iwp_oversize` and `iwp_undersize`, shown as `over size` and `under size`.
Settings: `client.get_setting("awp.backlog.target_weeks", project=project).effective.value` (int) and `("awp.iwp.size_hours", ...)` (`[low, high]`); read once per load, not per row.

## Interfaces (create; names exact)
```python
# backlog_text.py
BACKLOG_COLUMNS = ("Foreman", "IWPs", "Weeks", "Target", "Status", "Undated")
SIZING_COLUMNS = ("Number", "Subject", "State", "Hours", "Bounds", "Flag")
def iwp_weeks(planned_start, planned_finish) -> int          # 0 when a date is missing
def backlog_rows(rows, target_weeks) -> list[BacklogRow]      # foreman order by name, `-` last; rows are IwpRow
def size_flag(hours, low, high) -> str
def sizing_rows(rows, low, high) -> list[IwpRow-with-flag]    # only flagged, by number
def backlog_cells(row, labels=None) / sizing_cells(row, labels=None) -> tuple[str, ...]; def backlog_summary(rows, target_weeks) -> str   # `3 foremen, 2 below the 4-week target`
```
Keys: `b` backlog, `z` sizing, `F5`, `Esc`. `KEY_HINTS` `b backlog  z sizing  F5 reload  Esc back`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` lines 1-100, `widgets/cwp_register.py` (all), `widgets/log_screen.py` lines 96-225
- `packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py` lines 41-56, `handlers/iwp.py` lines 168-190 (size_bounds), `tests/fakes_iwp.py` (`seed_iwp`: add settings answers if `FakeClient.get_setting` has none: extend `fakes_iwp.py` only), `tests/helpers.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/backlog_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/backlog_screen.py` (create)
- `packages/tl-tui/tests/fakes_iwp.py` (settings answers only), `dev/accept/P2-I2/T08.py` (create), `docs/reports/P2-I2/T08.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T08.py            # no pytest
```
`T08.py`: `PASS weeks` (`iwp_weeks` for 1 day = 1, 14 days inclusive = 2, 15 = 3, missing = 0); `PASS backlog` (a hand-made IwpRow list: two foremen, one `-`, Draft rows ignored, status below and at-or-above target, undated counted); `PASS sizing` (hours None, 59, 60, 850, 851 against `[60, 850]` -> `""`, under, `""`, `""`, over); `PASS mount 80` and `PASS mount 170` (Textual pilot on `FakeClient` + `seed_iwp`; no overflow; panel at 170 shows heading and summary); `PASS keys` (`z` swaps the columns, `b` returns); `PASS words` no 32-hex id. Ends `T08 ok`.

## Escalation triggers
- Stop if `get_setting` is not on `ClientInterface` for the fake, or the weeks rule needs a field `IwpRow` lacks.

## Tests to add
None (S5 / T-screens twins hold the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; the `tui-layout` checklist answered line by line (7 lines). Subject `P2-I2-T08: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
