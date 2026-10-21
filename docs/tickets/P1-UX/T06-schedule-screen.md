# P1-UX-T06 — Schedule screen: Enter opens the record screen, plain text, schedule and snapshot Details

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3 (merged)
Branch: `p1/ux-t06-schedule-screen`

## Goal
In the schedule screen (F12) Enter on a schedule row or on a snapshot row opens the full record screen; Esc returns on the same row.
The Details tab of a schedule and of a snapshot show labelled fields (new `details/schedule.py`). Plain mode names a snapshot `Snapshot 2`
(technical: `MAIN#2`), writes `Current` not `current`, shows people by name, and hides the `tl xer worker` command and the file hash;
technical mode adds them. (The cost lists have no TUI screen, so nothing to do for cost; the compare and activity screens are not in this ticket.)

## Brief references (pasted)
> SCOPE clause 1: Enter on any row opens the full record view; Esc returns on the same row. Clause 2: plain words; no internal keys, ids, hashes, actor ids. Clause 3: technical mode shows what plain hides.
> D14: define `refresh_for_display_mode(self) -> None`. D22: a register opens records on `DataTable.RowSelected`, never a priority Enter binding (it steals Enter from the filter Input).
> S2 getter table: `get_schedule(project, code)`; a snapshot record's key is `CODE#N`: `get_schedule_snapshot(project, code, int(N))`. Record ids: `ScheduleView.id`, `SnapshotView.id`.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/record_screen.py (merged)
def open_record(screen: Screen[Any], client: ClientInterface, scope: str, project: str, actor: str, record_id: str) -> None
# tl_tui/details/__init__.py: DetailRow(label, value, technical=False); @register("schedule.Schedule", ...) renderer(client, project, record, labels) -> list[DetailRow]
# details/documents.py is the model; technical_rows(record) from details/generic.py; EMPTY, timestamp from tl_tui.text
# tl_tui/display.py: Labels, humanize, type_label, actor_label(labels, actor), mode_of(app).technical;  tl_tui/labels_load.py: load_labels(client, scope, record_types=...)
# client: get_schedule(project, code, *, limit=…, offset=0) -> ScheduleDetailView; get_schedule_snapshot(project, code, number) -> SnapshotView
# tl_tui/schedule_text.py (today)
def schedule_cells(view: ScheduleView) -> tuple[str, ...]   # (code, schedule_type raw, current number, data date, count, title)
def snapshot_cells(view: SnapshotView) -> tuple[str, ...]   # ("2*", "Published (current)", date, counts…, source_name)
def schedule_detail_lines(detail: ScheduleDetailView) -> list[str]   # "type {schedule_type}  |  owner {short(detail.owner)}  |  P6 project …"
def snapshot_detail_lines(view: SnapshotView) -> list[str]           # line 0 f"{view.key}  {view.state}{' (current)'…}  |  data date …  |  P6 …"; "requested by {short(view.requested_by)}"; waiting line "waiting for the worker (`tl xer worker`)"
# SnapshotView: id key number state is_current data_date previous_number p6_version p6_project activity_count relationship_count wbs_count calendar_count code_count udf_count error_count warning_count source_name source_size source_sha256 requested_by attempts last_error built_at published_at
# ScheduleView: id code title schedule_type owner p6_project current_snapshot_number current_data_date snapshot_count
# widgets/schedule_screen.py (today): tables "#sc-schedules" (row key = code) and "#sc-snapshots" (row key = number); self.shown (ScheduleView list), self.detail.snapshots;
#   current_schedule(), current_snapshot(), _describe(), _code(), _number(), _fill(keep, keep_snapshot); self.client, self.project, self.actor; compose/on_mount fill the tables.
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/schedule_screen.py`, `schedule_text.py` (lines 1-160 only), `details/documents.py`
- `packages/tl-tui/tests/test_schedule_text.py`, `test_schedule_screen.py`, `test_record_screen.py` (Enter/Esc pattern, lines 1-120)
- `packages/tl-tui/tests/fakes_schedule.py` (read-only: `seed_schedule` makes schedule `MAIN` id `SCHED-MAIN`, snapshots `SNAP-MAIN-1`, `SNAP-MAIN-2`, key `MAIN#2`)
- `packages/tl-tui/tests/fakes.py` (`FakeClient.add_stored_record(record_id, key, record_type, title)`: registers a record under a view's id so Enter finds it)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/schedule_screen.py`, `packages/tl-tui/src/tl_tui/schedule_text.py`
- `packages/tl-tui/src/tl_tui/details/schedule.py` (create)
- `packages/tl-tui/tests/test_schedule_text.py`, `test_schedule_screen.py`, `test_schedule_screen_pages.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_schedule_plain.py` (create)
- `docs/reports/P1-UX/T06.md` (create)

## Steps
1. `schedule_text` (only the functions below; the compare, activity and trend functions stay as they are, `compare_screen` and `activity_screen` import them):
   `schedule_cells(view)`: type via `humanize`. `snapshot_cells` unchanged. `schedule_detail_lines(detail, labels=None, *, technical=False)`: type `humanize`, owner via `actor_label`.
   `snapshot_detail_lines(view, labels=None, *, technical=False)`: line 0 starts `Snapshot {view.number}` (technical: `{view.key}`), requested by via `actor_label`, the waiting line reads
   `waiting to be processed` (technical: the old text with `tl xer worker`). Labels `None` means `Labels()`.
2. Screen: `on_mount` sets `self.labels = load_labels(self.client, f"project:{self.project}", ("schedule.Schedule", "schedule.ScheduleSnapshot"))`; `_describe()` reads
   `technical = mode_of(self.app).technical` and passes it and `self.labels`.
3. Add `on_data_table_row_selected(self, event)`: `event.stop()`; table `sc-schedules`: `self.shown[event.cursor_row].id`; table `sc-snapshots`: `self.detail.snapshots[event.cursor_row].id` (guard index and `self.detail is None`);
   `open_record(self, self.client, f"project:{self.project}", self.project, self.actor, record_id)`.
4. Add `refresh_for_display_mode(self) -> None`: `self._describe()` (the tables do not depend on the mode).
5. `details/schedule.py`: `@register("schedule.Schedule")` reads `client.get_schedule(project, str(record["key"]), limit=1)`; rows Type (`type_label`), Code, Title, Kind (`humanize`), Owner (`actor_label`, only if set),
   `P6 project` (only if set), `Current snapshot` (number or EMPTY), `Data date`, Snapshots (count), Created, Updated, then `technical_rows(record)`.
   `@register("schedule.ScheduleSnapshot")`: `code, _, number = str(record["key"]).rpartition("#")`, reads `client.get_schedule_snapshot(project, code, int(number))`; rows Type, Snapshot (`2 of MAIN`), State, Current (`Yes`/`No`),
   `Data date`, `Compares with` (`snapshot N`, only if set), `P6 version`, Activities, Relationships, WBS, Calendars, Codes, `User fields`, Errors, Warnings, File (`source_name`), `Requested by` (`actor_label`), Published (`date_only(published_at)`, only if set),
   `Last error` (only if set), technical-only rows `Attempts`, `File hash` (`source_sha256`), then `technical_rows(record)`. A key without `#` raises ValueError: the registry shows the generic rows with a note (do not catch it).
6. Update pinned expectations: type `current` -> `Current` in the row, `MAIN#2  Published (current)` -> `Snapshot 2  Published (current)`, `requested by user:dev` -> `requested by dev`, the waiting line; keep one technical assertion for the key and the command.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_schedule_text.py packages/tl-tui/tests/test_schedule_screen.py packages/tl-tui/tests/test_schedule_screen_pages.py packages/tl-tui/tests/test_schedule_plain.py packages/tl-tui/tests/test_activity_screen.py packages/tl-tui/tests/test_compare_screen.py packages/tl-tui/tests/test_embedded_schedule.py packages/tl-tui/tests/test_details_registry.py packages/tl-tui/tests/test_record_screen.py
```
Gate paths: all exist at dispatch except `test_schedule_plain.py` (new, this ticket creates it). Expected `gate: PASS`. No snapshot test shows this screen. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_schedule_plain.py` (TlApp on `FakeClient`, `seed_schedule("P123")`; open with `f12` as `test_schedule_screen.py` does; for Enter: `client.add_stored_record("SCHED-MAIN", "MAIN", "schedule.Schedule", "MAIN schedule")` and `("SNAP-MAIN-2", "MAIN#2", "schedule.ScheduleSnapshot", "MAIN#2")`):
- `test_enter_on_a_schedule_row_opens_the_record_and_escape_returns_to_the_same_row`.
- `test_enter_on_a_snapshot_row_opens_the_snapshot_record`.
- `test_a_row_the_viewer_cannot_read_opens_as_no_record` (no stored record; no id in the text).
- `test_plain_text_names_the_snapshot_and_hides_the_command_and_the_actor_id` (`Snapshot 2`, none of `MAIN#2`, `user:dev`, `tl xer worker`; `find_technical(text, labels) == []`).
- `test_technical_mode_restores_the_key_and_the_command_and_back` (flag on, `refresh_for_display_mode()`, then off).
- `test_the_schedule_and_snapshot_renderers_give_labelled_rows` (`details_for` with the stored record dicts; `File hash` and `Attempts` only in technical).

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- `add_stored_record` does not make the record screen open (the fix would be in `fakes.py`): stop.
- The fake `get_schedule` rejects `limit=1`: report; do not change the fake.
- Plain text still shows an id, hash, `CODE#N` or `svc:`/`user:`: list it; fix only inside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
