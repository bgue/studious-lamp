# P2-WEB1-T10 — WBS tree page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T02, the awp reads seam (6cfcfb9), P2-I1 T05b (`wbs_text`, merged)
Branch: `p2/web1-t10-wbs`

## Goal
`GET /web/p/{project}/wbs` shows the WBS tree depth-first (Subject indented by depth, hours, cost-code cell) in the log standard, with the terminal's columns, cells, panel and summary. One module, `tl_web/pages/wbs.py` (stub exists). The path of construction is T16 (waits for its text module).

## Pins (this file wins; the common recipe is `docs/tickets/P2-WEB1/TWINS.md`)
1. `LOG_NAME = "WBS tree"`, `columns = present.wbs_text.WBS_COLUMNS` (no drop order). Row `WbsRow`, base `WebLog["WbsRow"]`.
2. `load_rows`: `tree = list(self.client.wbs_tree(self.project))`, kept in `self._tree`. Query strings (recipe 4): `?depth=N` (integer 1 to 8, else absent) and `?unallocated=1`. Rows: `present.wbs_text.unallocated_leaves(tree)` when asked (worked out on the whole tree), then `present.wbs_text.depth_limited(rows, n)` when `depth` is set. `row_key = row.id`; `row_record = (row.code, row.title)`; cells `present.wbs_text.wbs_cells(row, self._tree)`.
3. Summary as the terminal: `present.layout.join_facts(f"{len(rows)} of {len(tree)} nodes", f"depth {n}" if n else "", "unallocated leaves" if asked else "")`.
4. Panel: `full = self.client.get_wbs_node(self.project, row.code)`; `present.plain_lines(present.wbs_text.wbs_page(full, self._tree, panel=True, technical=self.technical))`. No fallback to the listing's row when the read fails (D33: hidden = missing, recipe 5); the codes contain dots, the mirror takes the code as it is.

## Interfaces (verbatim from the tree)
```python
# tl_tui/wbs_text.py (re-exported as present.wbs_text)
WBS_COLUMNS; def wbs_cells(row, rows) -> tuple[str, ...]; def depth_limited(rows, n) -> list[WbsRow]
def unallocated_leaves(rows) -> list[WbsRow]; def wbs_page(row, rows, *, panel=False, technical=False) -> Page
# WebReadClient.wbs_tree(project, *, depth=None) -> list[WbsRow]; .get_wbs_node(project, code) -> WbsRow
# WbsRow: id code title parent_code depth position retired total_hours by_cost_code cwp_count cwps
```

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/wbs_text.py`, `packages/tl-tui/tests/fakes_awp.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/wbs.py` (replace the stub)
- `packages/tl-web/tests/test_web_wbs_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T10 rows`)
- `docs/reports/P2-WEB1/T10.md` (create)

## Tests to add
`test_web_wbs_log.py`: cases (a)-(j) for slug `wbs` with the fake's 3 nodes (1, 1.1, 1.2); the panel route for `1.1` (a dotted code) works; `?depth=1` leaves one row and the status line says `depth 1`; `?unallocated=1` equals `unallocated_leaves`; `?depth=abc` and `?depth=99` are ignored. Case (i): the page has no technical-only row, so only the REFUSAL part applies. Screenshot `T10-wbs.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of `T10-wbs.png`.

## Escalation triggers
- *Blocked* if `wbs_text` needs a Textual import or a mirror raises `UnsupportedRead`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
