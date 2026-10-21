# P1-UX-T11 — Walking test: every screen the keymap opens, plain and technical

Status: ready (staged: dispatch when T08c and T09a are merged)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T01-T10, T13, T08b, T06b, T09d, T08c, T09a (all merged)
Branch: `p1/ux-t11-plain-walk`

## Goal
One test file walks every screen reachable from `keymap.py` and proves SCOPE clauses 2 and 3: as a plain user no rendered text has a technical token (`find_technical(text, labels) == []`); as an admin, Ctrl+D makes technical text appear and Ctrl+D again removes it. The screen list is generated from `KEYMAP`, never typed by hand (plan check F12). Leaks found in merged screens are fixed only when the fix is a label or mode argument in that screen's `*_text.py`; every other leak goes in the report as a follow-up list (file:line, the token, the screen).

## Brief references (pasted)
> SCOPE 2: no ULID, hash, schema version, internal key, clock or calendar id on any screen. SCOPE 3: the toggle shows these and hides them again; a plain user gets a one-line refusal.
> D14: widgets define `refresh_for_display_mode()`. D27: text functions default raw; widgets pass the mode. D36/D37: plain history needles, plain phases/percent/relationship types.

## Interfaces (verbatim from repo)
```python
# tl_tui/keymap.py
@dataclass(frozen=True) class KeyEntry: context: str; keys: str; description: str; owner: str | None = None; binding: str | None = None
KEYMAP: tuple[KeyEntry, ...]      # context "App": owner "TlApp", binding e.g. "f7", "ctrl+g", "ctrl+d", "n", "slash"
# tl_tui/display.py
def find_technical(text: str, labels: Labels | None = None) -> list[str]   # domain keys count only with labels
class DisplayMode: technical: bool; toggle(self, *, is_admin: bool) -> str   # "" or REFUSAL
# tl_tui/labels_load.py: load_labels(client, scope, record_types=("core.Record",)) -> Labels
# tests: helpers.run_pilot(app, scenario, size=(120, 40)); helpers.screen_text(app) (current screen only)
#        fakes.FakeClient(), fakes.SCOPE; app = TlApp(FakeClient(), scope=SCOPE, actor="user:kim", is_admin=False)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/keymap.py` (App entries), `display.py` (lines 140-185)
- `packages/tl-tui/tests/test_technical_toggle.py` (pilot pattern), `helpers.py`, `fakes.py` (lines 216-260, `add_stored_record`)
- `packages/tl-tui/tests/test_record_plain.py` (how a plain record screen is read)

## Allowed paths
- `packages/tl-tui/tests/test_plain_walk.py` (create)
- Only if the walk finds a leak: `packages/tl-tui/src/tl_tui/*_text.py` EXCEPT `settings_text.py` (T11b), and the pinned test of the module you change
- `docs/reports/P1-UX/T11.md` (create)

## Steps
1. `walk_keys()` returns the KEYMAP entries with `context == "App"` and a `binding`, minus `EXCLUDED = {"ctrl+q": "quits", "escape": "closes a panel", "ctrl+d": "tested below"}`. `test_every_app_key_is_walked_or_excluded` fails if a binding is in neither (a new key forces a decision).
2. `walk(app, labels)` presses each binding from the grid, then again with a record open (move to the first row, Enter). After each key: settle, read the whole stack's text (`app.screen` plus, for a modal, its parent is not needed), also press the view-only keys the opened screen lists in its `KEY_HINTS` (digits, `t`, `m`, `h`; never a key that edits, creates, disables or sends), collect `(binding, text)`, then `escape` until the grid is back. Help (F1): use `help_text()`; its scroll box hides lines. The record screen is opened from each register by Enter on its first row; read tabs 1-5.
3. Tests: `test_plain_user_walk_has_no_technical_text` (labels from `load_labels(client, SCOPE)`; the assertion message lists binding and tokens); `test_admin_ctrl_d_walk_shows_technical_text_then_hides_it` (Ctrl+D on: the documents register (F7), the tag register (F8) and a record screen Details each give `find_technical != []`; Ctrl+D off: every walked text is `[]` again); `test_every_app_key_is_walked_or_excluded`; `test_walk_reaches_the_screens` (the walk saw at least: help, document register, tag register, correspondence, schedule, review queue, integration registry, schema workbench, about:config, accounts (admin), domain screen).
4. Leak found: fix only as allowed above, add one assertion to the module's own test, name it in the report. Else list it in the report under "Follow-up leaks"; keep the walk green by listing the screen in `KNOWN_LEAKS = {binding: token}` with a comment `# follow-up`, never by weakening `find_technical`.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_plain_walk.py packages/tl-tui/tests/test_technical_toggle.py packages/tl-tui/tests/test_display.py packages/tl-tui/tests/test_keymap.py
```
Gate paths: all exist at dispatch except `test_plain_walk.py` (new). Add the test file of every `*_text.py` you changed. Expected `gate: PASS`. Never regenerate a snapshot.

## Tests to add
`packages/tl-tui/tests/test_plain_walk.py`: the four tests above.

## Report requirements
Standard report. Table of walked bindings (binding, screen, plain hits, admin-technical hits). "Follow-up leaks" list. Fixes made, one line each.

## Escalation triggers
- A leak needs a change outside `*_text.py` (widget, client, schema): list it, do not fix it.
- The fake client cannot serve a screen: say which; do not edit `fakes*.py`.
- More than 10 leaks: stop after the report; the supervisor splits.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
