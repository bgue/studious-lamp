# P2-I1-T05a — CWP text: Textual-free awp_text module and the Details renderer

Status: ready (T03b, T10c merged; Interfaces from the tree at p2/i1 8b1aeec)
Tier: haiku
Review: full
Labels: tui
Depends on: T03b, T10c (both merged)
Branch: `p2/i1-t05a-cwp-text`
Worktree: `/home/user/wt/i1/t05a` (from `p2/i1` head)

## Goal
All the text of the CWP register (spec §8, skill `tui-layout`) in `tl_tui/awp_text.py`, a module that imports no `textual` (D27, the split of `correspondence_text.py`):
the web client's CWP page imports it (`tl_web/present.py`, P2-WEB1). The Details tab and the panel share one renderer, `tl_tui/details/awp.py` (registered for `awp.CWP`),
built on `awp_text.cwp_rows`. The screen itself is T05d (after this); T05b and T05c build on `hours_text`, `date_text` and the column names here.

## Contract of `tl_tui/awp_text.py` (fixed now: web tickets cite it; shared by T05b and T05c)
```python
# pure functions over tl_mod_awp.views models and tl_api.routes.awp.CwpDetailView; no client calls, no textual, no I/O
HOURS_UNIT = "h"
def hours_text(value: Decimal | None) -> str         # None -> "—"; 4200 -> "4 200"; 12.5 -> "12.5" (space groups, no trailing .0)
def date_text(value: str | None) -> str              # None -> "—"; YYYY-MM-DD as is
CWP_COLUMNS = ("Number","Subject","State","Discipline","CWA","Planned start","Budget h","Allocated")
CWP_DROP = ("Planned start","Discipline")            # dropped first at narrow width (layout.DROP_FIRST names the order; add the two names there if absent)
CWP_RIGHT = ("Budget h",)
def cwp_cells(row: CwpRow, labels: Labels | None = None) -> tuple[str, ...]    # 8 cells; Allocated "✓" or "—"; State humanized; Discipline label from the code list
def cwp_summary(d: CwpDetailView) -> str             # "Piping · CWA 12 · 2026-11-03 to 2027-01-29 · 4 200 h" (join_facts; absent facts skipped)
def cwp_page(d: CwpDetailView, labels: Labels | None = None, *, technical: bool = False, panel: bool = False) -> Page
    # identity_line(number, title); state_line(state); summary only when panel; sections in order: Scope (Budget hours, Contractor, table Commodity/Qty/UOM),
    # Allocation (table WBS node/%/Hours: wbs_code, percent, hours = budget*percent/100 half-even to 0.01; no title column, the view has none; note "Not allocated"), References (table Package/Type/Status/Forecast/Constraint source; note "No packages linked"),
    # Schedule (table Activity/Name/Start/Finish from `ActivityLink`: Activity = resolution.activity_id, Name/Start/Finish = resolution.activity.name/early_start[:10]/early_finish[:10], "—" when the activity is None; the Activity cell gets a "!" suffix when link.status == "stale" or resolution.state is not current/as_of; note "No activities linked"), Timeline (Date/Who/Event/Note, oldest first),
    # section "Files and links" with Prop Files = d.file_count and Prop Links = d.link_count. Panel: Schedule cut to 4 rows by `layout.limited` inside `cwp_page` (`rows_page` already cuts Timeline to 4). Technical: id, key (technical mode only).
def cwp_rows(d: CwpDetailView, labels: Labels | None = None) -> list[DetailRow]   # the sections above as DetailRow (table_rows for tables); cwp_page = rows_page(cwp_rows(..), identity=, state=, summary=, technical=, panel=) then the Schedule cut. The Details renderer returns cwp_rows.
def group_by_cwa(rows: Sequence[CwpRow]) -> list[tuple[str, tuple[CwpRow, ...]]]   # key `c`: CWA code ("—" last), rows keep number order
```
Screen keys (T05d): `/` filter, `d` discipline, `s` state, `c` by CWA; they are the client's `list_cwps(state=, discipline=, cwa=)` arguments.

## Interfaces (in the tree; verbatim names)
```python
# tl_tui.layout: Page(identity,state,sections,summary), Section(heading,items,note), Prop, TableRow(columns,cells), Cell(text,style), prop(label,value),
#  identity_line(number,title), state_line(state,since=None), join_facts(*facts), limited(items,limit), more_note(n), state_style(text), plain_lines(page,identity=True,width=None)
# tl_tui.details: DetailRow(label,value,technical,section,panel,columns,cells), register("awp.CWP"), rows_page(rows,identity=,state=,summary=,technical=,panel=), table_rows(section,columns,rows)
#  renderer signature (client, project, record: dict, labels) -> list[DetailRow]; record["key"] is the CWP number; imports of tl_tui.details/layout/display are textual-free (checked)
# tl_tui.display: Labels, code_label(labels, list_name, code), humanize(name)
# tl_tui.widgets.log_screen: LogScreen[Row] hooks log_project columns load_rows row_key row_cells row_record panel_text(-> render(page)) drop_order shrink_columns keep_columns
#  actions_for(row) summary_text open_row; class vars LOG_NAME KEY_HINTS KEY_CELLS HELP_KEYS BINDINGS; pattern widgets/tag_register.py (ctor (client, project), open_row = open_record(self, client, f"project:{project}", project, actor, row.id))
# client (T03b): list_cwps(project, *, state=, discipline=, cwa=) -> list[CwpRow]; get_cwp(project, number) -> CwpDetailView (CwpDetail + link_count, file_count, timeline: list[TimelineRow(date,who,event,note)])
# tl_mod_awp.views: CwpRow(id number title state discipline cwa planned_start planned_finish budget_hours allocated); CwpDetail adds contractor_text quantities(Any: list of {commodity,qty,uom}) allocations[CwpAllocation(wbs_code,percent)] packages[PackageRow] activities[ActivityLink]
#  PackageRow(id kind package_no status_text forecast_date actual_date constraint_source source_system title cwps)
# tl_mod_schedule.resolver.ActivityLink(link_id,status,pin,reason,ref_key,resolution: Resolution(state,schedule_code,activity_id,snapshot_id,snapshot_number,data_date,activity: ActivityRow|None))
# tests: packages/tl-tui/tests/fakes_awp.py seed_awp(client) (3 CWPs, CWAs A1 A2, WBS 1 1.1 1.2 depths 0/1/1); helpers.py run_pilot, settle, panel_of
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/correspondence_text.py` lines 1-216 (pattern), `details/__init__.py` lines 1-160 (`rows_page`, `table_rows`), `details/schedule.py` (a renderer)
- `packages/tl-tui/src/tl_tui/layout.py` lines 44-80 and 98-240; `packages/tl-tui/tests/fakes_awp.py` (`seed_awp`)
may explore: `display.py` (Labels, code_label, humanize)

## Allowed paths
- `packages/tl-tui/src/tl_tui/awp_text.py` (create), `packages/tl-tui/src/tl_tui/details/awp.py` (create)
- `packages/tl-tui/src/tl_tui/layout.py` (only the `DROP_FIRST` and `SHORTENABLE` names the screens need)
- `dev/accept/P2-I1/T05a.py` (create), `docs/reports/P2-I1/T05a.md` (create)
Screen, nav entry and palette entry: T05d and supervisor glue.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05a.py                        # no pytest
```
`T05a.py`: `PASS no textual` (a subprocess imports `tl_tui.awp_text` and `tl_tui.details.awp` with `sys.modules["textual"] = None`); `PASS cells` (8 cells, `✓`/`—`, hours_text 4200 -> "4 200", 12.50 -> "12.5", None -> "—");
`PASS group_by_cwa` (CWA order, "—" last); `PASS page` prints `cwp_page` as plain lines at width 80 and 170 for the `seed_awp` CWP (detail built with `CwpDetailView(**cwp.model_dump(), link_count=0, file_count=0, timeline=[])`),
every section heading present, one blank line between sections, panel=True has a summary line and at most 4 Schedule rows; `PASS details` (`details_for(FakeClient, "P123", {"type": "awp.CWP", "key": <number>}, Labels(), mode)` returns rows
in the same sections). Ends `T05a ok`.

## Tests to add
none (T11: `packages/tl-tui/tests/test_cwp_register.py`, 80 and 170 columns, plain walk entry).

## Report requirements
`docs/reports/P2-I1/T05a.md` <= 60 lines; deviations first; tui-layout checklist answered line by line (7 lines). Subject `P2-I1-T05a: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a fact on the screen needs a field no view carries (write which); never compute it by extra client calls per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
