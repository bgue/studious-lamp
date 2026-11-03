# P2-I3-T06g — the For column and signed receive quantities (materials_text)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06a (merged), T06f (merged: the two screens that read these columns), S5 (merged), D35
Branch: `p2/i3-t06g-for-columns`

## Goal
Add the `For` column to the movement log and to the lot panel's Reservations table, and sign a receive quantity by kind when the ledger gives no direction (D35), all in `materials_text.py`. `StockScreen` and `MovementLogScreen` follow because they read `MOVEMENT_COLUMNS`, `movement_columns_for` and `movement_cells`.
No new screen. New screenshots of the two screens show the result.

## Brief references (pasted)
> `docs/tickets/P2-I3/text-contracts.md`, "Movement log" and "Stock" bullets. `MOVEMENT_COLUMNS = (Date, Kind, Lot, Item, Qty, For, From, To, By)`. **For** is `MovementView.work_package`, else `cost_code`, else `—` (`mto_line` is not shown). `For` is dropped last: `MOVEMENT_DROP = ("By", "Item", "To", "From", "For")`.
> `movement_columns_for(rows)` also drops `For` when every row has the same `work_package or cost_code` (including all empty).
> Qty sign (`_signed_qty`): `direction` `in` gives `+`, `out` gives `-` (as now); when `direction` is None the sign follows the ledger kind as `tl mat movements` does: `receive` and `return` `+`; `issue` and `scrap` `-`; every other kind (`transfer`, `adjust`, `reserve`, `unreserve`) unsigned. A zero stays `0`.
> Lot panel Reservations table: `LOT_RESERVATION_COLUMNS = ("MTO line", "For", "Location", "Qty")`, For = `ReservationView.work_package` (`—` when None). The lot panel's Movements table (`LOT_MOVEMENT_COLUMNS`) is unchanged: no For there.
> Movement panel (`widgets/movement_screen.py`): `PANEL_COLUMNS` gains `"For"` after `"Qty"` so the property lines show it.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_tui/materials_text.py (edit in place; no signature changes)
MOVEMENT_COLUMNS: tuple[str, ...] = ("Date", "Kind", "Lot", "Item", "Qty", "From", "To", "By")
MOVEMENT_DROP: tuple[str, ...] = ("By", "Item", "To", "From")
LOT_RESERVATION_COLUMNS: tuple[str, ...] = ("MTO line", "Location", "Qty")
def movement_columns_for(rows) ; def _movement_cell(view, column, labels, technical) ; def _signed_qty(view) ; def lot_page(...)  # Reservations section builds TableRow(LOT_RESERVATION_COLUMNS, (mto_line, location title, qty))
# tl_mod_materials.views.MovementView: kind direction("in"|"out"|None) work_package cost_code (str|None) ...   ReservationView: mto_line location qty work_package(str|None)
# widgets/movement_screen.py: PANEL_COLUMNS: tuple[str, ...] = ("Date", "Kind", "Lot", "Item", "Qty", "From", "To", "By")
```

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md` (Stock and Movement log bullets), `packages/tl-tui/src/tl_tui/materials_text.py` lines 38-72 and 231-404
- `packages/tl-tui/src/tl_tui/widgets/movement_screen.py` lines 30-115
- `dev/accept/P2-I3/T06f.py` (whole: seed copy, `EmbeddedClient`, `TlApp` host, helpers; copy them)
may explore: `layout.py` (table fitting), `widgets/stock_screen.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/materials_text.py` (edit), `packages/tl-tui/src/tl_tui/widgets/movement_screen.py` (edit: `PANEL_COLUMNS` only)
- `dev/accept/P2-I3/T06g.py` (create), `docs/reports/P2-I3/T06g.md` (create)
- `dev/accept/P2-I3/T06a.py`, `dev/accept/P2-I3/T06f.py`: only an assertion that breaks because a column or sign now differs (consequential pin; list each in the report)
Not here: `stock_screen.py`, `layout.py`, `app.py`, any test file. If a table at 80 columns cannot fit with `For` without a `layout.py` change, say so in the report; do not edit `layout.py`.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06g.py
```
`T06g.py` (you write it; exit 0; one `PASS <check>` per line): (1) over hand-built `MovementView`s: `receive` with direction None gives `+N`, `return` `+N`, `issue` `-N`, `scrap` `-N`, `transfer` and `reserve` unsigned, `direction="out"` with kind `issue` still `-N`, zero stays `0`; `For` shows the work package, else the cost code, else `—`; `movement_columns_for` drops `For` when all are the same; `MOVEMENT_DROP` ends with `For`.
A hand-built lot detail with a reservation whose `work_package` is set shows it in the Reservations table at widths 80 and 170 (every line within the width); with None shows `—`; no `None` and no standalone `-` anywhere.
(2) screens over a temp copy of the seed ledger: push `StockScreen(client, "P123")` and `MovementLogScreen(client, "P123")` on `TlApp` at (80, 30) and (170, 40); the movement log shows a `+` quantity for a receipt row and the header `For` at 170 (the seed has a reservation or issue against a work package; if none, hand the screen a fake with one);
`down` on a stock row shows the panel Reservations with `For`; save `app.export_screenshot(title="Stock")` to `.accept/shots/T06g-stock-<w>.svg` and `title="Movements"` to `.accept/shots/T06g-movements-<w>.svg`.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the screenshot paths. Commit subjects `P2-I3-T06g: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if a name listed under Interfaces is missing, or if a provided check of T06f.py fails because of this change in a way that needs a `stock_screen.py` edit.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
