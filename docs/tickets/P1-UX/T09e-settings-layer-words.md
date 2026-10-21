# P1-UX-T09e — about:config: the layer a change goes to in plain words

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tui, tests
Depends on: T09b (merged)
Branch: `p1/ux-t09e-settings-layer-words`

## Goal
T09b left two raw layer ids on the about:config screens (review leftovers): the setting panel line `change goes to project:P1` and the
edit form line `at project:P123`. In plain mode both name the layer in words (`Project P123`, `Company`, `User`); technical mode keeps the raw id.

## Brief references (pasted)
> D13/T09b: layer names are plain words in plain mode (`Company`, `Project P123`, `User`) via `settings_text.layer_label`; the raw `project:P123` is an internal key.
> Mode is read with `mode_of(self.app).technical`; a screen whose text depends on it defines `refresh_for_display_mode(self) -> None` (SettingsScreen already does).

## Interfaces (verbatim from repo)
```python
# tl_tui/settings_text.py (merged)
def layer_label(layer: str) -> str       # "project:P123" -> "Project P123"; "company" -> "Company"; "user:kim" -> "User"; unknown kind: as stored
def detail_lines(view: SettingView, target: str | None, *, technical: bool = False) -> list[str]
#   ... f"change goes to {target if target is not None else 'nowhere: platform default only'}",
# widgets/setting_form.py (merged), SettingForm.compose():
#   where = "company" if self.action in ("lock", "unlock") else self.target
#   yield Static(f"at {where}", markup=False, id="form-layer")
# widgets/settings_screen.py:167: detail.update("\n".join(detail_lines(view, self.target(view), technical=technical)))
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/settings_text.py` (`detail_lines`, `layer_label`)
- `packages/tl-tui/src/tl_tui/widgets/setting_form.py` (`compose`)
- `packages/tl-tui/tests/test_settings_text.py` (line 66), `test_settings_screen.py` (lines 83, 122, 197)

## Allowed paths
- `packages/tl-tui/src/tl_tui/settings_text.py`, `packages/tl-tui/src/tl_tui/widgets/setting_form.py`
- `packages/tl-tui/tests/test_settings_text.py`, `test_settings_screen.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_settings_plain.py` (create)
- `packages/tl-tui/tests/__snapshots__/test_snapshots_settings/*` (only if a snapshot shows the form or the panel line)
- `docs/reports/P1-UX/T09e.md` (create)

## Steps
1. `detail_lines`: the `change goes to` target is `layer_label(target)` unless `technical` (raw target). `None` keeps `nowhere: platform default only`.
2. `SettingForm.compose`: `where` passes through `layer_label` unless `mode_of(self.app).technical`; the lock/unlock case (`company`) reads `Company`.
3. Update the pinned expectations: `change goes to Project P1`; `at Project P123`; `at Company`. Keep one technical assertion for each of the two lines.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_settings_text.py packages/tl-tui/tests/test_settings_screen.py packages/tl-tui/tests/test_settings_plain.py packages/tl-tui/tests/test_admin_plain.py packages/tl-tui/tests/test_snapshots_settings.py
```
Gate paths: all exist at dispatch except `test_settings_plain.py` (new, this ticket creates it). Expected: `gate: PASS`. If a snapshot test fails, regenerate only `test_snapshots_settings` with `--snapshot-update` and name what changed. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_settings_plain.py` (TlApp on `FakeClient`, as `test_settings_screen.py` opens F9 and the form with `e`):
- `test_the_panel_and_the_form_name_the_layer_in_words` (`Project P123` present, `project:P123` absent, `find_technical(text) == []`).
- `test_technical_mode_shows_the_raw_layer_in_both_places` (flag on, then `refresh_for_display_mode()` on the settings screen; the open form is built after the flag).

## Report requirements
Standard report. One line per changed assertion.

## Escalation triggers
- Another raw `project:`/`user:` id shows on these two screens: list it; do not fix outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
