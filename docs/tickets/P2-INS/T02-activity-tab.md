# P2-INS-T02 — Activity tab replaces History; owns `record_view.py` (INS-A3)

Status: draft (written round 1; the next round refreshes the pasted interfaces after S1 and T01 merge)
Tier: haiku
review: full
Labels: tui, tests, docs
Depends on: S1, T01 merged. B1's `ClientInterface.checks` is not needed here; S2 need not be merged
Branch: `p2/ins-t02-activity-tab`
Worktree: `/home/user/wt/ins-t02`

## Goal
The record screen's fourth tab is Activity (key `4`, and `h` as today), built from `ClientInterface.activity` and `record_activity_text`. `v` Revisions only (the same rows as today's History, through
`activity(revisions_only=True)`), `r` related on or off (default on), `/` text filter; the tab title shows the active filters. The same piece adds the Insights tab pane and its key `9`
as a stub widget that B2 (T03) fills, so `record_view.py` is edited only here (plan check F9). ADR-0025's "TUI History display" ticket folds in; Trace display stays. Intent "why": the base has none, so the `Why` column is absent (say so in the README line).

## Brief references (pasted; spec A0, A1.4; plan check F3)
- Record tab keys: `1` Details, `2` Properties, `3` Links, `4` Activity, `5` Trace, `6` Files, `T` Thread; `7` and `8` are reserved by other specs; **`9` Insights; never `n` or `I`** (global app keys). The log marker, `!` filter and panel line are not in this increment.
- Load lazily when the tab is first shown and again on `reload`, off the UI thread, first page 120 rows; a last row "Show older" (Enter) asks `next_before_seq`. A client error keeps the display and posts a status line (as `reload` does today). Reads are not logged.
- Revisions only: the table equals today's History cells (`history_columns`, `history_cells`), same order (oldest-first today: keep today's order in that mode and newest-first in the full mode, say which in the tab title).
- Enter on a row of a related record opens that record (`open_record`); other rows do nothing.
- Technical mode adds event type and version as the History table does; a mode switch redraws without a read.

## Interfaces (open these; do not paste more than needed)
`ClientInterface.activity(record_id, *, revisions_only, related, before_seq, limit) -> ActivityPage`; the `record_activity_text` functions of T01; `RecordView` (`record_view.py` bindings, `TABS`, `_read_tab`, `show_tab`); the pattern of `widgets/thread_tab.py` (`show_record(record)`). New widgets: `widgets/activity_tab.py` (`ActivityTab`, `show_record`), `widgets/insights_tab.py` (`InsightsTab` stub: a `Static` "Insights", `show_record(record)` that remembers the record; B2 fills it).

## Context (<= 8 files)
`widgets/record_view.py`; `widgets/thread_tab.py`; `record_text.py` (history functions stay, used by Revisions only); `keymap.py`; `tests/test_keymap.py`; `tests/test_record_view.py`; `tests/test_plain_walk.py`; `packages/tl-tui/README.md` (record view row).
may explore: `tests/helpers.py`.

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`, `activity_tab.py` (create), `insights_tab.py` (create, stub), `keymap.py` (rows for `4`, `h`, `v`, `r`, `/` on the tab and `9` on the record view)
- `packages/tl-tui/tests/test_activity_tab.py` (create), `test_record_view.py`, `test_keymap.py`, `test_plain_walk.py` (consequential pins: History becomes Activity; listed), the command-palette snapshot (L-P1-I8-13)
- `packages/tl-tui/README.md` (record view row and the keys), `docs/reports/P2-INS/T02.md`
Not allowed: `client.py`, `embedded.py`, `remote.py`, `schema/**`, `record_text.py`, other screens.

## Acceptance
```
just check
just gate packages/tl-tui/tests
```
Expected: `just check` clean; the tui suite passes with the keymap test tying every new entry to a real binding and `OWN_KEYS` unchanged elsewhere.

## Tests to add
`test_activity_tab.py` on `FakeClient`: the tab shows the rows newest first; `v` gives the History cells exactly; `r` toggles related rows and the title; `/` filters; "Show older" appends the next page; a client error keeps the display; `9` selects the Insights pane and `4`/`h` the Activity pane; plain walk as a plain user and an admin finds no id, hash or type key (`find_technical`); `n` and `I` are not bound on the record view.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; list each consequential pin; output of the two commands (<= 5 lines each).

## Commit
`P2-INS-T02: <imperative summary>`; trailer lines as `SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if `/`, `r` or `v` collide with a binding the keymap test pins on the record view; the History tab is read by a test outside Allowed paths in a way a pin cannot cover; the tab needs a client method that does not exist.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
