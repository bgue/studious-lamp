# P1-UX-T11b — Carry-overs: palette refusal, remote hidden=missing, grid Ver, settings kinds

Status: ready (staged: dispatch when T08c is merged; disjoint from T11)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T10, S2, T09e, T08c (merged)
Branch: `p1/ux-t11b-carry-overs`

## Goal
Four small leftovers, each with its test. (a) T10 review F1: a plain user who runs the palette entry "Technical details" is refused with the one-line refusal and the mode stays off. (b) S2 review F1: on the remote client (real API on loopback) a record screen for a restricted id reads exactly like one for a missing id. (c) Q6, decision D39: the grid's `Ver` column shows only in technical mode (plain default columns omit it). (d) Q7, D39: settings list and origin rows capitalise the layer kind words in plain (`Company ●`); technical keeps `company ●`.

## Brief references (pasted)
> D19: the palette toggle entry is ungated; the refusal lives in `DisplayMode.toggle`. D20: record header `v{version}` is hidden in plain. D35/Q6/Q7: grid `Ver` and lowercase settings kinds decided by T11. D39 (orch): Q6 keep `Ver` only in technical; Q7 capitalise the kind words in plain.
> ADR-0016: a hidden record answers as one that never existed. Tests that read a restricted record run under `use_viewer(LOWEST)`.

## Interfaces (verbatim from repo; grid abridged as of c52873d, T08c changes the tuple: re-read before editing)
```python
# tl_tui/widgets/grid.py   GridColumn("version", "Ver", 3, "right")   (in the default column tuple)
# tl_tui/settings_text.py  _LAYER_WORDS: dict[str, str] = {"company": "Company", "project": "Project", "user": "User"}
# tests/test_record_screen.py (pattern)  hidden = seed_hidden_world(db, service, tmp_path); hidden.ids["restricted"|"privileged"|"bogus"|"open"]; _text_of_record_screen(client, record_id, tmp_path)
# tests/test_remote_client.py (pattern)  with harness.live(actor) as server: RemoteClient(server.base_url, server.token, ...)  (read its fixture use)
# tests/remote_support.py: SCOPE, LIVE_TIMEOUT_S, free_port, OtherWriter
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/grid.py` (column tuple, `refresh_for_display_mode`), `settings_text.py` (the rows that print `company`/`project`)
- `packages/tl-tui/tests/test_technical_toggle.py`, `test_record_screen.py` (lines 170-200), `test_remote_client.py` (first 80 lines), `test_settings_plain.py`
- `docs/reports/P1-UX/T09e.md` (where the lowercase kinds show)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/grid.py`, `settings_text.py`
- `packages/tl-tui/tests/test_technical_toggle.py` (add), `test_record_screen_remote.py` (create), `test_grid.py`, `test_settings_plain.py`, `test_settings_text.py` (add or update pins)
- Snapshots, only by regenerating the failing tests of `test_snapshots.py`, `test_snapshots_feed.py`, `test_snapshots_links.py`, `test_snapshots_settings.py` that show the grid header or the settings rows
- `docs/reports/P1-UX/T11b.md` (create)

## Steps
1. (a) Test: plain app (`is_admin=False`), `ctrl+p`, type `Technical`, Enter; `REFUSAL` is on screen, `app.display_mode.technical is False`. No source change expected; if the palette lets the entry through, stop (Blocked).
2. (b) Test `test_record_screen_remote.py`: seed the hidden world on the harness ledger; for `restricted`, `privileged`, `bogus` open `RecordScreen` through a `RemoteClient` of the plain viewer; text equals the text for a random unknown id, shows `No record`, contains neither the id nor the number. Admin sees `open`. If the harness cannot make a plain viewer, stop (Blocked).
3. (c) The default columns omit `Ver` when `mode_of(self.app).technical` is False; `refresh_for_display_mode` rebuilds them; the column chooser still lists Version, and a chosen set is kept as chosen. Same mechanism T08c used for its mode-aware headers.
4. (d) In plain the kind word of a layer on list rows and origin rows reads `Company`, `Project`, `User` (reuse `_LAYER_WORDS`); technical unchanged. Update pins; regenerate only snapshot tests that fail, name each in the report.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_technical_toggle.py packages/tl-tui/tests/test_record_screen_remote.py packages/tl-tui/tests/test_record_screen.py packages/tl-tui/tests/test_grid.py packages/tl-tui/tests/test_grid_filter.py packages/tl-tui/tests/test_column_chooser.py packages/tl-tui/tests/test_settings_text.py packages/tl-tui/tests/test_settings_plain.py packages/tl-tui/tests/test_settings_screen.py packages/tl-tui/tests/test_settings_parity.py packages/tl-tui/tests/test_snapshots.py packages/tl-tui/tests/test_snapshots_feed.py packages/tl-tui/tests/test_snapshots_links.py packages/tl-tui/tests/test_snapshots_settings.py packages/tl-tui/tests/test_app_shell.py packages/tl-tui/tests/test_live_app.py
```
Gate paths: all exist at dispatch except `test_record_screen_remote.py` (new). Expected `gate: PASS`. Regenerate with `uv run pytest <file> -k <test> --snapshot-update -q`; never a whole file.

## Tests to add
`test_technical_toggle.py`: `test_plain_user_is_refused_through_the_palette_entry`. `test_record_screen_remote.py`: `test_remote_hidden_record_reads_like_a_missing_one`, `test_remote_readable_record_opens`. `test_grid.py`: `test_ver_column_only_in_technical_mode`. `test_settings_plain.py`: `test_layer_kind_words_are_capitalised_in_plain_and_raw_in_technical`.

## Report requirements
Standard report; one line per snapshot regenerated and why.

## Escalation triggers
- (a) or (b) fails for a product reason (the refusal or hidden=missing is broken): stop, report as Blocked with the diff of the two texts.
- Hiding `Ver` moves more than 6 snapshots: do (a), (b), (d), report (c) as Blocked.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
