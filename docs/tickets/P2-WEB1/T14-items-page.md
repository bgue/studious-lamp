# P2-WEB1-T14 — items page

Status: staged (activation list in `M4-TWINS.md`)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, p2/i3 merged into p2/web1, the materials reads seam (r9), T17 (seed)
Branch: `p2/web1-t14-items`

## Goal
`GET /web/p/{project}/items` shows the company item library (number, subject, state, category, UOM, projects) with the terminal item library's columns, cells, panel and summary; the panel lists the projects that use the item. One module, `tl_web/pages/items.py`.

## Pins (this file wins; then `M4-TWINS.md`, then `TWINS.md`)
1. `LOG_NAME = "Item library"`, `columns = ITEM_COLUMNS`, `drop_order = ITEM_DROP`. Row `MaterialItemView`. `row_key = row.code`, `row_record = (row.code, row.title)`.
2. `load_rows`: `list_materials_items(project=self.project, limit=500)`, all kept in `self._all`; `?state=Active|Retired` narrows after the read as the screen does (`retired` flag); anything else absent.
3. Panel: `projects = list_materials_item_projects(row.code)`; `present.plain_lines(present.item_text.item_page(row, projects, self.labels, technical=self.technical))`. This read is company-wide: the mirror calls the JSON route, so the viewer filter is the route's; do not filter or add to it. No catch (the terminal's "projects could not be read" line is not twinned: a failed read is the error page).
4. Summary `present.item_text.summary_line(len(rows), len(self._all), state=, project=self.project, text="")`.

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`, `M4-TWINS.md`
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/item_text.py`, `packages/tl-tui/src/tl_tui/widgets/item_library.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-tui/tests/fakes_materials_seed.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/items.py` (replace the stub)
- `packages/tl-web/tests/test_web_item_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T14 rows`)
- `docs/reports/P2-WEB1/T14.md` (create)

## Tests to add
`test_web_item_log.py`: cases (a)-(h) and (j) of TWINS.md for slug `items` over the seed. Case (i): applies if `item_page` shows technical rows, else REFUSAL only. Then: `?state=Retired` keeps the retired item; the panel Projects table (`Project` = the project id); an item used in no project shows `Not used in any project`. Screenshot `T14-items.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of the PNG. Commit subject `P2-WEB1-T14: ...`. Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead`, the text module needs a Textual import, or a view lacks a field the pin names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
