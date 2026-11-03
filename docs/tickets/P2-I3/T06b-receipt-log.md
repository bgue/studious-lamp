# P2-I3-T06b — `receipt_text.py` and ReceiptLogScreen (the receipts log and receipt panel)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06a (merged), S5 (merged: `received_by`)
Branch: `p2/i3-t06b-receipt-log`

## Goal
The goods-receipts log with its panel: a Textual-free text module (contract: `text-contracts.md`, "Receipts") and the read-only `LogScreen` that mounts it. Unregistered; the owner sees it in the acceptance screenshots.

## Brief references (pasted)
> Contract for the module and the screen: `docs/tickets/P2-I3/text-contracts.md` (read whole; "Shape every module follows", "Receipts", "Screens"). Skill `tui-layout` rules are stated there.
> `RECEIPT_COLUMNS = (Number, Subject, State, Received, Location, Lines, MTR)`; Number is `number`, Subject `title`, State the humanized state, Received `received_on[:10]`, Location the code, Lines the count, MTR `mtr_mark(view.mtr)`. `RIGHT = {Lines}`. DROP (least needed first): `Lines, Location, MTR, Received`.
> Keys `o` open only, `m` missing MTR (both are the route's flags, so the screen re-reads), `/` filter. `KEYS = "o open only  m missing MTR  / filter  F5 reload  Esc close"`.
> `receipt_page`: identity `number · title`; state `<State> · since <day>` (day of `decided_on`, else `inspected_on`, else `received_on`; `day()`); summary `PO <po_line or —> · N lines · <location>`; sections in this order
> Lines (table Line, Item `item_code title`, Qty, UOM, Heat, Condition; UOM dropped when constant; Heat `—` when None), Delivery (Supplier, PO line, Delivery ref, Received on, Received by via `who(labels, received_by)`), Inspection (Inspected by, Inspected on,
> Decided by, Decided on, then `Rejection reason` only when state is `Rejected`; last line `Receiving inspection  n/a until quality inspections exist`), Files (table Slot, File, Status with the `mtr` slot first; amber note `MTR required to accept` when `mtr_required` and `mtr` is `missing`; note `No files` when none).
> Empty values in Delivery and Inspection are `—`. People through `who`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views
class ReceiptView(BaseModel): id, number, title, state, received_on, location, supplier_text, delivery_ref: str|None, po_line: str|None, lines: int, mtr: MtrState, mtr_required: bool
class ReceiptLineView(BaseModel): line_no, item_code, item_title, qty: Decimal, uom, heat_no: str|None, condition, serials_text: str|None, lot: str|None
class ReceiptFileView(BaseModel): file_id, slot: str|None, filename, status, uploaded_at
class ReceiptDetailView(ReceiptView): created_at, inspected_by, inspected_on, decided_by, decided_on, rejection_reason, received_by (all str|None), line_rows: list[ReceiptLineView], files: list[ReceiptFileView]
# tl_tui.materials_text: EMPTY qty_text(Decimal) mtr_mark(state) day(iso) who(labels, actor) next_kind(current, kinds)
# tl_tui.layout: Page(identity, state, sections, summary) Section(heading, items, note) Prop(label, value) TableRow(columns, cells) Cell(text, style) plain_lines(page, *, identity=True, width=None) render(page)
# ClientInterface: list_materials_receipts(project, *, open_only=False, missing_mtr=False, limit=1000) get_materials_receipt(project, number)
```
Create `packages/tl-tui/src/tl_tui/receipt_text.py` with: `RECEIPT_COLUMNS`, `RECEIPT_DROP`, `RIGHT`, `KEYS`, `columns_for(rows)`, `row_cells(view, columns, labels=None, *, technical=False)`, `summary_line(shown, total, *, open_only=False, missing_mtr=False, text="")`
(`Showing N of M receipts · open only · missing MTR`), `receipt_page(detail, labels=None, *, technical=False) -> Page` (`technical` adds the receipt `id` as a Delivery property `Id`), `receipt_lines(detail, labels=None, *, technical=False, width=None) -> list[str]`.
And `packages/tl-tui/src/tl_tui/widgets/receipt_log.py`: `ReceiptLogScreen(client: ClientInterface, project: str)`, `LOG_NAME` "Receipts", `keep_columns` Number, Subject, State; `load_rows` calls `list_materials_receipts(project, open_only=..., missing_mtr=..., limit=MAX_VIEW_ROWS)`
(`from tl_mod_materials.limits import MAX_VIEW_ROWS`); `panel_text` calls `get_materials_receipt(project, row.number)`; `row_key` the number; `row_record` `(number, title)`.

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`, `packages/tl-tui/src/tl_tui/materials_text.py` (signatures: `grep -n "^def \|^[A-Z_]* ="`; read `lot_page` for how a Page with tables is built)
- `packages/tl-tui/src/tl_tui/tag_text.py` (shape of a text module), `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (shape of the screen)
- `dev/accept/P2-I3/T04b.py` lines 270-292 and `dev/accept/P2-W0/RM-S3.py` lines 381-405 (seed copy + `EmbeddedClient`; `run_test`, `settle`, `screen_text`, `TlApp`)
may explore: `widgets/log_screen.py`, `layout.py` lines 99-146

## Allowed paths
- `packages/tl-tui/src/tl_tui/receipt_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/receipt_log.py` (create)
- `dev/accept/P2-I3/T06b.py` (create), `docs/reports/P2-I3/T06b.md` (create)
Not here: `materials_text.py`, `app.py`, `client.py`, `log_screen.py`, `layout.py`, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06b.py
```
`T06b.py` (you write it; exit 0; one `PASS <check>` per line): (1) over a temp copy of the seed ledger (project `P123`, receipt `P123-RCPT-0001`, heat H-7781, MTR attached): for widths 80 and 170 print `receipt_lines(detail, width=w)` and the first rows of the log as joined cells; assert no `None`, no standalone `-`,
`—` for empty, every table line within the width, the sections in the order Lines, Delivery, Inspection, Files, `Received by` present, `columns_for` drops a constant column (build two `ReceiptView`s by hand: same location, then two locations); a hand-built Rejected detail shows `Rejection reason`; an
unrejected one does not; `mtr_required` with `mtr="missing"` shows `required to accept`; `import tl_tui.receipt_text` leaves `textual` out of `sys.modules` (fresh subprocess).
(2) the screen: push `ReceiptLogScreen(client, "P123")` on `TlApp` at (80, 30) and (170, 40); `screen_text` shows `P123-RCPT-0001`; `down`/`up` shows its panel; `o` and `m` change the summary text; Esc closes; save `app.export_screenshot(title="Receipts")` to `.accept/shots/T06b-receipts-<w>.svg`.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the two screenshot paths. Commit subjects `P2-I3-T06b: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if a contract line needs `textual` in the text module, or if `layout` cannot express a table with a note.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
