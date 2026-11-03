# P2-WEB1-T12 — stock page

Status: staged (activation list in `M4-TWINS.md`)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, p2/i3 merged into p2/web1, the materials reads seam (r9), T17 (seed)
Branch: `p2/web1-t12-stock`

## Goal
`GET /web/p/{project}/stock` shows the stock on hand (lot, item, location, quantities) in the log standard with the terminal stock screen's columns, cells, panel and summary. One module, `tl_web/pages/stock.py`.

## Pins (this file wins; then `M4-TWINS.md`, then `TWINS.md`)
1. `LOG_NAME = "Stock"`, `columns = present.materials_text.STOCK_COLUMNS`, `drop_order = STOCK_DROP`. Row `StockRowView`, base quoted.
2. Query strings: `?lot=`, `?item=`, `?heat=`, `?location=` (text, 1 to 200 chars, else absent) and `?subtree=1` (only with `location`), passed to `list_materials_stock(project, lot=, location=, item=, heat=, subtree=, limit=500)`.
3. `row_key = f"{row.lot}@{row.location}"`; `row_record = (that same text, row.item_title)` (unique per row; the lot key may hold `/`, the panel route takes it as it is).
4. Panel: `detail = get_materials_lot(project, row.lot)`; `mtr` = the filename of the `mtr` slot file of `get_materials_receipt(project, detail.receipt)` when `detail.receipt` is set, a 404 there means `None` (the only catch); `present.plain_lines(present.materials_text.lot_page(detail, row, self.labels, mtr=mtr, technical=self.technical))`.
5. Summary: `present.materials_text.stock_summary(len(rows), len(rows), item=, location=, heat=, lot=, subtree=)` from the filters (read its signature).

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`, `M4-TWINS.md`
- `packages/tl-web/src/tl_web/pages/wbs.py`, `packages/tl-web/tests/test_web_wbs_log.py` (models)
- `packages/tl-tui/src/tl_tui/materials_text.py` (stock half), `packages/tl-tui/src/tl_tui/widgets/stock_screen.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-tui/tests/fakes_materials_seed.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/stock.py` (replace the stub)
- `packages/tl-web/tests/test_web_stock_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T12 rows`)
- `docs/reports/P2-WEB1/T12.md` (create)

## Tests to add
`test_web_stock_log.py`: cases (a)-(h) and (j) of TWINS.md for slug `stock` over the seed. Case (i): technical wording applies (the lot panel has technical rows when `technical`); if `lot_page` shows none, only REFUSAL, say so. Then: each filter keeps the matching rows; `?subtree=1` without `location` is ignored; a lot with no heat; the panel of a lot whose receipt read is 404 shows no MTR; the panel number with `/` in the lot. Screenshot `T12-stock.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of the PNG. Commit subject `P2-WEB1-T12: ...`. Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead`, the text module needs a Textual import, or a view lacks a field the pin names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
