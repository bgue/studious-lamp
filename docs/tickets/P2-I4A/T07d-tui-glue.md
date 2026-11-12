# P2-I4A-T07d — TUI glue: palette, navigation, technical rows

Status: staged (dispatch after T07a and T07b merge)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T07a, T07b
Branch: `p2/i4a-t07d-tui-glue`
Worktree: harness-created under `/home/user/wt/i4a/t07d` (from `p2/i4a` head)

## Goal
Make the two screens reachable. Wiring only, at most 60 lines outside pins: no screen logic (L-P2-WEB1-1). Model: `docs/tickets/P2-I2/T07c-screen-glue.md`.

## Brief
1. `packages/tl-tui/src/tl_tui/commands.py`: two `AppCommand` rows (key `""`) `requisitions` (requisition log, `RequisitionLogScreen(client, project)`) and `work-orders` (`WorkOrderBacklogScreen(client, project)`); in `app.py` the two classes in the `screens` dict of `_push_awp` and two one-line actions `action_requisitions`, `action_work_orders` beside `action_iwps`.
2. `RequisitionScreen`: add `Binding("w", "work_order", ...)` pushing `WorkOrderScreen` for its work order key when it has one (local import; no binding if none); hint `w Work order`. Do not touch the log screens' bindings.
3. Technical-mode rows: in technical mode the log and page show the record id as the other registers do (follow `iwp_text`: no new rule).
4. The record actions (approve, reject, cancel, schedule, assign, start, complete, close) come from the S2 `actions.py` rules through the generic record screen: this ticket does not build them; the test pins that `RecordScreen` for an approved requisition lists them. If it does not, write which under Blocked.

## Context (read these, nothing else)
- `docs/reports/P2-I4A/{T07a,T07b}.md`, `widgets/requisition_register.py`, `widgets/work_order_backlog.py`, `app.py` (`_push_awp` only), `commands.py`
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/actions.py` (RULES, names only)

## Allowed paths
- `packages/tl-tui/src/tl_tui/commands.py`, `packages/tl-tui/src/tl_tui/app.py` (the `_push_awp` table and two actions), `packages/tl-tui/src/tl_tui/widgets/requisition_register.py` (`RequisitionScreen` binding only)
- consequential pins (union form, listed; `packages/tl-tui/tests/test_palette.py`, `test_awp_nav.py`)
- `packages/tl-tui/tests/test_requisition_nav.py` (create), `docs/reports/P2-I4A/T07d.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_requisition_nav.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_awp_nav.py
```

## Tests to add
`packages/tl-tui/tests/test_requisition_nav.py` (headless pilot on `FakeClient` with `seed_requisitions`): the palette lists `requisitions` and `work-orders`; choosing each shows the right screen; from the Approved requisition's screen `w` shows its work order and Esc returns; a requisition with no work order has no `w`; the record screen lists the S2 actions for the Approved requisition.

## Escalation triggers
- A screen constructor needs a change beyond the key binding; the diff passes about 60 lines; the generic record screen lacks the S2 actions.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T07d: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
D-r3f (orchestrator, 2026-11-11): brief item 4 (record-screen actions for requisitions and work orders) is out of this ticket: the generic record screen reads no action offers and `action_ui.ACTION_UI` has no requisition rows. Deferred (DEFERRED.md); the CLI covers every write and the demo reaches the TUI only through the palette. The rest passed review.
