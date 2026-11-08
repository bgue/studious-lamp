# P2-INS-T02b — Activity tab replaces History in the record view; key 9 Insights (INS-A3, part 2)

Status: ready after T01 and T02 merged (round 3 dispatches it)
Tier: haiku
review: full
Labels: tui, tests, docs
Depends on: T02 merged (`ActivityTab`, `InsightsTab`), T01 merged (the real text)
Branch: `p2/ins-t02b-activity-wiring`
Worktree: `/home/user/wt/ins-t02b`

## Goal
`widgets/record_view.py` (this ticket owns it; T03 never edits it, plan check F9) shows the Activity tab where History was (key `4`, `h` as today) and the Insights tab as a new pane (key `9`), both through `show_record` like the Thread tab. The old `#rv-history` table goes (Revisions only lives in `ActivityTab`); the keymap, README and the pins that named History follow. ADR-0025's "TUI History display" folds in; Trace stays.

## Brief references (pasted; spec A0, A1.4)
- Record tab keys: `1` Details, `2` Properties, `3` Links, `4` Activity, `5` Trace, `6` Files, `T` Thread, `9` Insights; `7` and `8` are reserved by other specs; never `n` or `I` (global app keys). `h` opens the Activity tab as it opened History.
- `TABS["history"]` becomes `TABS["activity"] = "tab-activity"` and `TABS["insights"] = "tab-insights"`; `action_history` stays as the `h` action name (the keymap row text changes). `_read_tab` gets `TABS["activity"]: "#activity-tab"` and `TABS["insights"]: "#insights-tab"` in its tab map (lazy: shown first time, again on `reload`, as the other tabs).
- `reload()` no longer reads `reads.history` for a table; keep `self._events` only if another line of the view still uses it (check `grep -n "_events"`), else remove it with `_draw_history`. `history_cells` and `history_columns` stay exported from `record_view` (other code imports them, `__all__`).
- The tab title `History` becomes `Activity`; the Insights pane title `Insights`. KEY_HINTS: `1-6 tabs  T thread  9 insights`.
- Keymap rows (context `Record view`, owner `RecordView` or `ActivityTab`; add `"ActivityTab": ActivityTab` to `OWNERS` in `test_keymap.py`): `h` "Show the Activity tab"; `1 2 3 4 5` text "Details, Psets, Links, Activity, Trace tab"; `9` "Insights tab" (owner RecordView, binding `9`); ActivityTab rows `v` "Activity tab: revisions only on or off", `r` "Activity tab: related records on or off", `/` "Activity tab: filter the rows" (binding `slash`), `o` "Activity tab: show older rows". `CONTEXTS` stays unchanged.

## Interfaces (open these)
`widgets/record_view.py` (`TABS`, `BINDINGS`, `compose`, `_read_tab`, `reload`, `_draw_history`, `action_history`, `show_tab`); `widgets/activity_tab.py` and `insights_tab.py` as merged by T02 (`ActivityTab(client, scope, *, actor, id)`, `InsightsTab(id=...)`, both `show_record(record)`); `widgets/thread_tab.py` use in `compose` (pattern: `ThreadTab(self.client, self.scope, actor=self._actor(), id="thread-tab")`).

## Context (<= 8 files)
`widgets/record_view.py`; `keymap.py` lines 170-210; `tests/test_keymap.py`; `tests/test_record_view.py`, `test_record_plain.py`, `test_record_files_tab.py` (the History assertions: `rv-history`, `tab-history`, `"History"`); `packages/tl-tui/README.md` (record view row).
may explore: `tests/test_plain_walk.py`, `tests/helpers.py`.

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`, `keymap.py`
- `packages/tl-tui/tests/test_record_view.py`, `test_record_plain.py`, `test_record_files_tab.py`, `test_keymap.py` (the files that name `rv-history` or `tab-history` today; consequential pins: History becomes Activity; list each in the report, with a counterpart that pins `h` and Revisions only still showing today's History cells)
- `packages/tl-tui/tests/test_record_activity_wiring.py` (create)
- `packages/tl-tui/README.md` (record view row and the keys), `docs/reports/P2-INS/T02b.md`
Not allowed: `client.py`, `embedded.py`, `fakes.py`, `schema/**`, `record_text.py`, `activity_tab.py`, `insights_tab.py`, other screens. Run `grep -rn "rv-history\|tab-history\|TABS\[.history.\]" packages/tl-tui` first: a hit outside Allowed paths that a pin cannot cover is *Blocked*.

## Acceptance
```
just check
just gate packages/tl-tui/tests
```
Expected: `just check` clean; the tui suite passes with the keymap test tying every new entry to a real binding.

## Tests to add (`test_record_activity_wiring.py`)
`4` and `h` select `tab-activity`; `9` selects `tab-insights`; the Activity table has rows for a record with history (FakeClient) and `v` then shows exactly today's History cells; the Insights pane receives the record (`InsightsTab.record["key"]`); `n` and `I` are not bound on `RecordView` (`_binding_keys`); a plain walk as a plain user and as an admin finds nothing from `find_technical` on the Activity pane.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; list each consequential pin; output of the two commands (<= 5 lines each).

## Commit
`P2-INS-T02b: <imperative summary>`; trailer lines as `SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if `v`, `r`, `/` or `o` collide with a binding the keymap test pins on the record view; the History tab is read by a test outside Allowed paths that a pin cannot cover; `9` is already bound.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Orchestrator addendum (2026-11-08)
Also fix two T01 review nits in `packages/tl-tui/src/tl_tui/record_activity_text.py` (allowed path for these lines only):
- an own `Record.Updated` with no changes must not read `changed: ` — show the label alone; add a test;
- `TECHNICAL_COLUMNS` reuses `record_text.history_columns(True)` plus `From` instead of a hand-typed copy.
