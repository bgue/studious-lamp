# P1-UX-T09b — Accounts and about:config screens in plain language

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00 (merged)
Branch: `p1/ux-t09b-admin-settings-plain`

## Goal
The accounts screen (F10) and the about:config screens (F9) show no internal ids, sequence numbers or service ids in
plain mode; technical mode shows them as today. Rows here are not records (accounts, tokens, settings), so there is no
Enter-to-record in this ticket.

## Brief references (pasted)
> SCOPE clause 2: hidden by default: record and event ids, hashes, internal keys, actor ids of services (`svc:...`; show
> the service's label). Clause 3: technical mode shows what plain mode hides.
> D13 (supervisor, reversible): setting keys such as `ui.theme` stay visible (they are the names a person sets and the CLI
> uses); token ids, change sequence numbers and `svc:` actor ids are technical-only.
> Mode is read with `mode_of(self.app).technical` (`app.display_mode`; T10 adds it, a test host without it reads as plain).
> A screen whose text depends on the mode defines `refresh_for_display_mode(self) -> None` (T10 calls it on a toggle).

## Interfaces (verbatim from repo)
```python
# tl_tui/display.py (merged)
class Labels: type_titles; code_labels; domains; subtypes; services: Mapping[str, str]   # all default empty
def actor_label(labels: Labels, actor: str) -> str   # svc:x -> labels.services[x] or "a service"; user:kim -> "kim"
def mode_of(widget_or_app: object) -> DisplayMode      # .technical: bool
# tl_tui/admin_text.py (today)
ACCOUNT_COLUMNS = ("Name", "Kind", "Roles", "Status", "Lock")
TOKEN_COLUMNS = ("Agent", "Label", "Expires", "State", "Id")
def token_cells(token: AgentTokenView, names: dict[str, str], now: str) -> tuple[str, str, str, str, str]:
    # (names.get(token.account_id, "?"), token.label, expires, token_state(token, now), token.token_id)
# tl_tui/settings_text.py (today)
def history_cells(change: SettingChange) -> tuple[str, str, str, str, str, str]:
    # (str(change.seq), change.layer, time, change.actor, moved, change.reason or "")
def detail_lines(view: SettingView, target: str | None) -> list[str]:
    # ... for change in e.scheduled: f"scheduled {change.applies_at} {format_value(change.new_value)} (seq {change.seq})"
# widgets/setting_history.py: COLUMNS = ("#", "Layer", "When (UTC)", "By", "Change", "Reason");
#   on_mount adds columns; reload() fills; _say(f"Only the latest change at {change.layer} can be undone (#{latest.seq}).")
# widgets/admin_screen.py: on_mount adds ACCOUNT_COLUMNS / TOKEN_COLUMNS; _fill(keep) rebuilds both tables
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/admin_text.py`, `settings_text.py`
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py`, `setting_history.py`, `settings_screen.py` (detail panel calls `detail_lines`)
- `packages/tl-tui/tests/test_admin_text.py`, `test_settings_text.py`, `test_admin_screen.py` (line ~233 pins the token columns)
may explore: `packages/tl-tui/tests/fakes_admin.py`, `fakes_settings.py`, `test_snapshots_settings.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/admin_text.py`, `settings_text.py`
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py`, `setting_history.py`, `settings_screen.py`
- `packages/tl-tui/tests/test_admin_text.py`, `test_settings_text.py`, `test_admin_screen.py`, `test_settings_screen.py` (update pinned expectations)
- `packages/tl-tui/tests/test_admin_plain.py` (create)
- `packages/tl-tui/tests/__snapshots__/test_admin_screen/*` (regenerate the one that shows the token table)
- `docs/reports/P1-UX/T09b.md` (create)

## Steps
1. `admin_text`: `TOKEN_COLUMNS = ("Agent", "Label", "Expires", "State")` and `TECHNICAL_TOKEN_COLUMNS = (*TOKEN_COLUMNS, "Id")`;
   `token_cells(token, names, now, *, technical: bool = False)` returns the fifth cell only when `technical`.
2. `settings_text`: `history_cells(change, labels: Labels | None = None, *, technical: bool = False)`: plain drops the seq cell and shows
   `actor_label(labels or Labels(), change.actor)` in By; technical returns today's six cells unchanged. `detail_lines(view, target, *, technical=False)`:
   the `scheduled` line ends `(seq N)` only when technical. Add `HISTORY_COLUMNS` / `TECHNICAL_HISTORY_COLUMNS` the same way as tokens.
3. Screens read `technical = mode_of(self.app).technical` where they fill. `AdminScreen`: build the token columns from the mode
   (`table.clear(columns=True)` then `add_columns`) in `_fill` or a helper; `SettingHistory`: same for its columns, and drop the
   `(#N)` from the undo message in plain mode (`... can be undone.`). `SettingsScreen` passes the flag to `detail_lines`.
4. Each of `AdminScreen`, `SettingHistory`, `SettingsScreen` defines `refresh_for_display_mode(self)` that re-fills with the cursor kept
   (use the existing reload/_fill; do not add a new read path).
5. Update the pinned expectations in the existing tests to the plain default and keep one technical-mode assertion where each pinned the old text.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_admin_text.py packages/tl-tui/tests/test_settings_text.py packages/tl-tui/tests/test_admin_screen.py packages/tl-tui/tests/test_settings_screen.py packages/tl-tui/tests/test_admin_plain.py packages/tl-tui/tests/test_app_admin.py -q
uv run pytest packages/tl-tui/tests/test_admin_screen.py packages/tl-tui/tests/test_snapshots_settings.py --snapshot-update -q
uv run pytest packages/tl-tui/tests/test_admin_screen.py packages/tl-tui/tests/test_snapshots_settings.py -q
```
Expected: pass; only snapshots that showed the token Id column or a seq change. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_admin_plain.py` (pilot on the fake client; host app sets `app.display_mode = DisplayMode()`):
- `test_plain_token_table_has_no_id_column_and_no_token_id_in_the_text` (rendered text contains none of the fake token ids; `find_technical(text) == []`).
- `test_technical_mode_shows_the_id_column` (set `display_mode.technical = True`, call `refresh_for_display_mode()`, Id column and ids present; then off again hides them).
- `test_history_plain_drops_seq_and_names_a_service_actor_as_a_service` (a change by `svc:enricher` reads `a service`, no `svc:`); technical shows `svc:enricher` and the `#` column.
- `test_the_undo_message_has_no_sequence_number_in_plain_mode`.

## Report requirements
Standard report. List the existing assertions you changed and why (one line each). Name the snapshots regenerated.

## Escalation triggers
- Plain text still shows a ULID, hash, `svc:` or `name@x.y.z` somewhere on these screens that this ticket does not name: list it, do not fix outside Allowed paths.
- A fake lacks a way to produce a service actor or token: add it to the fake only if the fake file is in Allowed paths, else stop.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
