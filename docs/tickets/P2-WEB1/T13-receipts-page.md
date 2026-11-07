# P2-WEB1-T13 — receipts page

Status: ready (r9; the seam, p2/i3 and the Open-link hook are in the tree)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, T17 merged (the seed); in the tree: p2/i3, the ten materials mirrors, the page stub, `WebLog.row_open_key`
Branch: `p2/web1-t13-receipts`

## Goal
`GET /web/p/{project}/receipts` shows the receipts log (number, subject, state, received, location, lines, MTR) with the terminal receipt log's columns, cells, panel and summary; the panel is the receipt page (lines, delivery, inspection, files). One module, `tl_web/pages/receipts.py`.

## Pins (this file wins; then `M4-TWINS.md`, then `TWINS.md`)
1. `LOG_NAME = "Receipts"`, `columns = RECEIPT_COLUMNS`, `drop_order = RECEIPT_DROP`. Row `ReceiptView`. `row_key = row.number`, `row_record = (row.number, row.title)`, `row_cells = present.receipt_text.row_cells(row, RECEIPT_COLUMNS, self.labels, technical=self.technical)`.
2. Query strings `?open=1` (not Accepted, Rejected or Void) and `?mtr=missing`, passed as `open_only`, `missing_mtr` to `list_materials_receipts(project, open_only=, missing_mtr=, limit=500)`.
3. Panel: `detail = get_materials_receipt(project, row.number)`; `present.plain_lines(present.receipt_text.receipt_page(detail, self.labels, technical=self.technical))` . A 404 is the one 404 page.
4. Summary `present.receipt_text.summary_line(len(rows), total, open_only=, missing_mtr=, text="")`.
5. The line `MTR required to accept` (when `mtr_required` and no MTR) is in the panel through the module; do not add it.
6. Open link (D41): this row has no record page, so override `row_open_key(self, row) -> None` (the page then shows no Open link and every row's `data-open` is empty). Case (h) is therefore: `doc.buttons() == []`, no `a#log-open`, and no `data-open` value on any row.

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`, `M4-TWINS.md`
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/receipt_text.py`, `packages/tl-tui/src/tl_tui/widgets/receipt_log.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-tui/tests/fakes_materials_seed.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/receipts.py` (replace the stub)
- `packages/tl-web/tests/test_web_receipt_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T13 rows`)
- `docs/reports/P2-WEB1/T13.md` (create)

## Tests to add
`test_web_receipt_log.py`: cases (a)-(h) and (j) of TWINS.md for slug `receipts` over the seed. Case (i): applies if `receipt_page` shows technical rows, else REFUSAL only. Then: `?open=1` drops the Accepted receipt; `?mtr=missing` keeps the receipt without MTR and its panel has the MTR line; a rejected receipt's panel has the rejection reason; `?open=zzz` is ignored. Screenshot `T13-receipts.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of the PNG. Commit subject `P2-WEB1-T13: ...`. Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead`, the text module needs a Textual import, or a view lacks a field the pin names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
