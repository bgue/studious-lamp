# P2-I3-T06f — StockScreen and MovementLogScreen (the stock and movement screens)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06a (merged), T04b (merged)
Branch: `p2/i3-t06f-stock-screens`

## Goal
Two read-only log screens mounting `materials_text` (T06a): the stock by lot and location with the lot panel, and the movement log. Unregistered (no nav, no `app.py`); the owner sees them in
the acceptance screenshots. The `For` column and signed receive quantities are NOT here (T06g changes `materials_text` later; these screens read `columns_for` and `*_cells` so they follow).

## Brief references (pasted)
> Screen rules: `docs/tickets/P2-I3/text-contracts.md`, sections "Screens" and "Per screen" (Stock, Movement log). Layout skill rules are already in `materials_text`.
> StockScreen keys: `/` filter box (client side), `l` show only the highlighted row's lot (again: all), `i` its item, `h` its heat, `z` subtree of the location (only when `location` was given). `l i h` are
> server filters of `list_materials_stock`; the summary counts `len(self.shown)` of `len(self.rows)`. Panel: `get_materials_lot(project, row.lot)`, and `mtr` = the filename of the file in slot `mtr` of
> `get_materials_receipt(project, detail.receipt)` (`views.MTR_SLOT`), else None (any `CLIENT_ERRORS` on that second call gives None, not an error line).
> MovementLogScreen keys: `k` next kind (`next_kind(kind, kinds)` with `kinds` = the kinds present in the rows read, unfiltered), `p` next period (`next_period`; `period_range(period, today)` to `since`/`until` of `list_materials_movements`).
> The movement log has no panel detail call: `panel_text` shows the highlighted movement as property lines (Date, Kind, Lot, Item, Qty, From, To, By, Reason, Person) built from the row, `render(Page)`, identity `#<seq> · <Kind word>`.

## Interfaces (verbatim from repo at the branch point)
```python
# widgets/tag_register.py is the shape; widgets/log_screen.py hooks: log_project, columns, load_rows, row_key, row_cells, row_record, panel_text, keep_columns, drop_order, shrink_columns, actions_for, summary_text, open_row
# tl_tui.materials_text: STOCK_COLUMNS STOCK_DROP STOCK_KEYS MOVEMENT_COLUMNS MOVEMENT_DROP MOVEMENT_KEYS PERIODS KIND_WORDS
#   stock_columns_for(rows) stock_cells(view, columns, labels=None, *, technical=False) stock_summary(shown, total, *, item=None, location=None, heat=None, lot=None, subtree=False)
#   lot_page(detail, row=None, labels=None, *, mtr=None, technical=False) -> Page
#   movement_columns_for(rows) movement_cells(view, columns, labels=None, *, technical=False) movement_summary(shown, total, *, kind=None, period="all", lot=None)
#   next_kind(current, kinds) next_period(current) period_range(period, today) -> (since | None, until | None)
# ClientInterface: list_materials_stock(project, *, lot, location, item, heat, subtree=False, limit=1000) get_materials_lot(project, key) get_materials_receipt(project, number)
#   list_materials_movements(project, *, lot, since, until, kind, limit=1000)
```
Create `StockScreen(client: ClientInterface, project: str, *, location: str | None = None)` in `widgets/stock_screen.py` and `MovementLogScreen(client, project, *, lot: str | None = None)` in `widgets/movement_screen.py`.
`LOG_NAME` "Stock" and "Movements"; `KEY_HINTS` = `STOCK_KEYS` / `MOVEMENT_KEYS`; `keep_columns` returns the first two columns (Lot, Subject / Date, Kind) since neither log has a State column; `drop_order` = `STOCK_DROP` / `MOVEMENT_DROP`.
`row_key` stock: `f"{row.lot}@{row.location}"`; movement: `str(row.seq)`. `row_record` stock: `(heat or lot, item_title)`; movement: `(f"#{seq}", kind word)`.
Limit: pass `limit=MAX_VIEW_ROWS` (`from tl_mod_materials.limits import MAX_VIEW_ROWS`, 1000; the routes refuse more; not `views.MAX_VIEW_ROWS`, which pyright treats as private).

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`, `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (whole; the shape), `packages/tl-tui/src/tl_tui/materials_text.py` (signatures only: `grep -n "^def \|^[A-Z_]* ="`)
- `dev/accept/P2-I3/T04b.py` lines 270-292 (copy of the seed ledger plus `EmbeddedClient(SqliteUowFactory(db), actor=ALICE)`; copy its imports) and `dev/accept/P2-W0/RM-S3.py` lines 381-405 (`run_test`, `settle`, `screen_text`, `TlApp(client, scope=..., actor=..., is_admin=...)`)
may explore: `widgets/log_screen.py` (the hooks above), `tests/helpers.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/stock_screen.py` (create), `packages/tl-tui/src/tl_tui/widgets/movement_screen.py` (create)
- `dev/accept/P2-I3/T06f.py` (create), `docs/reports/P2-I3/T06f.md` (create)
Not here: `materials_text.py`, `app.py`, `client.py`, `navigation.py`, `log_screen.py`, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06f.py
```
`T06f.py` (you write it; exit 0; one `PASS <check>` per line): over a temp copy of the seed ledger and `EmbeddedClient`, at sizes (80, 30) and (170, 40): push `StockScreen(client, "P123")` on `TlApp`, `settle`, assert it is the
top screen, `screen_text` has the keys row and a heat or lot number, press `l` and assert the summary names the lot, press `l` again and the lot filter is gone; press `down` and assert the panel text has `Quantities` and `Traceability`;
save `app.export_screenshot(title="Stock")` to `.accept/shots/T06f-stock-<w>.svg`. Same for `MovementLogScreen`: rows present, `k` changes the summary to a kind word, `p` to `last 7 days`, panel has `Qty`; screenshot `T06f-movements-<w>.svg`.
Also: a `FakeClient` (`tests/fakes.py` with `put_materials(project, stock=[])`) gives an empty `StockScreen`: panel `No stock on hand`-style text, no exception. No `None`, no standalone `-` in `screen_text`. Esc closes the screen.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the two screenshot paths. Commit subjects `P2-I3-T06f: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if a hook of `LogScreen` cannot express a key above, or if `materials_text` lacks a name listed here.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
