# P2-I3-T06a — `materials_text.py`: shared helpers, stock log, lot panel, movement log

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T04b (merged)
Branch: `p2/i3-t06a-materials-text`

## Goal
The first screen text module (D25): everything the stock log, the lot panel and the movement log show, as pure functions with no Textual, no client call, no clock and no I/O.
The screens that mount it are T06f (later); the web twins import it. T06b-e import the shared helpers from here. `For` columns and reservation `For` are NOT built (D26; a later ticket adds them after S5).

## Brief references (pasted)
> Contract for every text module: `docs/tickets/P2-I3/text-contracts.md` (read it whole; 67 lines) and skill `tui-layout` rules as stated there. Allowed imports: `tl_mod_materials.views` (models only), `tl_tui.layout`, `tl_tui.display`, `tl_tui.text`.
> Stock: `STOCK_COLUMNS = (Lot, Subject, Location, On hand, Reserved, Available, UOM)`; Lot is the heat, else the lot key; Subject is `item_title`; UOM dropped when constant; `RIGHT = {On hand, Reserved, Available}`; no State column. Keys `/ l i h z`.
> `lot_page(detail, row)`: identity `heat · item_title` (heat, else the lot key); second line `Lot <key> · receipt <number>`; summary `<location title> · N on hand · N reserved · N available` for the selected row; sections
> Quantities (table Location, On hand, Reserved, Available), Reservations (table MTO line, Location, Qty; note `No reservations`), Movements (table Date, Kind, Qty, From, To, By; last 10), Traceability (Receipt, PO line, Heat, MTR; the screen passes `mtr: str | None`).
> Movement log: `MOVEMENT_COLUMNS = (Date, Kind, Lot, Item, Qty, From, To, By)`; Date `recorded_at[:10]`; Kind word (`issue` Issue, `transfer` Transfer, `return` Return, `adjust` Adjust, `scrap` Scrap, `receipt` Receipt, `reserve` Reserve, `unreserve` Release; any other value humanized);
> Qty signed by `direction` (`in` `+`, `out` `-`, else unsigned). Keys `k` kind, `p` period. Read only.
> Shared: `qty_text(Decimal) -> str` (trailing zeros dropped, at most 3 decimals, integer part grouped by a plain space, `0` for zero), `mtr_mark(state)` (`present` ✓, `missing` —, `n/a` n/a), `day(iso)` (first 10 chars, `—` for None), `who(labels, actor)`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views: StockRowView(lot, heat_no, item_code, item_title, location, location_title, on_hand, reserved, available, uom)
#   LotDetailView(id, key, heat_no, item_code, item_title, uom, issued_net, receipt, receipt_line, po_line, quantities, reservations, movements)
#   ReservationView(mto_line, location, qty)  MovementView(seq, recorded_at, kind, lot, heat_no, item_code, qty, uom, direction, from_location, to_location, mto_line_id, cost_code_id, person, reason, actor)
# tl_tui.layout: Page(identity, state, sections, summary) Section(heading, items, note) Prop(label, value) TableRow(columns, cells) Cell(text, style) plain_lines(page, *, identity=True, width=None) EMPTY
# tl_tui.display: Labels (dataclass of mappings)
```
Create `packages/tl-tui/src/tl_tui/materials_text.py` with exactly these public names (the web twins and T06b-g call them; names are the contract):
```python
EMPTY: str   # re-export of layout.EMPTY ("—")
RIGHT: frozenset[str]
STOCK_COLUMNS, STOCK_DROP, MOVEMENT_COLUMNS, MOVEMENT_DROP: tuple[str, ...]        # DROP least needed first: stock (UOM, Location); movement (By, Item, To, From)
KIND_WORDS: Mapping[str, str];  PERIODS = ("all", "7 days", "30 days", "this month")
def qty_text(value: Decimal) -> str;  def mtr_mark(state: str | None) -> str;  def day(iso: str | None) -> str;  def who(labels: Labels | None, actor: str | None) -> str   # who: cut a leading `user:`/`agent:`; None -> EMPTY
def next_kind(current: str | None, kinds: Sequence[str]) -> str | None            # None (all) -> kinds[0] -> ... -> None
def next_period(current: str) -> str;  def period_range(period: str, today: str) -> tuple[str | None, str | None]   # `today` is YYYY-MM-DD; 7/30 days back inclusive; month = first of the month; "all" -> (None, None)
def stock_columns_for(rows: Sequence[StockRowView]) -> tuple[str, ...]            # STOCK_COLUMNS minus UOM when constant (and Location when constant)
def stock_cells(view: StockRowView, columns: Sequence[str], labels: Labels | None = None, *, technical: bool = False) -> tuple[str, ...]
def stock_summary(shown: int, total: int, *, item: str | None = None, location: str | None = None, heat: str | None = None, lot: str | None = None, subtree: bool = False) -> str
STOCK_KEYS: str                                                                    # "/ filter  l lot  i item  h heat  z subtree  F5 reload  Esc close"-style, one line at 170
def lot_page(detail: LotDetailView, row: StockRowView | None = None, labels: Labels | None = None, *, mtr: str | None = None, technical: bool = False) -> Page
def lot_lines(detail, row=None, labels=None, *, mtr=None, technical=False, width: int | None = None) -> list[str]     # plain_lines(page, width=width)
def movement_columns_for(rows: Sequence[MovementView]) -> tuple[str, ...]         # drops By/To/From/Item when constant, never Date, Kind, Lot, Qty
def movement_cells(view: MovementView, columns: Sequence[str], labels: Labels | None = None, *, technical: bool = False) -> tuple[str, ...]
def movement_summary(shown: int, total: int, *, kind: str | None = None, period: str = "all", lot: str | None = None) -> str
MOVEMENT_KEYS: str
```
`technical=True` adds the `seq` to the movement Date cell's row (as `#<seq>` after the date) and the lot `id` as a Traceability property `Id`. Qty in cells and tables is `qty_text`; a movement's Qty is `+12`/`-3`. A `None` value is `EMPTY`, never `None` or `-`.
Summary texts: `Showing N of M stock rows · item X · location Y` (filters named only when set); `Showing N of M movements · Issue · last 30 days`.

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`
- `packages/tl-tui/src/tl_tui/tag_text.py` (shape of a text module: `row_cells`, `summary_line`, `next_class`), `packages/tl-tui/src/tl_tui/layout.py` (lines 99-146 models, 498-530 `plain_lines`)
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (models, lines 60-160)
may explore: `packages/tl-tui/src/tl_tui/schedule_text.py` (a larger module), `packages/tl-tui/src/tl_tui/text.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/materials_text.py` (create)
- `dev/accept/P2-I3/T06a.py` (create), `docs/reports/P2-I3/T06a.md` (create)
Not here: `layout.py` (the DROP/SHORTENABLE names stay in the module), screens, `app.py`, `client.py`, any test file, `views.py`.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06a.py
```
`T06a.py` (you write it, exit 0, one `PASS <check>` per line): build the views from `views.stock/lot_detail/movements` over a copy of `.accept/p2-i3.db` (project `P123`, lot `P123-RCPT-0001@1`, MTR `mtr` = `"mtr.pdf"`); for widths 80 and 170 print `lot_lines(..., width=w)` and the first three stock and movement rows
as joined cells and assert: no `None` and no standalone `-` value; `—` for an empty cell; every table line is within the width; `stock_columns_for` drops UOM when constant and keeps it for two UOMs (build one `StockRowView` by hand); the Reservations section shows `No reservations` for a lot with none;
`qty_text(Decimal("1234567.5000"))` is `1 234 567.5`, `qty_text(Decimal("0.000"))` is `0`, `qty_text(Decimal("0.12345"))` has at most 3 decimals; `period_range("30 days", "2026-11-02")` is `("2026-10-04", "2026-11-02")`; `next_kind` cycles and returns None after the last; a Receipt movement with `direction="in"` shows `+`;
`import tl_tui.materials_text` leaves `textual` out of `sys.modules` (run it in a fresh subprocess: `python -c 'import tl_tui.materials_text, sys; print("textual" in sys.modules)'` prints `False`).

## Tests to add
None (T11: `packages/tl-tui/tests/test_materials_text.py`).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines. Commit subjects `P2-I3-T06a: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a name above conflicts with `layout.py`, if a contract line cannot be met without importing `textual` or a widget, or if a table cannot stay within 80 columns with `layout`'s own column dropping.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
