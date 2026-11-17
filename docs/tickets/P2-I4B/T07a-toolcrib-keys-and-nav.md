# P2-I4B-T07a — Toolcrib keys (F2 issue, F3 return, Ctrl+R kept) and its place in the palette

Status: ready (dispatch now; needs T06 only)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06 (merged)
Branch: `p2/i4b-t07a-toolcrib-nav`
Worktree: `/home/user/wt/i4b/t07a` (from `p2/i4b` head)

## Goal
Settle decision D11 and make the toolcrib screen reachable. Ctrl+I is Tab in a terminal, so the issue mode has had no working key. Issue is `F2`, return is `F3`, and `Ctrl+R` stays as the second key for return. The default mode stays issue, so the screen is usable with the keyboard alone from the first line. Then register the screen: a palette entry `toolcrib` (no key) and `TlApp.action_toolcrib`. Wiring only, at most 60 lines outside pins and tests: no screen logic (L-P2-WEB1-1). Model: `docs/tickets/P2-I4A/T07d-tui-glue.md`.

## Brief
1. `packages/tl-tui/src/tl_tui/toolcrib_text.py`: `KEYS = "Enter send  F2 issue  F3 return  Ctrl+R return  Esc close"`; nothing else in the module changes (the provided test does not read KEYS or any key).
2. `widgets/toolcrib_screen.py`: the BINDINGS become `f2` -> `mode('issue')`, `f3` -> `mode('return')`, `ctrl+r` -> `mode('return')`; the docstring lines 3-4 name the new keys. Check `packages/tl-tui/src/tl_tui/keymap.py` and `app.py` BINDINGS for `f2` and `f3`: the modal's own bindings win while it is open, but if an app-level `f2` or `f3` binding is `priority=True` write which under Blocked and stop.
3. `commands.py`: one `AppCommand("toolcrib", "Toolcrib: issue and return a tool in one line", "", "toolcrib")`, next to the materials rows.
4. `app.py`: `action_toolcrib` beside `action_stock`: do nothing when a modal is open (`self._modal_open()`); project from `project_of_scope(self.scope)` (a notice "The toolcrib needs a project." as `_push_awp` words its own when none); read `self.client.list_materials_locations(project)` under `CLIENT_ERRORS` (notice `describe_error`), choose `crib_choices(locations)[0]` (first toolcrib code by sort), and push `ToolcribScreen(self.client, project, self.actor, crib)`; with no toolcrib the notice is `No toolcrib in this project. Add a location of kind toolcrib.` (warning). A project with several cribs opens the first by code: a crib choice screen is out of scope (note it in the report).

## Context (read these, nothing else)
- `docs/reports/P2-I4B/T06.md`, `packages/tl-tui/src/tl_tui/toolcrib_text.py` (KEYS, `crib_choices`), `widgets/toolcrib_screen.py`
- `packages/tl-tui/src/tl_tui/app.py` (`_push_awp`, `action_stock`, `_modal_open`), `commands.py`, `keymap.py` (grep `f2`, `f3`)
- `packages/tl-tui/tests/test_requisition_nav.py` (the pilot pattern), `tests/fakes_materials.py` (locations a test can load; a location of kind `toolcrib` and one stock row for a lot)

## Allowed paths
- `packages/tl-tui/src/tl_tui/toolcrib_text.py` (KEYS only), `packages/tl-tui/src/tl_tui/widgets/toolcrib_screen.py` (BINDINGS and docstring), `packages/tl-tui/src/tl_tui/commands.py`, `packages/tl-tui/src/tl_tui/app.py` (`action_toolcrib` only)
- consequential pins (union form, listed): `packages/tl-tui/tests/test_palette.py`, `test_keymap.py`, `test_awp_nav.py`, any palette-count pin the gate shows
- `packages/tl-tui/tests/test_toolcrib_nav.py` (create), `docs/reports/P2-I4B/T07a.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_toolcrib_nav.py packages/tl-tui/tests/test_toolcrib_text.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_keymap.py packages/tl-tui/tests/test_awp_nav.py
```
Do not edit `test_toolcrib_text.py` or its provided copy. Also run once `uv run python dev/accept/P2-I4B/T06.py` (its drive keys: change a Ctrl+I press to F2 if it uses one; it is outside Allowed paths only as a consequential edit, list it).

## Tests to add
`packages/tl-tui/tests/test_toolcrib_nav.py` (headless pilot on `FakeClient` with a toolcrib location and one tool in stock, `tl_tui.app.TlApp` as `test_requisition_nav.py` builds it):
- the palette lists `toolcrib`; choosing it shows `ToolcribScreen` for the first crib code;
- `KEYS` names F2, F3 and Ctrl+R and not Ctrl+I; the screen's BINDINGS hold `f2`, `f3`, `ctrl+r` and no `ctrl+i`;
- `f3` sets the title to the return mode, `f2` back to issue, `ctrl+r` to return; the typed line and the focus stay;
- with no toolcrib location the palette entry leaves the app on its own screen and shows the notice; with a modal open the entry does nothing;
- one line `<lot> Ana Ruiz` + Enter in issue mode posts one `IssueStock` (the fake records the command) and clears the line.

## Escalation triggers
- An app-level `f2`/`f3` binding is priority; the screen needs a change beyond bindings; the diff passes about 60 lines outside tests.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4B-T07a: ...`; the commit body ends with the trailer lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
