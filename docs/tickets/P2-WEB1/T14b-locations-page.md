# P2-WEB1-T14b — locations page

Status: staged (activation list in `M4-TWINS.md`)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, p2/i3 merged into p2/web1, the materials reads seam (r9), T17 (seed)
Branch: `p2/web1-t14b-locations`

## Goal
`GET /web/p/{project}/locations` shows the storage locations as a tree (Subject indented by depth) with the terminal location screen's columns, cells, panel and summary; the panel shows the stock held there and the children. One module, `tl_web/pages/locations.py`.

## Pins (this file wins; then `M4-TWINS.md`, then `TWINS.md`)
1. `LOG_NAME = "Locations"`, `columns = LOCATION_COLUMNS`, `drop_order = LOCATION_DROP`. Row `LocationView`. `row_key = row.code`, `row_record = (row.code, row.title)`. Rows in the order the read gives (the tree order).
2. `load_rows`: `list_materials_locations(project, limit=500)`, kept in `self._all`. No query string.
3. Panel: `stock = list_materials_stock(project, location=row.code, limit=500)`; `present.plain_lines(present.location_text.location_page(row, self._all, stock, self.labels, technical=self.technical))` . A 404 is the one 404 page.
4. Summary `present.location_text.summary_line(len(rows), len(self._all), text="")`.
5. HTML collapses the two leading spaces per depth that `location_cells` puts in Subject (T10 saw the same for the WBS): the text is right, the page shows no indent. Do not work around it; note it in the report (a CSS rule is a separate decision).

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`, `M4-TWINS.md`
- `packages/tl-web/src/tl_web/pages/wbs.py`, `packages/tl-web/tests/test_web_wbs_log.py` (models)
- `packages/tl-tui/src/tl_tui/location_text.py`, `packages/tl-tui/src/tl_tui/widgets/location_screen.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-tui/tests/fakes_materials_seed.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/locations.py` (replace the stub)
- `packages/tl-web/tests/test_web_location_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T14b rows`)
- `docs/reports/P2-WEB1/T14b.md` (create)

## Tests to add
`test_web_location_log.py`: cases (a)-(h) and (j) of TWINS.md for slug `locations` over the seed. Case (i): applies if `location_page` shows technical rows, else REFUSAL only. Then: the child location's cells carry the indent (compare to the module); the panel of the root lists its children, the panel of a leaf with stock lists the contents (Lot, Item, On hand); a leaf with none shows the empty note. Screenshot `T14b-locations.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of the PNG. Commit subject `P2-WEB1-T14b: ...`. Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead`, the text module needs a Textual import, or a view lacks a field the pin names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
