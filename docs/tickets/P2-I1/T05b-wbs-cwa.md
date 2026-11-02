# P2-I1-T05b — WBS tree and CWA register: Textual-free text modules and screens

Status: draft (r8: split by area to pass the Haiku size check, then ready when T05a is merged)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a
Branch: `p2/i1-t05b-wbs-cwa`
Worktree: `/home/user/wt/i1/t05b` (from `p2/i1` head)

## Goal
Two `LogScreen`s (spec §8 "WBS tree", "CWA register") with their text in `tl_tui/wbs_text.py` and `tl_tui/cwa_text.py`, neither importing `textual` (D27); the web reuses them.
`hours_text`, `date_text`, `join_facts` come from `awp_text` (T05a). Cost code names are not in any view yet: the Cost codes table has Code, Hours, % only (D26; the Name column joins when a view carries it).

## Contract (fixed now; pure functions)
```python
# tl_tui/wbs_text.py   (WbsRow from tl_mod_awp.views; depth 0 is the top node)
WBS_COLUMNS = ("Number","Subject","Budget h","Cost codes"); WBS_RIGHT = ("Budget h",)
def wbs_cells(row: WbsRow, rows: Sequence[WbsRow]) -> tuple[str, ...]   # Subject indented 2 spaces per depth; Budget h = hours_text(total_hours); Cost codes "3 · 100%" on a leaf with by_cost_code, "—" on a parent or empty leaf
def is_leaf(row: WbsRow, rows: Sequence[WbsRow]) -> bool                # no other row has parent_code == row.code
def depth_limited(rows, n: int) -> list[WbsRow]                         # keys 1-8 (client-side cut of an already loaded tree; the client's depth= is for the API)
def unallocated_leaves(rows) -> list[WbsRow]                            # key u: leaves with no cost code
def wbs_summary(row, rows) -> str                                       # "Parent 1.2 · 4 CWPs · 4 200 h" / "Leaf · 2 CWPs · 600 h" (cwp_count, T10c)
def wbs_page(row: WbsRow, rows: Sequence[WbsRow], *, panel: bool = False, technical: bool = False) -> Page
    # identity "1.2.3 · Rack 12 piping"; state line "Leaf · active" / "Parent of 4 · active" ("Retired" for retired); sections Cost codes (table Code/Hours/%; % = hours/total_hours, whole number), CWPs (table Number/Subject/%/Hours from row.cwps; note "No CWPs allocated"), Timeline is omitted until a view carries it (note in report)
# tl_tui/cwa_text.py
CWA_COLUMNS = ("Number","Subject","Position","CWPs","Budget h"); CWA_RIGHT = ("Position","CWPs","Budget h")
@dataclass(frozen=True) class CwaLine: row: CwaRow; position: int | None; cwps: tuple[CwpRow, ...]; steps: int   # steps = len(path.steps), 0 without a path
def cwa_lines(cwas: Sequence[CwaRow], path: PathView | None, cwps: Sequence[CwpRow]) -> list[CwaLine]   # position from path.steps (cwa code), cwps with row.cwa == code; ordered by position, absent last, then code
def visible_lines(lines, show_retired: bool) -> list[CwaLine]           # key r
def cwa_cells(line: CwaLine) -> tuple[str, ...]; def cwa_summary(line) -> str   # "Position 3 of 12 · 4 CWPs · 11 300 h"
def cwa_page(line: CwaLine, *, panel: bool = False, technical: bool = False) -> Page   # sections Location, CWPs (table Number/Subject/State/Budget h), Files and Links omitted until a view carries counts (note)
```
The CWA screen loads `list_cwas`, `get_path`, `list_cwps` (three client calls, no per-row call). The WBS screen loads `wbs_tree` once and `get_wbs_node` for the panel.

## Context, Allowed paths, Acceptance
- Context: `awp_text.py` (T05a, merged), `widgets/tag_register.py` (the screen pattern), `correspondence_text.py` (pattern), `layout.py` lines 98-146, `tests/fakes_awp.py`.
- Allowed: `tl_tui/wbs_text.py`, `tl_tui/cwa_text.py`, `widgets/wbs_screen.py`, `widgets/cwa_register.py` (create); `dev/accept/P2-I1/T05b.py`, `docs/reports/P2-I1/T05b.md` (create). Nav entries are supervisor glue.
- Acceptance: setup, `just check`, `uv run python dev/accept/P2-I1/T05b.py` (PASS no textual for both modules; cells and pages on the seed fake; indent; key `u`; mount at 80 and 170 columns; ends `T05b ok`). No pytest.
- Tests to add: none (T11 `test_wbs_screen.py`, `test_cwa_register.py`). Report <= 60 lines, deviations first, tui-layout checklist. Subject `P2-I1-T05b: ...`; trailer as T05a.
- Escalation: a needed fact absent from every view -> *Blocked*, never an extra call per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
