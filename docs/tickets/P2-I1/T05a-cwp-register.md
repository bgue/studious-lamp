# P2-I1-T05a — CWP register: Textual-free text module, shared renderer, screen

Status: draft (ready when T03b and T10c are merged; r7 fills `Interfaces` from the tree)
Tier: haiku
Review: full
Labels: tui
Depends on: T03b, T10c
Branch: `p2/i1-t05a-cwp-register`
Worktree: `/home/user/wt/i1/t05a` (from `p2/i1` head)

## Goal
The CWP register (spec §8, skill `tui-layout`) as a `LogScreen`, and all of its text in `tl_tui/awp_text.py`, a module that imports no `textual`
(decision D27, the same split as `correspondence_text.py`): the web client's CWP page renders the same columns, summary line and sections by importing it
(`tl_web/present.py`, P2-WEB1). The Details tab and the panel share one renderer, `tl_tui/details/awp.py` (registered for `awp.CWP`), built on `awp_text.cwp_page`.

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
    # Allocation (table WBS node/Title?/%/Hours: wbs_code, percent, hours = budget*percent/100), References (table Package/Type/Status/Forecast/Constraint source; note "No packages linked"),
    # Schedule (table Activity/Name/Start/Finish; a stale or orphaned link marks the Activity cell "!"; note "No activities linked"), Timeline (Date/Who/Event/Note, oldest first),
    # Files (n) and Links (n) as one-line counts. Panel: first lines of Schedule and Timeline with more_note. Technical: id, key (technical mode only).
def group_by_cwa(rows: Sequence[CwpRow]) -> list[tuple[str, tuple[CwpRow, ...]]]   # key `c`: CWA code ("—" last), rows keep number order
```
Keys row: `/` filter, `d` discipline, `s` state, `c` by CWA; filters are the client's `list_cwps(state=, discipline=, cwa=)` arguments.
Actions bar shows only offered actions: none in I1 (writes come with the actions bar of P2-I2); do not add buttons.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/correspondence_text.py` (pattern, all), `packages/tl-tui/src/tl_tui/widgets/correspondence_screen.py` (LogScreen subclass pattern), `layout.py` lines 98-146 and 498-530
- `packages/tl-tui/src/tl_tui/details/schedule.py` and `details/__init__.py` lines 1-60 (`@register`, `rows_page`)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` model classes only; `packages/tl-tui/tests/fakes_awp.py` (`seed_awp`)
may explore: `display.py` (Labels, code_label, humanize)

## Allowed paths
- `packages/tl-tui/src/tl_tui/awp_text.py` (create), `packages/tl-tui/src/tl_tui/details/awp.py` (create), `packages/tl-tui/src/tl_tui/widgets/cwp_register.py` (create)
- `packages/tl-tui/src/tl_tui/layout.py` (only the `DROP_FIRST` and `SHORTENABLE` names the screens need)
- `dev/accept/P2-I1/T05a.py` (create), `docs/reports/P2-I1/T05a.md` (create)
Nav entry ("Work packaging" > "CWPs") and palette entry are supervisor glue (`nav_tree.py`, `app.py`).

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05a.py                        # no pytest
```
`T05a.py`: `PASS no textual` (a subprocess imports `tl_tui.awp_text` with `sys.modules["textual"] = None`); `PASS cells` (8 cells, `✓`/`—`); `PASS page` prints
`cwp_page` as plain lines at width 80 and 170 for the `seed_awp` CWP, every section heading present and one blank line between sections; `PASS mount 80` and `PASS mount 170`
(the screen on `FakeClient` through the Textual pilot as `tests/helpers.py` does; no line wider than the terminal; Subject is not right of the third column). Ends `T05a ok`.

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
