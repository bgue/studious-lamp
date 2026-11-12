# P2-I4A-T07b — `work_order_text.py` and the work order backlog screen

Status: staged (dispatch after T04c2 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T04c2
Branch: `p2/i4a-t07b-work-order-backlog`
Worktree: harness-created under `/home/user/wt/i4a/t07b` (from `p2/i4a` head)

## Goal
`tl_tui/work_order_text.py` (Textual-free) and `WorkOrderBacklogScreen(client, project)` (the work order backlog: what is open, scheduled, assigned, started) with `WorkOrderScreen(client, project, key)` (one work order). Same shape and rules as T07a; reads `list_work_orders` and `get_work_order` only. Palette and navigation are T07d.

## Interfaces (create; names exact)
```python
# work_order_text.py
WO_COLUMNS = ("Number", "Kind", "State", "Assigned", "Planned start", "Planned finish", "Hours")
WO_DROP = ("Hours", "Planned finish", "Assigned"); WO_RIGHT = ("Hours",)
def wo_cells(row, labels=None) -> tuple[str, ...]       # Hours via awp_text.hours_text, dates via awp_text.date_text, Assigned actor_label
def wo_summary(total, shown, *, state=None, assigned_to=None) -> str   # `4 work orders` / `2 of 4 work orders, state Scheduled`
def wo_page(detail, labels=None, technical=False, panel=False) -> Page  # identity `<key> · <requisition key>`, state line, planned and actual dates, hours planned and actual
```
Keys: `s` next state filter (Open, Scheduled, Assigned, Started, Completed, Closed, none), `m` toggles `assigned_to = the signed-in actor`, `F5`; Enter opens `WorkOrderScreen`; `KEY_HINTS` `/ filter  s state  m mine  F5 reload  Esc back`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/{awp_text.py, backlog_text.py}`, `widgets/backlog_screen.py`, `widgets/iwp_register.py`, `widgets/log_screen.py` (lines 96-225)
- `packages/tl-tui/tests/fakes_requisitions.py`, `docs/reports/P2-I4A/T04c2.md`

## Allowed paths
- `packages/tl-tui/src/tl_tui/work_order_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/work_order_backlog.py` (create; both screens)
- `packages/tl-tui/tests/test_work_order_text.py`, `packages/tl-tui/tests/test_work_order_screens.py` (create)
- `docs/reports/P2-I4A/T07b.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_work_order_text.py packages/tl-tui/tests/test_work_order_screens.py
```

## Tests to add
- `test_work_order_text.py`: cells, summary and page lines from `seed_requisitions`'s two work orders; no 32-hex id; unset dates and hours print as the layout's empty value.
- `test_work_order_screens.py` (pilot on `FakeClient`): mounts at 80 and 170 columns without overflow; `s` and `m` change the row count; Enter pushes `WorkOrderScreen`; a missing key shows an error status, no traceback.

## Escalation triggers
- A fact on a screen needs a field no row or detail carries; never read per row.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T07b: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. The `tui-layout` checklist answered line by line (7 lines).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
