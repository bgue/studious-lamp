# P2-INS-T02 — Activity tab widget and the Insights pane stub (INS-A3, part 1)

Status: ready (round 2, against merged S1 @2fbcdcf; T02b wires it into the record view)
Tier: haiku
review: full
Labels: tui, tests
Depends on: S1 merged (yes). Runs in one workflow with T01: `record_activity_text.py` is a committed stub with frozen signatures (T01 replaces its bodies); import it, never edit it, and write no test that pins its wording
Branch: `p2/ins-t02-activity-tab`
Worktree: `/home/user/wt/ins-t02`

## Goal
`widgets/activity_tab.py` (`ActivityTab`) shows `ClientInterface.activity(...)` as a table, standing alone (a test host app like `test_thread_tab.py`'s `Host`); `widgets/insights_tab.py` is a stub pane (`InsightsTab`) that T03 fills. Nothing here touches `record_view.py` or `keymap.py` (T02b). Split from the first draft by the Haiku checklist (one diff over 400 lines).

## Brief references (pasted; spec A1.4)
- `ActivityTab(client, scope, *, actor="user:dev", id=None)`, a `Vertical` with `can_focus=True` like `ThreadTab`; `show_record(record: dict)` stores the record, resets state and calls `reload()`; `reload()` reads the first page (limit 120) with a plain call (the pattern of `ThreadTab.reload`: `except CLIENT_ERRORS` posts `StatusMessage(describe_error(exc), "error")` and keeps the display; `NotImplementedError` leaves the tab empty); `refresh_for_display_mode()` redraws from the rows held, with no read.
- Bindings on the tab (all `show=False`): `v` Revisions only on or off, `r` related on or off (default on), `slash` focus the filter `Input` (id `activity-filter`; pattern `log_screen.py` `action_filter`, `on_input_changed`), `o` Show older (next page by `next_before_seq`, appended below), `enter` on a related row posts `OpenRecord(self.scope, row.from_key, follow=True)`; on any other row nothing. Toggling `v` or `r` reloads from the first page.
- Full mode: newest first; columns and cells from `activity_columns(rows, technical=...)` and `activity_cells(row, labels, technical=..., with_why=page_has_why(rows))` (`technical = mode_of(self.app).technical`; labels as `ThreadTab`: `load_labels(self.client, self.scope, ())` on mount). Revisions only: `client.activity(id, revisions_only=True, related=False)`; the table is exactly `history_columns(technical)` and `history_cells(row.event, labels, technical=technical)` of today's History, oldest first (`reversed(rows)`).
- Filter: rows kept by `row_matches(row, text, labels)` in full mode (Revisions only ignores the filter). A header `Static` (id `activity-title`) shows `filter_title(revisions_only, related, text)` plus ` · newest first` or ` · oldest first`; a hint `Static` (id `activity-hint`) `v revisions only · r related · / filter` plus `  o older` when `next_before_seq` is set. Empty page: `Nothing recorded yet.`
- `InsightsTab(Vertical)`: stub; `compose` yields `Static("Insights", id="insights-body", markup=False)`; `show_record(record)` stores `self.record`; nothing else (T03 fills it).
- Plain by default: `display.find_technical` finds nothing in any cell; no id, hash or event type key shown (the cells functions guarantee it).

## Interfaces (verbatim at @2fbcdcf)
```python
# tl_tui/client.py (ClientInterface; FakeClient in tests/fakes.py has the same, building rows from its history, newest first, no related rows)
def activity(self, record_id: str, *, revisions_only: bool = False, related: bool = True,
             before_seq: int | None = None, limit: int = 120) -> ActivityPage: ...
# tl_core.insights.types: ActivityPage(rows: list[ActivityRow], next_before_seq: int | None)
# ActivityRow(event: Event, kind, related=False, from_id=None, from_key=None, why=None, decided_by=None, note=None)
# tl_tui/record_activity_text.py (committed stub; T01 owns the bodies; signatures frozen)
def activity_columns(rows: list[ActivityRow], *, technical: bool) -> tuple[str, ...]
def activity_cells(row: ActivityRow, labels: Labels, *, technical: bool, with_why: bool) -> tuple[str, ...]
def page_has_why(rows: list[ActivityRow]) -> bool
def filter_title(revisions_only: bool, related: bool, text: str) -> str
def row_matches(row: ActivityRow, text: str, labels: Labels) -> bool
```

## Context (<= 6 files)
`widgets/thread_tab.py` (the pattern); `widgets/log_screen.py` lines 240-260 and 530-600 (filter input); `record_activity_text.py`; `tests/test_thread_tab.py` (the Host pattern); `tests/fakes.py` (`FakeClient.activity`, `_events`, `calls`); `messages.py`.
may explore: `tests/helpers.py` (`run_pilot`, `screen_text`).

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/activity_tab.py` (create), `insights_tab.py` (create)
- `packages/tl-tui/tests/test_activity_tab.py` (create)
- `docs/reports/P2-INS/T02.md` (create)
Not allowed: `record_view.py`, `keymap.py`, `record_activity_text.py`, `client.py`, `fakes.py`, `record_text.py`, any other test.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_activity_tab.py
```
Expected: `just check` clean; the new test file passes alone.

## Tests to add (`test_activity_tab.py`, Host app with `FakeClient`; assertions never pin T01's wording: compare with the text functions' own output)
Table row count equals the page and rows are newest first (by seq, read from the fake's events); `v` gives exactly `history_columns`/`history_cells` oldest first and the call used `revisions_only=True`; `r` toggles `related` in the client call (read `calls` and the last kwargs by wrapping `activity` in the test) and the title; `/` then text taken from one row's own cell reduces the rows (and an unmatched text gives none); `o` appends the older page when a small `limit` makes a cursor (monkeypatch `PAGE` size via a module constant `PAGE_SIZE = 120` that the test lowers); a client error posts a status line and keeps the rows; Enter on a related row (build one `ActivityRow(related=True, from_key="X-1")` by wrapping `activity`) posts `OpenRecord` with `follow=True`, Enter on a non-related row posts nothing; `refresh_for_display_mode` makes no client call; `find_technical` finds nothing in the cells of every row shown in plain mode.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; output of the two commands (<= 5 lines each).

## Commit
`P2-INS-T02: <imperative summary>`; trailer lines as `docs/build-spec/SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if a frozen signature cannot give a table with as many cells as columns; `ThreadTab`'s pattern does not fit; a test would need `fakes.py` changed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
