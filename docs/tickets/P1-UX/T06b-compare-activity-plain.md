# P1-UX-T06b — Compare and activity screens, look-ahead and orphan lines: plain words

Status: ready (stage)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, T06 (merged)
Branch: `p1/ux-t06b-compare-activity-plain`

## Goal
The compare screen, the activity screen and the look-ahead and orphaned-links panels of the schedule screen name a snapshot `Snapshot 2` (never `MAIN#2`), show P6 status words instead of codes, and show no record or link ids in plain mode;
technical mode keeps today's text. All redraw on `refresh_for_display_mode` (D14). These screens list activities and comparison rows, which are not records: no Enter.

## Brief references (pasted)
> SCOPE clause 2: plain words; no internal keys, ids, hashes. Clause 3: technical shows what plain hides. D29: a snapshot's plain name is `Snapshot N`, technical `CODE#N`. D14: `refresh_for_display_mode(self) -> None`. D27: pure functions keep raw output by default (`technical=True`); widgets pass the mode.
> P6 activity ids such as `A1010` and activity names are the user's own words: they stay in both modes.

## Interfaces (verbatim from repo)
```python
# tl_tui/schedule_text.py (today; T06 already added snapshot_detail_lines(view, labels=None, *, technical=False))
def compare_header_lines(c: Comparison) -> list[str]   # f"{c.new.key} ({date}) against {c.old.key} ({date})", "data date +Nd | latest finish ..."; Comparison.old/new are Header(key, number, data_date)
def compare_section_lines(c: Comparison, name: str, limit=...) -> list[str]   # progress rows: f"{r.old_status} to {r.new_status}" (raw P6 codes); other rows use activity ids/names
def activity_cells(a: ActivityRow) -> tuple[str, ...]   # (activity_id, a.status raw, start, finish, float, %, "critical"/"", name)
def page_line(page: ActivityPage, *, critical: bool, text: str) -> str    # f"{page.snapshot_key}  data date ..." ; ActivityPage has snapshot_key and offset/total/rows
def activity_detail_lines(detail: ActivityDetail) -> list[str]   # f"{id}  {name}  |  {detail.snapshot_key}", f"{a.task_type}  {a.status}  {pct}% ({percent_type})  |  WBS ..."; ActivityDetail has snapshot_key
def trend_lines(points) -> list[str]                    # f"  #{p.snapshot_number}  {date}  {p.state}  float ..."
def look_ahead_lines(answer: LookAhead) -> list[str]    # f"look-ahead {answer.snapshot_key}: ..." ; rows f"  {r.activity_id}  {r.phase}  ..."
def orphan_lines(links) -> list[str]                    # f"  {o.activity_id}  last seen in snapshot N  record {o.from_id}  link {o.link_id}"
# widgets/compare_screen.py: CompareScreen(client, project, code, new, old=None): _show() calls compare_header_lines(c), compare_tabs(c), compare_section_lines(c, name)
# widgets/activity_screen.py: ActivityScreen(client, project, code, number=None): _fill() title f"Activities of {page.snapshot_key}", page_line(...), activity_cells(a); _describe() activity_detail_lines(detail), trend_lines(trend)
# widgets/schedule_screen.py (T06 merged): _describe() builds lines with look_ahead_lines(answer) and orphan_lines(links); it reads technical = mode_of(self.app).technical
# tl_tui/display.py: humanize, mode_of(app).technical
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/schedule_text.py` (lines 100-135 and 186-363), `widgets/compare_screen.py`, `widgets/activity_screen.py`
- `packages/tl-tui/src/tl_tui/widgets/schedule_screen.py` (lines 195-225 only: the two calls)
- `packages/tl-tui/tests/test_schedule_text.py`, `test_compare_screen.py`, `test_activity_screen.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/schedule_text.py`, `widgets/compare_screen.py`, `widgets/activity_screen.py`, `widgets/schedule_screen.py` (only the two calls and the mode)
- `packages/tl-tui/tests/test_schedule_text.py`, `test_compare_screen.py`, `test_activity_screen.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_schedule_more_plain.py` (create)
- `docs/reports/P1-UX/T06b.md` (create)

## Steps
1. `schedule_text`: add `snapshot_name(key: str, *, technical: bool) -> str`: technical returns `key`; plain returns `Snapshot {n}` for `CODE#n` (`rpartition("#")`), else `key`. Add `status_words(code: str | None) -> str`: `humanize` of the code after dropping a leading `TK_`, `TT_`, `PCT_`, `CS_` prefix (`TK_Active` -> `Active`, `TT_Task` -> `Task`); `-` for none.
2. Add `technical: bool = True` (keyword, last) to `compare_header_lines`, `compare_section_lines` (progress rows use `status_words` in plain), `activity_cells` (status), `page_line`, `activity_detail_lines` (snapshot name, status, task type), `look_ahead_lines`, `orphan_lines`
   (plain drops `  record {from_id}  link {link_id}` and says `last seen in snapshot N`). `trend_lines` is unchanged. Plain forms use `snapshot_name(..., technical=False)`.
3. Screens read `technical = mode_of(self.app).technical` and pass it to every call above (the activity title `Activities of {snapshot_name}`); `schedule_screen._describe` passes it to the two calls. Add `refresh_for_display_mode(self)` to `CompareScreen` and `ActivityScreen` (redraw from the held data; for the activity screen `_fill()` and `_describe()`).
4. Update pinned expectations that now read plain through the widgets; keep one technical assertion per text function.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_schedule_text.py packages/tl-tui/tests/test_compare_screen.py packages/tl-tui/tests/test_activity_screen.py packages/tl-tui/tests/test_schedule_more_plain.py packages/tl-tui/tests/test_schedule_screen.py packages/tl-tui/tests/test_schedule_screen_pages.py packages/tl-tui/tests/test_schedule_plain.py packages/tl-tui/tests/test_embedded_schedule.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_schedule_more_plain.py` (new, this ticket creates it). Expected `gate: PASS`. No snapshot test shows these screens. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_schedule_more_plain.py` (`seed_schedule("P123")`; open the screens as `test_compare_screen.py` / `test_activity_screen.py` do):
- `test_snapshot_name_plain_and_technical`, `test_status_words`.
- `test_compare_screen_plain_names_snapshots_and_has_no_technical_tokens` (`find_technical(text) == []`, no `MAIN#`, activity ids still shown).
- `test_activity_screen_plain_title_status_and_detail` (title `Activities of Snapshot 2`; no `TK_`; technical shows both).
- `test_look_ahead_and_orphan_lines_plain_hide_ids` (no `record ...  link ...`; technical keeps them).
- `test_both_screens_redraw_on_the_mode_switch`.

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- `ActivityPage` or `ActivityDetail` has no `snapshot_key` the way the fake builds it: stop and report.
- The fake rejects the plain forms of a call (a fake is read-only here): stop and report.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
