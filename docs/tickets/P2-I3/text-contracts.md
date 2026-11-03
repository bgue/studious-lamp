# P2-I3 screen text contracts (T06a-h, and the web twins T12-T14 of P2-WEB1)

Decision D25 (r5), updated r7 (D35-D37; S5 merged, so the D26 deferrals are lifted). Each screen keeps everything it shows in a
Textual-free module `packages/tl-tui/src/tl_tui/<x>_text.py` (precedent: `tag_text.py`, `schedule_text.py`, M3 D27). The screen widget only mounts,
moves selection and calls these functions. `tl_web` imports the same modules (`tl_web/present.py` is the only importer of `tl_tui`), so a module here
must not import `textual`, `rich` widgets, `tl_tui.app` or any `widgets/*`; allowed imports: `tl_mod_materials.views` and `views_detail` (models only),
`tl_tui.layout`, `tl_tui.display`, `tl_tui.text`, `tl_tui.client` (types), `tl_tui.materials_text`.
There is no `details/materials.py`: the panel and the record screen both call the module's `*_page` function.

## Shape every module follows (names are the contract; W = a web twin calls it)
- `COLUMNS: tuple[str, ...]` and `DROP: tuple[str, ...]` (least needed first; not edited into `layout.py`); `RIGHT: frozenset[str]` for numeric columns.
- `columns_for(rows) -> tuple[str, ...]`: `COLUMNS` minus any column whose value does not vary in `rows` (skill rule); Number, Subject, State stay first
  where the log has them. W (materials_text has two logs, so its names carry a prefix: `stock_columns_for`, `movement_columns_for`.)
- `row_cells(view, columns, labels=None, *, technical=False) -> tuple[str, ...]`, cells in the order of `columns`. W
- `*_page(view, ..., labels=None, *, technical=False) -> Page`: identity, state line, `summary`, sections in the order of spec §7. `*_lines(...) -> list[str]`
  is `plain_lines(page, width=width)`. W
- `summary_line(shown, total, *, <filters>) -> str` and `KEYS` (the keys-row text, one line at 170 columns). W
- Cycle helpers for keyed filters (`next_kind(current, kinds)`, as `tag_text.next_class`).
- Pure: no client call, no clock (the date is a parameter), no I/O. Quantities are `Decimal` in, text out (`materials_text.qty_text`). A `None` is `—`, never `None` or `-`.

## Module list, owners and shared helpers
| Module | Ticket | Holds |
|---|---|---|
| `materials_text.py` | T06a (merged), T06g (For) | shared `qty_text`, `mtr_mark`, `day`, `who`; stock log, lot panel, movement log |
| `receipt_text.py` | T06b | receipt log and receipt panel |
| `receipt_entry_text.py` | T06e | form field list, line validation messages, status-line texts |
| `item_text.py` | T06c | item library and its panel |
| `location_text.py` | T06h | locations and their panel |
| `mto_text.py` | T06d | MTO lines, shortages, line panel |
T06b-e, T06h import `materials_text` and share no other file.

## Per screen (columns, state, keys, panel; the view model is `tl_mod_materials.views` / `views_detail`)
- **Stock** (`materials_text`, done): `STOCK_COLUMNS = (Lot, Subject, Location, On hand, Reserved, Available, UOM)`; no State column. Keys `/ l i h z`.
  `lot_page(detail, row)`: sections Quantities, Reservations, Movements, Traceability. T06g adds `For` to the Reservations table (below).
- **Movement log** (`materials_text`): `MOVEMENT_COLUMNS = (Date, Kind, Lot, Item, Qty, For, From, To, By)` after T06g (T06a has no For). Kind words are keyed by the
  LEDGER kinds `MOVEMENT_KINDS` (`receive` Receipt, `issue` Issue, `transfer` Transfer, `return` Return, `adjust` Adjust, `scrap` Scrap, `reserve` Reserve,
  `unreserve` Release; D35). **For** is `MovementView.work_package`, else `cost_code`, else `—` (`mto_line` is not shown; the work package is the reader's word). Qty is signed by
  `direction` (`in` +, `out` -); when `direction` is None the sign follows the kind as `tl mat movements` does (`receive`, `return` +; `issue`, `scrap` -; others unsigned; D35).
  `For` is dropped last (after By, Item, To, From). Keys `k` kind, `p` period. Read only. Lot panel Reservations table: `MTO line, For, Location, Qty`, For = `ReservationView.work_package`.
- **Receipts** (`receipt_text`): `RECEIPT_COLUMNS = (Number, Subject, State, Received, Location, Lines, MTR)`; MTR cell is `mtr_mark`. Keys `o` open only
  (not Accepted, Rejected, Void), `m` missing MTR (the route's flags). `receipt_page(detail: ReceiptDetailView)`: identity `number · title`; state `<state> · since <day>`
  (the day of the last decision, else inspection, else receipt); summary `PO <po_line> · N lines · <location>`; sections Lines (table Line, Item, Qty, UOM, Heat, Condition),
  Delivery (Supplier, PO line, Delivery ref, Received on, **Received by**), Inspection (Inspected by, Inspected on, Decided by, Decided on, Rejection reason when Rejected;
  `Receiving inspection  n/a until quality inspections exist`), Files (MTR slot first; amber `required to accept` when `mtr_required` and missing).
- **Items** (`item_text`): `ITEM_COLUMNS = (Number, Subject, State, Category, UOM, Projects)`; Number is `code`; State `Active` or `Retired`; Category via the code-list label.
  `item_page(item: MaterialItemView, projects: Sequence[ItemProjectView])`: summary `<Category> · <UOM> · used in N projects`; sections Specification (Size, Rating, Material,
  Consumable `Yes`/`No`) and **Projects** (table Project, On hand, Reserved, Available; note `Not used in any project`; D37: `ItemProjectView.title` is the project id, so the column is the id).
  The screen passes `projects` from `list_materials_item_projects(code)`.
- **Locations** (`location_text`): `LOCATION_COLUMNS = (Number, Subject, Kind, Lots, Lines)`; Subject indented two spaces per `depth`. Panel summary `<Kind> under <parent path> · N lots`;
  the parent path comes from the rows already loaded (`parent_code` chain). Sections Contents (table Lot, Item, On hand; the screen passes the stock rows of
  `list_materials_stock(location=code)`), Children (code, title).
- **MTO lines** (`mto_text`): `MTO_COLUMNS = (Number, Subject, For, Required, Reserved, Issued, Short, Need by)`; Number is the line key, Subject the item title, For the work package
  number, Need by `—` when None. Views: `1` all lines, `2` short only (the route's flag). `mto_page(detail: MtoLineDetailView)`: identity `<key> · <item title>`; state `Short N <UOM>` or `Covered`;
  summary `For <work package> · required N · short N`; sections Source (MTO key, document revision parsed from `<doc>@<rev>/MTO...`), Coverage (Required, Reserved,
  Issued, Short as property lines), **Reservations** (table Lot, Location, Qty; note `No reservations`), **Open receipts** (table Receipt, State, Received on, Qty; note `No open receipts`).

## Screens (T06b, T06c, T06d, T06f, T06h each end with a screen; D36)
Each screen is a `LogScreen` subclass (precedent `widgets/tag_register.py`; hooks in `widgets/log_screen.py`) in `packages/tl-tui/src/tl_tui/widgets/<x>.py`, built as
`Screen(client, project)` (the item library takes `project: str | None = None`), UNREGISTERED: no nav entry, no `app.py` change (registry glue is the supervisor's, last).
- Overrides: `LOG_NAME`, `KEY_HINTS` (= the module's KEYS text), `KEY_CELLS`, `HELP_KEYS`, `BINDINGS` for the screen's own keys, `log_project`, `columns` (via `columns_for` on the rows), `drop_order` (= `DROP`),
  `keep_columns` (the base keeps a `State` column: a log without one returns Number and Subject only), `load_rows` (one list call; the filters are the screen's), `row_key`, `row_cells`,
  `row_record`, `panel_text` (one detail call per highlighted row, errors via `CLIENT_ERRORS`/`describe_error` and `self.say`, then `render(page)`), `summary_text`.
- Read only: `actions_for` returns `[]`; `open_row` does nothing yet (record screens come with the web twins). Keys that are text inside the filter box do nothing (`isinstance(self.focused, Input)`).
- `LogTable` has no alignment hook, so `RIGHT` columns stay left-aligned in the TUI; the web twin uses `RIGHT`.
- The clock: a screen passes `date.today().isoformat()` to `period_range`; the text module never reads it.
- Screenshots are part of acceptance: the script pushes the screen on `TlApp` with a client over a copy of `.accept/p2-i3.db` (project `P123`), at 80x30 and 170x40, and saves
  `app.export_screenshot(title=...)` to `.accept/shots/<ticket>-<w>.svg` (untracked; the owner opens them). Precedent for the host, `settle` and `screen_text`: `dev/accept/P2-W0/RM-S3.py` (lines 383-402).

## Tests and acceptance for a text module
No pytest (D1; T11 owns the tests). The ticket's acceptance script prints, for 80 and 170 columns, the panel `plain_lines` and the first rows of the table from a `FakeClient`/`fakes_materials` fixture or
a copy of `.accept/p2-i3.db`, and asserts: no `None`, no `-` as a value, `—` for empty, every line of the table within the width, the columns of `columns_for`, and that `import tl_tui.<x>_text` leaves
`textual` out of `sys.modules` (fresh subprocess).
