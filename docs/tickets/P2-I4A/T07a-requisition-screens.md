# P2-I4A-T07a — `requisition_text.py`, requisition log and record page

Status: staged (dispatch after T04c2 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T04c2
Branch: `p2/i4a-t07a-requisition-screens`
Worktree: harness-created under `/home/user/wt/i4a/t07a` (from `p2/i4a` head)

## Goal
`tl_tui/requisition_text.py` (Textual-free) and `RequisitionLogScreen(client, project)` (the module's home log) with `RequisitionScreen(client, project, key)` (one requisition: summary, kind fields, work order). Models: `docs/tickets/P2-I2/T07b-iwp-screens.md`, `widgets/iwp_register.py`; load the `tui-layout` skill. No business logic: the screens call `list_requisitions` and `get_requisition` only. Palette and navigation are T07d.

## Interfaces (create; names exact)
```python
# requisition_text.py
REQ_COLUMNS = ("Number", "Subject", "Kind", "State", "Priority", "Need by", "Requester")
REQ_DROP = ("Requester", "Need by", "Priority"); REQ_RIGHT = ()
def req_cells(row, labels=None) -> tuple[str, ...]          # Kind as a word (labour, material, general, scaffold), Need by via awp_text.date_text, Requester actor_label
def req_summary(total, shown, *, kind=None, state=None) -> str    # `7 requisitions` / `3 of 7 requisitions, state Requested`
def req_page(detail, labels=None, technical=False, panel=False) -> Page   # identity `<key> · <subject>`, state line, summary line, sections Detail (the kind fields as property:value lines), Work order (`<key> · <state>` or `none yet`)
```
Keys of the log: `k` next kind filter, `s` next state filter, `m` toggles `requester = the signed-in actor`, `F5` reload; Enter opens `RequisitionScreen`; `KEY_HINTS` `/ filter  k kind  s state  m mine  F5 reload  Esc back`. `RequisitionScreen`: Esc back, `F5`, text only. Words shown say "labour"; a requisition is never shown by id.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` (`hours_text`, `date_text`), `iwp_text.py`, `widgets/iwp_register.py` (all), `widgets/log_screen.py` (lines 96-225)
- `packages/tl-tui/tests/fakes_requisitions.py` (T04c2: `seed_requisitions`), `docs/reports/P2-I4A/T04c2.md`

## Allowed paths
- `packages/tl-tui/src/tl_tui/requisition_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/requisition_register.py` (create; both screens)
- `packages/tl-tui/tests/test_requisition_text.py`, `packages/tl-tui/tests/test_requisition_screens.py` (create)
- `docs/reports/P2-I4A/T07a.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_requisition_text.py packages/tl-tui/tests/test_requisition_screens.py
```

## Tests to add
- `test_requisition_text.py`: cells, summary and page lines for each kind from `seed_requisitions`; no 32-hex id; "labour" not "labor" in any shown word.
- `test_requisition_screens.py` (Textual pilot on `FakeClient`, model `test_materials_screens.py`): mounts at 80 and 170 columns without overflow, Subject not right of the third column; `k`, `s`, `m` change the row count; Enter pushes `RequisitionScreen` showing the work order section; `RecordNotFoundError` shows an error status, no traceback.

## Escalation triggers
- A fact on a screen needs a field no row or detail carries (write which); never read per row.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T07a: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. The `tui-layout` checklist answered line by line (7 lines).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
