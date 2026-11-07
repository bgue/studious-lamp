# P2-WEB1-T19 — Two visual fixes seen in the wave-1 screenshots

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web, css
Depends on: T12, T13 (merged).
Branch: `p2/web1-t19-panel-polish`   (from p2/web1)

## Goal
1. **Stock page hides the location.** At 1280-1599 CSS px (panel beside the list) `tl.css` line 40 hides every
   `.tl-drop` column, and `StockWebLog.drop_order()` returns the terminal's `STOCK_DROP` = ("UOM", "Location").
   Two lots of the same heat in different bays then show as identical rows (screenshot `T12-stock.png`, rows
   `H4471` 12.5 and `H4471` 3). On the web, only UOM may drop: `StockWebLog.drop_order()` returns `("UOM",)`
   (a web-only choice; do not change `materials_text.STOCK_DROP`, the terminal keeps its own).
2. **Panel tables wrap.** `.tl-panel-text` is `white-space: pre-wrap; overflow-wrap: anywhere`, so a panel table
   wider than the panel breaks mid-row (receipts panel *Lines*: `Heat Condition` drops to a second line). Panel
   text is terminal text already laid out in columns: make it `white-space: pre; overflow-x: auto;` (keep the
   monospace font, drop `overflow-wrap`), so a wide table scrolls inside the panel and every row stays on one line.

## Allowed paths
- `packages/tl-web/src/tl_web/pages/stock.py`
- `packages/tl-web/src/tl_web/static/tl.css`
- `packages/tl-web/tests/test_web_stock_log.py` (add one test: the Location header cell has no `tl-drop` class,
  the UOM one has it)
- `packages/tl-web/tests/*` only where a pinned CSS or column-class string changes because of the two edits
- `docs/reports/P2-WEB1/T19.md` (create)

## Steps
1. Edit `drop_order` and the CSS rule as above. Nothing else.
2. Re-take the two screenshots with the existing screenshot tests (`-k screenshot` in `test_web_stock_log.py`
   and `test_web_receipt_log.py`); they write to `/home/user/wt/p2-web1/.accept/shots/`. Look at both PNGs (Read
   the file) and say in the report what each now shows: the Location column on stock; the receipts Lines table on
   one line per row.

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-web/tests | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
