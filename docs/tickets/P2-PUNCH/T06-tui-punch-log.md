# P2-PUNCH-T06 — TUI: `punch_text.py`, the punch log, the record screen, palette glue

Status: staged (dispatch after T04 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T04
Branch: `p2/punch-t06-tui`
Worktree: harness-created under `/home/user/wt/punch/t06` (from `p2/punch` head)

## Goal
`tl_tui/punch_text.py` (Textual-free), `PunchLogScreen(client, project)` (the module's home log) and `PunchScreen(client, project, key)` (one item), reachable from the palette by id `punch`. No business logic: the screens call `list_punch_items`, `get_punch_item`, `get_punch_counts` and, for the three actions, `quality_command`. Models: `widgets/iwp_register.py`, `iwp_text.py`, `docs/tickets/P2-I2/T07b-iwp-screens.md`. Load the `tui-layout` skill.

## Interfaces (create; names exact)
```python
# punch_text.py
PUNCH_COLUMNS = ("Number", "Subject", "State", "Cat", "Area", "System", "Due", "Assignee")
PUNCH_DROP = ("Assignee", "System", "Area"); PUNCH_RIGHT = ()
def punch_cells(row, labels=None) -> tuple[str, ...]            # Due via awp_text.date_text; Assignee via actor_label
def punch_summary(counts, total, shown, *, state=None, overdue=False) -> str   # `7 punch items: 3 Open, 2 Cleared, 1 Verified, 1 Void` / `2 of 7 punch items, state Open, overdue`
def punch_page(detail, labels=None, technical=False, panel=False) -> Page   # identity `<key> · <subject>`, state line `Open · category A · due 2026-11-20`, summary line, sections Where (area, system, raised from), Work (assignee, cleared by and note, verified by), History (reopened n and reason, void reason)
```
Keys of the log: `s` next state filter, `c` next category filter, `o` toggles overdue, `m` toggles `assignee = the signed-in actor`, `F5` reload; Enter opens `PunchScreen`; `KEY_HINTS` `/ filter  s state  c category  o overdue  m mine  F5 reload  Esc back`. `PunchScreen`: `Esc` back, `F5` reload, `c` Clear (asks a note), `v` Verify (asks "are you sure"), `o` Reopen (asks a reason); each key is shown only for the states the S2 `RULES` table offers it in, builds the S2 command with the screen's actor and scope as `widgets/receipt_entry.py` `build_command` does, sends it with `client.quality_command` inside `LogScreen.attempt`-style handling so a refusal (the clearer verifying) reaches the status line, then reloads. An item is never shown by id.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` (`date_text`), `iwp_text.py`, `widgets/iwp_register.py` (all), `widgets/action_form.py` (public names), `widgets/receipt_entry.py` (lines 255-290)
- `packages/tl-tui/tests/fakes_punch.py` (T04: `seed_punch`), `docs/reports/P2-PUNCH/{T04,S2}.md`, `packages/tl-modules/quality/src/tl_mod_quality/actions.py` (RULES, names only)

## Allowed paths
- `packages/tl-tui/src/tl_tui/punch_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/punch_log.py` (create; both screens)
- `packages/tl-tui/src/tl_tui/commands.py` (one `AppCommand("punch", "Punch list: items by state, area and system", "", "punch")` row), `app.py` (the `punch` entry in the `screens` dict of `_push_awp`, its import, and one `action_punch`)
- `packages/tl-tui/tests/test_punch_text.py`, `test_punch_screens.py`, `test_punch_nav.py` (create); consequential pins in union form, listed: `test_palette.py`, `test_awp_nav.py`
- `docs/reports/P2-PUNCH/T06.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_punch_text.py packages/tl-tui/tests/test_punch_screens.py packages/tl-tui/tests/test_punch_nav.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_awp_nav.py
```

## Tests to add
- `test_punch_text.py`: cells, summary and page lines for each state from `seed_punch`; no 32-hex id; the overdue item is marked in the summary filter text only when asked.
- `test_punch_screens.py` (Textual pilot on `FakeClient`, model `test_materials_screens.py`): mounts at 80 and 170 columns without overflow, Subject not right of the third column; `s`, `c`, `o`, `m` change the row count; Enter pushes `PunchScreen`; on an Open item `c` asks a note and sends `ClearPunchItem`, on a Cleared one `v` sends `VerifyPunchItem`, a refusal from the fake shows on the status line; keys not offered for the state do nothing; `RecordNotFoundError` shows an error status, no traceback.
- `test_punch_nav.py`: the palette lists `punch`; choosing it shows `PunchLogScreen`.

## Escalation triggers
- A fact on a screen needs a field no row or detail carries (write which); the diff outside the two new files passes about 60 lines; a screen constructor or `LogScreen` needs a change.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-PUNCH-T06: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. The `tui-layout` checklist answered line by line (7 lines).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
