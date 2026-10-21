# P1-UX-T10 — Technical-details toggle: Ctrl+D, help, palette, refresh hook

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00 (merged)
Branch: `p1/ux-t10-technical-toggle`

## Goal
An admin presses `Ctrl+D` anywhere in the app and technical details switch on, and again off; a plain user gets the
one-line refusal and nothing changes. The key is in the help screen and the palette ("Technical details"). Every open
widget that can re-render is told to (`refresh_for_display_mode`). Also fixes a duplicate-hit nit in `find_technical`.

## Brief references (pasted)
> SCOPE clause 3: one key toggles a "technical details" mode. Off by default, per viewer, not remembered, offered only
> to admins; a plain user pressing the key gets a one-line refusal. The key is in the help screen and palette.
> D5/D7/D10: mode is in-memory `DisplayMode` on the app as `app.display_mode` (Textual owns `App.display`, so never
> that name); key `Ctrl+D`; palette entry "Technical details".
> App-level keys stay live under a modal (app.py `_modal_open`); the toggle must work with a modal open and must not open one.

## Interfaces (verbatim from repo)
```python
# tl_tui/display.py (T00, merged)
REFUSAL = "Technical details are for admins"
class DisplayMode:
    technical: bool = False
    def toggle(self, *, is_admin: bool) -> str:   # "" when switched, REFUSAL for a plain user
def mode_of(widget_or_app: object) -> DisplayMode  # reads .display_mode, else a plain default
def find_technical(text: str, labels: Labels | None = None) -> list[str]:
    hits: list[tuple[int, str]] = []
    for pattern in TECHNICAL_PATTERNS:
        hits.extend((match.start(), match.group(0)) for match in pattern.finditer(text))
    ...
    return [token for _, token in sorted(hits)]
# tl_tui/commands.py
@dataclass(frozen=True)
class AppCommand: id: str; label: str; keys: str; action: str   # action -> TlApp.action_<action>
# tl_tui/keymap.py
KeyEntry(context, keys, description, owner=None, binding=None)   # e.g. KeyEntry("App","Ctrl+O","Schema workbench: ...","TlApp","ctrl+o")
# tl_tui/app.py: TlApp.BINDINGS entries like Binding("ctrl+o", "schema", "Schema workbench", show=False)
#   self.is_admin: bool (set in __init__); def _say(self, text: str, severity: Severity = "info") -> None  (footer status)
#   def _modal_open(self) -> bool
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/app.py` (BINDINGS 74-106, `__init__` 108-135, `_say` 320, `action_schema`/`action_help` ~673-690)
- `packages/tl-tui/src/tl_tui/keymap.py` (App entries; add after the `Ctrl+O` entry)
- `packages/tl-tui/src/tl_tui/commands.py`
- `packages/tl-tui/src/tl_tui/display.py` (`find_technical` at the end), `packages/tl-tui/tests/test_display.py`
- `packages/tl-tui/tests/test_keymap.py` (do not edit; shows how an admin app and the pilot are built), `tests/helpers.py`
may explore: `packages/tl-tui/tests/test_app_admin.py` (admin app construction), `tests/test_palette.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/app.py`, `keymap.py`, `commands.py`, `display.py`
- `packages/tl-tui/tests/test_technical_toggle.py` (create), `packages/tl-tui/tests/test_display.py` (add tests only)
- `packages/tl-tui/tests/__snapshots__/test_snapshots_links/test_command_palette.raw` (regenerate) and any other
  stored snapshot or test the run shows pins the palette list or key map (name it in the report)
- `docs/reports/P1-UX/T10.md` (create)

## Steps
1. `TlApp.__init__`: `self.display_mode = DisplayMode()`. Binding `Binding("ctrl+d", "toggle_technical", "Technical details", show=False)`.
2. `action_toggle_technical(self)`: `text = self.display_mode.toggle(is_admin=self.is_admin)`. If `text`: `self._say(text, "warning")`, return.
   Else `self._say("Technical details on" if self.display_mode.technical else "Technical details off")`, then call
   `refresh_for_display_mode()` (no arguments) on every widget in `self.screen_stack` screens (the screen itself and
   `screen.walk_children()`) that has a callable attribute of that name. A hook that raises must not stop the others
   (catch `Exception`, say nothing; the next open renders correctly). No modal check: it works under a modal.
3. Keymap: `KeyEntry("App", "Ctrl+D", "Technical details on or off (admins)", "TlApp", "ctrl+d")`. Palette:
   `AppCommand("technical", "Technical details on or off (admins)", "Ctrl+D", "toggle_technical")` after the `schema` command.
4. `find_technical`: dedupe the hits by `(start, token)` before sorting (a dotless package ref such as `foo@1.2.3`
   matches both `PACKAGE_PATTERN` and `CALENDAR_REF_PATTERN`). Regression test in `test_display.py`: `find_technical("foo@1.2.3") == ["foo@1.2.3"]`
   and `find_technical("co.acme.engineering@3.2.0")` still returns one token.
5. Regenerate the snapshot(s) this changes, once, with `--snapshot-update`; run again without it.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_technical_toggle.py packages/tl-tui/tests/test_display.py packages/tl-tui/tests/test_keymap.py packages/tl-tui/tests/test_palette.py -q
uv run pytest packages/tl-tui/tests/test_snapshots_links.py::test_command_palette --snapshot-update -q
uv run pytest packages/tl-tui/tests/test_snapshots_links.py -q
```
Expected: pass; only the palette snapshot (and any named in the report) changes. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_technical_toggle.py` (pilot, fake client; build the app as `test_app_admin.py` does):
- `test_admin_ctrl_d_switches_technical_mode_on_and_off` (`app.display_mode.technical` True, then False; footer says "Technical details on" / "off").
- `test_plain_user_gets_the_refusal_and_mode_stays_off` (footer shows `REFUSAL`).
- `test_the_key_works_with_a_modal_open_and_opens_none` (press `f1`, then `ctrl+d`; screen is still `HelpScreen`; mode flipped for an admin).
- `test_toggle_calls_refresh_hooks_on_open_screens` (push a probe `ModalScreen` with a child widget defining `refresh_for_display_mode`; each is called once per toggle; a refused toggle calls none; a hook that raises does not stop the next).
- `test_palette_entry_runs_the_toggle` (`ctrl+p`, type "Technical", Enter; mode flipped for an admin).
- `test_mode_is_off_at_start_and_not_remembered` (a new `TlApp` has `technical False`).
`test_display.py`: the dedupe tests from step 4.

## Report requirements
Standard report. Name every snapshot or test file you regenerated or changed besides the palette one. For the dedupe
(F2 from T00 review): list the `display.py` line numbers and the mutants you ran on them (remove the dedupe; dedupe
by token only instead of `(start, token)`) and which test killed each.

## Escalation triggers
- `ctrl+d` does not reach the app binding when the grid or a record view has focus (Textual's `Input` binds `ctrl+d`
  for delete-right: it must still reach the app when no Input has focus). Write the focus where it fails; do not pick another key.
- A test that "must not be edited" fails after the keymap/palette entries are added.
- The change needs a file outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
