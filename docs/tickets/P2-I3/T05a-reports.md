# P2-I3-T05a — Materials reports and the report route

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: api, core-read
Depends on: T04a (merged), S4 (merged)
Branch: `p2/i3-t05a-reports`

## Goal
`tl_mod_materials/reports.py`: six read-only reports built from the existing views (no SQL, no schema), a formula-safe CSV writer, and one route
`GET /projects/{project}/materials/reports/{name}`. T05b (CLI `tl mat report`) and the web twins call the same functions.

## Brief references (pasted)
> Reports (`tl mat report`, API, CSV with formula-safe cells): `stock_on_hand`, `movement_log` (period), `mto_status` (per work package and item: required, received, reserved, issued),
> `shortages`, `heat_trace` (heat -> lots -> receipt -> MTR file -> locations -> issues), `consumables_by_cost_code` (period).
> Views are viewer-filtered and the route passes no viewer (D23). A spreadsheet runs a text that starts with `= + - @` (or tab/CR) as a formula: write it with a leading `'`; a plain number (`-3`, `1.5`) is left alone.

## Interfaces (verbatim from repo at the branch point)
```python
# views (T04a ticket lists the signatures): stock, lot_detail, movements, receipts, receipt_detail, mto_lines, items
# ReceiptDetailView.files: list[ReceiptFileView(file_id, slot, filename, status, uploaded_at)]; the MTR slot is "mtr"
# tl_mod_cost.views.cost_codes(conn, scope) -> list[CostCodeView(id, code, title, ...)]   # the route builds {id: code} for consumables_by_cost_code
```
To create in `reports.py` (the signatures are the contract; T05b and the web call them):
```python
REPORT_NAMES: Final = ("stock_on_hand", "movement_log", "mto_status", "shortages", "heat_trace", "consumables_by_cost_code")
class Report(BaseModel): name: str; columns: list[str]; rows: list[list[str]]; truncated: bool   # truncated: a view returned MAX_VIEW_ROWS rows
def build_report(conn, scope: str, name: str, *, since: str | None = None, until: str | None = None, heat: str | None = None,
                 cost_codes: Mapping[str, str] | None = None) -> Report        # unknown name: ValueError; heat_trace without heat: ValueError
def safe_cell(value: str | None) -> str
def to_csv(report: Report) -> str                                               # header row, then rows, csv.writer, "\r\n", every cell through safe_cell
```
Columns and sources (quantities as `format(Decimal, "f")` of the view value, no exponent; empty = `""`):
- `stock_on_hand`: Lot, Heat, Item, Description, Location, On hand, Reserved, Available, UOM <- `views.stock(limit=MAX_VIEW_ROWS)`
- `movement_log`: Date (`recorded_at[:10]`), Kind, Lot, Item, Qty, UOM, From, To, By, Reason <- `views.movements(since, until)`
- `mto_status`: Work package, Item, UOM, Required, Received, Reserved, Issued <- `views.mto_lines` grouped by (work_package or "", item_code), quantities summed; `Received` is the project-wide `qty_received` total of that item code over `views.po_lines` (the same on every work package row; `0` when the item has no PO line)
- `shortages`: Work package, Line, Item, UOM, Required, Reserved, Issued, Short <- `views.mto_lines(short_only=True)`
- `heat_trace` (needs `heat`): columns Heat, Lot, Receipt, MTR file, Event, Date, Location, Qty. For each stock row with that heat, grouped by lot: one `On hand` row per balance
  (Date `""`, Location, Qty = on hand) and one `Issued` row per issue movement of that lot (`views.movements(lot=..., kind="issue")`: Date, Location = `from_location`, Qty); Receipt and
  MTR file come from `lot_detail(...).receipt` and `receipt_detail(...).files` (slot `mtr`, filename, else `""`). An unknown heat gives zero rows, not an error.
- `consumables_by_cost_code` (period): Cost code, Item, UOM, Qty issued <- issue movements in the period whose item is `consumable` in `views.items` and whose `cost_code_id` is set; label =
  `cost_codes.get(id, id)`; summed by (label, item_code, uom), sorted by label then item.
Rows are sorted as the view returns them except where "sorted" is said. Route: query `since`, `until` (`max_length=10`), `heat` (`max_length=200`), `format` (`json` default | `csv`);
`name` is a `Literal` of `REPORT_NAMES` (unknown = 422); guard `document.read`; operation id `get_materials_report`; `csv` answers `text/csv` with `Content-Disposition: attachment; filename="<name>.csv"`.
The route fills `cost_codes` with `{c.id: c.code for c in tl_mod_cost.views.cost_codes(conn, scope)}` for `consumables_by_cost_code` only.

## Context (read these, nothing else)
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (signatures and models; read only), `limits.py`
- `packages/tl-api/src/tl_api/routes/materials.py` (add the route at the end; same `Ctx`, `Reader`)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/export.py` lines 83-90 (`safe_cell`; copy the rule, do not import it)
- `packages/tl-api/tests/test_confidentiality_walk.py` (`MIN_ROUTES`)
- `dev/accept/P2-I3/T04a.py` (how the routes were driven) and `S3.py` (`--keep`: seed ledger `.accept/p2-i3.db`, heat `H-7781`, MTO `ISO-1234@A/MTO` for `P123-CWP-PIP-0001`)

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/reports.py` (create)
- `packages/tl-api/src/tl_api/routes/materials.py` (the new route and its imports only)
- `packages/tl-api/tests/test_confidentiality_walk.py` (`MIN_ROUTES` +1), `docs/reference/openapi.json` (regenerate: `uv run python -m tl_api.openapi`)
- `dev/accept/P2-I3/T05a.py` (create), `docs/reports/P2-I3/T05a.md` (create)
Not here: `views.py`, any SQL, `tl_cli`, other routes. If a report needs a field the views lack, write it under *Blocked*.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T05a.py
just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_error_table.py packages/tl-api/tests/test_auth_review.py
```
`T05a.py` (you write it, exit 0, one `PASS <check>` per line) on a copy of the seed ledger: each of the six names builds; `stock_on_hand` rows equal `views.stock`; `heat_trace` for `H-7781` has
`On hand` rows for both lots and a non-empty MTR file name, `H-0000` zero rows, no heat is `ValueError`; `shortages` rows all have `Short > 0`; `mto_status` for `P123-CWP-PIP-0001` sums to
the three seeded lines; `safe_cell("=1+1")` is `'=1+1`, `safe_cell("-3")` is `-3`, `safe_cell("+cmd|x")` starts with `'`; `to_csv` of a movement report with a reason `=HYPERLINK(...)` has the cell quoted;
the route answers 200 JSON and CSV (content type and filename), unknown name 422, no token 401, `format=csv` first line is the header; the file has no `viewer` argument (grep).
The five-reader walk over classified records is T11's (report line).

## Tests to add
None (T11: `packages/tl-modules/materials/tests/test_reports.py` in the T05 list).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines. Commit subjects `P2-I3-T05a: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a report cannot be built from the listed views, if `tl_mod_cost` is not importable from `tl_api`, or if the walk fails for a reason other than `MIN_ROUTES`.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
