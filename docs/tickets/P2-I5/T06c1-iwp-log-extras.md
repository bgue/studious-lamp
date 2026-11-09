# P2-I5-T06c1 — IWP log extras: Ready and Blocking counts, state-since, filters in the summary, backlog past 200, `mine` at open

Status: staged (needs T11b merged; `list_iwp_counts` and the fake)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T11b
Branch: `p2/i5-t06c1-iwp-log`
Worktree: harness-created under `/home/user/wt/i5/t06c1` (from `p2/i5` head)

## Goal
The IWP log shows what a foreman and a planner scan by: how many readiness checks pass, how many blocking constraints are open, and since when the IWP is in its state. The summary counts the discipline and text filters. The backlog reads past 200 IWPs. The log can open with the `m` (mine) filter already on, which T06c2 uses for the landing. These close the P2-I2 follow-ups (STATE FOLLOW-UPS, DEFERRED row "P2-I2 small follow-ups"; the `m` key already exists).

## Brief references (pasted)
- Text (Textual-free, `tl_tui/iwp_text.py`; the web page shares `IWP_COLUMNS`, `iwp_cells`, `iwp_summary`: leave their output unchanged): add `IWP_COUNT_COLUMNS = (*IWP_COLUMNS, "Ready", "Blocking", "Since")`, `IWP_COUNT_DROP = (*IWP_DROP, "Since")`, `IWP_COUNT_RIGHT = (*IWP_RIGHT, "Ready", "Blocking")` and `iwp_count_cells(row, counts, labels=None) -> tuple[str, ...]` = `iwp_cells(...)` plus `ok/total` (`—` when `counts` is None or not `evaluated`), `open_blocking` as text, `state_since` as `date_text`. Extend `iwp_summary(total, shown, *, state=None, foreman=None, discipline=None, text=None)`: with either new argument the form is `3 of 7 IWPs, state Ready, discipline Piping, filter 'rack'`; with neither, output is byte-identical to today.
- Screen (`widgets/iwp_register.py`): `__init__(client, project, *, mine: bool = False)` sets `self.mine`; `load_rows` also reads `client.list_iwp_counts(project)` into `self.counts: dict[str, IwpCountRow]` (by number; a missing row reads as no counts); `columns` returns `IWP_COUNT_COLUMNS`, `drop_order` `IWP_COUNT_DROP`, `row_cells` `iwp_count_cells`; `summary_text` passes the discipline label and the filter text to `iwp_summary` (the discipline and text filters work on the rows held: the counts follow the shown rows because the summary counts `self.shown`).
- Backlog (`widgets/backlog_screen.py` line 91): `self.client.list_iwps(self.project, limit=500)`; when 500 rows come back the summary says `first 500 IWPs`.
- The panel and `IwpScreen` are unchanged.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/iwp_text.py` (1-112), `packages/tl-tui/src/tl_tui/widgets/{iwp_register.py (1-150), backlog_screen.py (60-130)}`
- `packages/tl-tui/tests/{fakes_week.py (T11b: `load_counts`), fakes_iwp.py (`seed_iwp`)}`, `dev/accept/P2-I2/T07b.py` (what pins the old columns), `docs/reports/P2-I5/T11a1.md`

## Allowed paths
- `packages/tl-tui/src/tl_tui/iwp_text.py`, `packages/tl-tui/src/tl_tui/widgets/{iwp_register.py, backlog_screen.py}`
- `packages/tl-tui/tests/test_iwp_text_counts.py`, `packages/tl-tui/tests/test_iwp_register_counts.py` (create)
- `docs/reports/P2-I5/T06c1.md`; consequential pins: `dev/accept/P2-I2/T07b.py` and `T08.py` if they assert the eight-column header of the log (keep a counterpart that pins `IWP_COLUMNS` itself, which the web still shows); list each

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_iwp_text_counts.py packages/tl-tui/tests/test_iwp_register_counts.py packages/tl-web/tests/test_web_TW1.py
uv run python dev/accept/P2-I2/T07b.py
```

## Tests to add
`test_iwp_text_counts.py` (pure): the three new cells for evaluated, never evaluated and `counts=None`; `iwp_summary` unchanged for the old calls (assert the old strings) and the new form with discipline and text; `IWP_COLUMNS` unchanged. `test_iwp_register_counts.py` (pilot over `FakeClient` with `seed_iwp` and `load_counts`): the log shows `2/3` and the blocking count; `d` changes the summary to name the discipline; the filter text shows in the summary; `IwpRegisterScreen(client, project, mine=True)` opens with only the actor's IWPs; the backlog asks `list_iwps` with `limit=500` (fake records the call).

## Escalation triggers
- `list_iwp_counts` lacks a number the log lists (the counts are by number); a snapshot test pins the log screen (list the file, update it).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T06c1: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
