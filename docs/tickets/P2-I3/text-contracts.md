# P2-I3 screen text contracts (T06a-e, and the web twins T12-T14 of P2-WEB1)

Decision D25 (r5). Each screen keeps everything it shows in a Textual-free module `packages/tl-tui/src/tl_tui/<x>_text.py`
(precedent: `tag_text.py`, `schedule_text.py`, M3 D27). The screen widget only mounts, moves selection and calls these
functions. `tl_web` imports the same modules (`tl_web/present.py` is the only importer of `tl_tui`), so a module here
must not import `textual`, `rich` widgets, `tl_tui.app` or any `widgets/*`; allowed imports: `tl_mod_materials.views`
(models only), `tl_tui.layout`, `tl_tui.display`, `tl_tui.text`, `tl_tui.client` (types), `tl_tui.materials_text`.
There is no `details/materials.py`: the panel and the record screen both call the module's `*_page` function
(spec §9 listed it; one module per screen avoids two tickets editing one file).

## Shape every module follows (names are the contract; W = a web twin calls it)
- `COLUMNS: tuple[str, ...]` and `DROP: tuple[str, ...]` (least needed first; not edited into `layout.py`).
- `columns_for(rows) -> tuple[str, ...]`: `COLUMNS` minus any column whose value does not vary in `rows` (skill rule);
  Number, Subject, State stay first where the log has them. W
- `row_cells(view, columns, labels=None, *, technical=False) -> tuple[str, ...]`, cells in the order of `columns`. W
- `*_page(view, ..., labels=None, *, technical=False) -> Page`: identity, state line, `summary`, sections
  in the order of spec §7. `*_lines(...) -> list[str]` is `plain_lines(page)`. W
- `summary_line(shown, total, *, <filters>) -> str` and `KEYS` (the keys-row text, one line at 170 columns). W
- Cycle helpers for keyed filters (`next_kind(current, kinds)`, as `tag_text.next_class`).
- Pure: no client call, no clock (the date is a parameter), no I/O. Quantities are `Decimal` in, text out.

## Module list, owners and shared helpers
| Module | Ticket | Holds |
|---|---|---|
| `materials_text.py` | T06a | shared: `qty_text(Decimal) -> str` (trailing zeros dropped, at most 3 decimals, integer part grouped by a plain space, `0` for zero), `mtr_mark(state) -> str` (`present` ✓, `missing` —, `n/a` n/a), `day(iso) -> str` (first 10 chars, `—` for None), `who(labels, actor) -> str`; plus the stock log and the movement log (below) |
| `receipt_text.py` | T06b | receipt log |
| `receipt_entry_text.py` | T06e | form field list, line validation messages, status-line texts |
| `item_text.py`, `location_text.py` | T06c | item library, locations |
| `mto_text.py` | T06d | MTO lines and shortages |
T06b-e import `materials_text` and so wait for T06a; they share no other file.

## Per screen (columns, state, keys, panel; the view model is `tl_mod_materials.views`)
- **Stock** (`materials_text`): `STOCK_COLUMNS = (Lot, Subject, Location, On hand, Reserved, Available, UOM)`; Lot is the heat, else the
  lot key; Subject is `item_title`; UOM dropped when constant; right-aligned numbers are
  `On hand`, `Reserved`, `Available` (`RIGHT`). No State column. Keys `/ l i h z`. `lot_page(detail: LotDetailView, row)`: identity
  `heat · item_title`, second line `Lot <key> · received <day>` (receipt number only: LotDetailView has no date, so `Lot <key> · receipt <number>`),
  summary `<location title> · N on hand · N reserved · N available` for the selected row; sections Quantities (table Location, On hand,
  Reserved, Available), Reservations (table MTO line, Location, Qty; note `No reservations`), Movements (Date, Kind, Qty, From, To, By; last 10),
  Traceability (Receipt, PO line, Heat, MTR taken from the receipt: the screen passes `mtr: str | None`).
- **Movement log** (`materials_text`): `MOVEMENT_COLUMNS = (Date, Kind, Lot, Item, Qty, From, To, By)`; Date is `recorded_at[:10]`; Kind is a
  word (`issue` Issue, `transfer` Transfer, `return` Return, `adjust` Adjust, `scrap` Scrap, `receipt` Receipt, `reserve` Reserve,
  `unreserve` Release); Qty signed by `direction` (`in` +, `out` -). Keys `k` kind, `p` period (`next_kind`, `next_period`). Read only; no panel actions.
- **Receipts** (`receipt_text`): `RECEIPT_COLUMNS = (Number, Subject, State, Received, Location, Lines, MTR)`; MTR cell is `mtr_mark`. Keys `o` open
  only (not Accepted, Rejected, Void), `m` missing MTR (the route's flags). `receipt_page(detail: ReceiptDetailView)`: identity `number · title`; state
  `<state> · since <day>`; summary `PO <po_line> · N lines · <location>`; sections Lines (table Line, Item, Qty, UOM, Heat, Condition), Delivery
  (Supplier, PO line, Delivery ref, Received on), Inspection (Inspected by, Inspected on, Decided by, Decided on, Rejection reason when Rejected;
  `Receiving inspection  n/a until quality inspections exist`), Files (MTR slot first; amber `required to accept` when `mtr_required` and missing).
- **Items** (`item_text`): `ITEM_COLUMNS = (Number, Subject, State, Category, UOM, Projects)`; Number is `code`; State `Active` or `Retired`;
  Category via the code-list label. Panel summary `<Category> · <UOM> · used in N projects`; section Specification (Size, Rating, Material, Consumable
  `Yes`/`No`). The Projects table of §7 is deferred (D26).
- **Locations** (`location_text`): `LOCATION_COLUMNS = (Number, Subject, Kind, Lots, Lines)`; Subject indented two spaces per `depth`. Panel summary
  `<Kind> under <parent path> · N lots`; the parent path comes from the rows already loaded (`parent_code` chain). Sections Contents (table Lot, Item, On hand;
  the screen passes the stock rows of `list_materials_stock(location=code)`), Children (code, title).
- **MTO lines** (`mto_text`): `MTO_COLUMNS = (Number, Subject, For, Required, Reserved, Issued, Short, Need by)`; Number is the line key, Subject the item
  title, For the work package number, Need by `—` when None. Views: `1` all lines, `2` short only (the route's flag). Panel summary
  `For <work package> · short N <UOM>`; sections Source (MTO key, document revision parsed from `<doc>@<rev>/MTO...`), Coverage (Required, Reserved,
  Issued, Short as property lines). The Coverage lot table and Open receipts are deferred (D26).

## Deferred, no view or field for it (D26; Q6 raised to the orchestrator)
`MovementView` and `ReservationView` carry ids, not the MTO line key, cost code or work package, so the movement log and the lot panel have no `For`
column; the receipt has no `received_by`; no route returns the reservations of one MTO line, per-project quantities of an item, or the open receipts of a PO
line. Piece S5 (`S5-view-keys.md`, dec Q6 YES, r6) adds them (`MovementView.mto_line/work_package/cost_code`, `ReservationView.work_package`, `ReceiptDetailView.received_by`, `MtoLineDetailView`, `ItemProjectView`); this section is lifted when S5 merges (T06b-e carry the columns, T06g the movement and lot `For`); until then the text modules omit those columns and sections and the T06 reports say so.

## Tests and acceptance for a text module
No pytest (D1). The ticket's acceptance script prints, for 80 and 170 columns, the panel `plain_lines` and the first rows of the table from a
`FakeClient`/`fakes_materials` fixture or a copy of `.accept/p2-i3.db`, and asserts: no `None`, no `-` as a value, `—` for empty, every line of the table within
the width, the columns of `columns_for`, and that `import tl_tui.<x>_text` leaves `textual` out of `sys.modules`.
