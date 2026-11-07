# P2-I1-T05b — WBS tree: Textual-free text module and screen

Status: ready (T05a merged at 1c6aed5; r8 split off the CWA register, now T05e)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a (merged)
Branch: `p2/i1-t05b-wbs`
Worktree: `/home/user/wt/i1/t05b` (from `p2/i1` head)

## Goal
A `LogScreen` (spec §8 "WBS tree", skill `tui-layout`) with its text in `tl_tui/wbs_text.py`, which does not import `textual` (D27); the web reuses it.
`hours_text`, `date_text` and the page helpers come from `awp_text` (T05a, merged). Cost code names are in no view: the Cost codes table has Code, Hours, % only (D26).
No actions bar entries in I1 (writes come with P2-I2): `actions_for` returns `[]`.

## Contract (fixed now; pure functions; WbsRow from tl_mod_awp.views, depth 0 is the top node)
```python
# tl_tui/wbs_text.py
WBS_COLUMNS = ("Number","Subject","Budget h","Cost codes"); WBS_RIGHT = ("Budget h",)
def wbs_cells(row: WbsRow, rows: Sequence[WbsRow]) -> tuple[str, ...]   # Subject indented 2 spaces per depth; Budget h = hours_text(total_hours); Cost codes "3 · 100%" on a leaf with by_cost_code, "—" on a parent or an empty leaf
def is_leaf(row: WbsRow, rows: Sequence[WbsRow]) -> bool                # no other row has parent_code == row.code
def depth_limited(rows, n: int) -> list[WbsRow]                         # keys 1-8: client-side cut of an already loaded tree (the client's depth= is for the API)
def unallocated_leaves(rows) -> list[WbsRow]                            # key u: leaves with no cost code
def wbs_summary(row, rows) -> str                                       # "Parent 1.2 · 4 CWPs · 4 200 h" / "Leaf · 2 CWPs · 600 h" (cwp_count, T10c)
def wbs_page(row: WbsRow, rows: Sequence[WbsRow], *, panel: bool = False, technical: bool = False) -> Page
    # identity "1.2.3 · Rack 12 piping"; state line "Leaf · active" / "Parent of 4 · active" ("Retired" when retired);
    # sections Cost codes (table Code/Hours/%; % = hours / total_hours, whole number), CWPs (table Number/Subject/%/Hours from row.cwps; note "No CWPs allocated"); no Timeline (no view carries it: say so in the report)
```
The screen loads `wbs_tree` once (client `wbs_tree(project)`) and `get_wbs_node(project, code)` for the panel. Keys: `1`..`8` depth cut, `0` all, `u` unallocated leaves only, `F5` reload. `KEY_HINTS`/`KEY_CELLS`/`HELP_KEYS` name `/ filter  1-8 depth  0 all  u unallocated  F5 reload  Esc back`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` (names; `hours_text`, `date_text`, `join_facts`-style helpers), `widgets/tag_register.py` (all; the screen pattern), `correspondence_text.py` (the text-module pattern)
- `packages/tl-tui/src/tl_tui/layout.py` lines 98-146 (`Page`, `Section`, tables), `widgets/log_screen.py` lines 96-225, `tests/fakes_awp.py` (`seed_awp`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/wbs_text.py`, `packages/tl-tui/src/tl_tui/widgets/wbs_screen.py` (create); `dev/accept/P2-I1/T05b.py`, `docs/reports/P2-I1/T05b.md` (create).
- Do NOT edit `layout.py`, `awp_text.py` or the nav files (supervisor glue). If a column needs `DROP_FIRST` or `SHORTENABLE`, write the name under *Open questions*.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05b.py                        # no pytest
```
`T05b.py` (screen on `FakeClient` + `seed_awp` through the Textual pilot, as `tests/helpers.py`): `PASS no textual` (import `wbs_text` with `sys.modules["textual"] = None`); `PASS cells` (indent per depth, leaf vs parent Cost codes); `PASS page` (sections in order, one blank line apart, `—` in fixed sections); `PASS depth` and `PASS unallocated` (row counts change); `PASS mount 80` and `PASS mount 170` (no line wider than the terminal; Subject not right of the third column; at 170 the panel shows heading, state and summary); `PASS missing` (an error from `get_wbs_node` shows a status, not a traceback). Ends `T05b ok`.

## Tests to add
none (T11: `packages/tl-tui/tests/test_wbs_screen.py`).

## Report requirements
`docs/reports/P2-I1/T05b.md` <= 60 lines; deviations first; tui-layout checklist answered line by line. Subject `P2-I1-T05b: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a fact on the screen needs a field no view carries (write which); never add a call per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
