# P2-I3-T06d — `mto_text.py` and MtoLinesScreen (MTO lines, shortages, line panel)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06a (merged), S5 (merged: `MtoLineDetailView`)
Branch: `p2/i3-t06d-mto-lines`

## Goal
The material take-off lines of a project with what is reserved, issued and short, and a panel with where each line is covered from: a Textual-free text module (contract: `text-contracts.md`, "MTO lines") and the read-only `LogScreen`
that mounts it. Unregistered; the owner sees it in the acceptance screenshots.

## Brief references (pasted)
> Contract: `docs/tickets/P2-I3/text-contracts.md` (read whole; "Shape every module follows", "MTO lines", "Screens").
> `MTO_COLUMNS = (Number, Subject, For, Required, Reserved, Issued, Short, Need by)`; Number is `key`, Subject `item_title`, For `work_package` (`—` when None), numbers via `qty_text`, Need by `need_by[:10]` or `—`. `RIGHT = {Required, Reserved, Issued, Short}`.
> DROP (least needed first): `Need by, Issued, For`. A log without a State column: Number and Subject stay first. Views `1` all lines, `2` short only (`short_only=True`). `KEYS = "1 all lines  2 short only  / filter  F5 reload  Esc close"`.
> `mto_page(detail)`: identity `<key> · <item_title>`; state `Short N <UOM>` when `short > 0`, else `Covered`; summary `For <work package or —> · required N · short N`; sections Source (MTO `mto`, Document and Revision parsed from `<doc>@<rev>/...`, `—` when the key has no `@`),
> Coverage (property lines Required, Reserved, Issued, Short, each `N <UOM>`), Reservations (table Lot, Location, Qty from `detail.reservations`; note `No reservations`), Open receipts (table Receipt, State, Received on, Qty from `detail.open_receipts`; note `No open receipts`).
> Empty values `—`. `technical` adds the line `id` to Source as `Id`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views
class MtoLineView(BaseModel): id, key, mto, line_no: int, item_code, item_title, uom, required, reserved, issued, short: Decimal, work_package: str|None, work_package_id: str|None, need_by: str|None
class ReservationRowView(BaseModel): lot, location, mto_line, mto_line_id, qty: Decimal, item_code, iwp_id: str|None
# tl_mod_materials.views_detail
class OpenReceiptView(BaseModel): number, state, received_on, qty: Decimal, uom, supplier_text
class MtoLineDetailView(MtoLineView): reservations: list[ReservationRowView], open_receipts: list[OpenReceiptView]
# tl_tui.materials_text: EMPTY qty_text(Decimal) day(iso)
# tl_tui.layout: Page(identity, state, sections, summary) Section(heading, items, note) Prop(label, value) TableRow(columns, cells) Cell(text, style) plain_lines(page, *, identity=True, width=None) render(page)
# ClientInterface: list_materials_mto_lines(project, *, work_package=None, short_only=False, limit=1000) get_materials_mto_line(project, key)
```
Create `packages/tl-tui/src/tl_tui/mto_text.py` with: `MTO_COLUMNS`, `MTO_DROP`, `RIGHT`, `KEYS`, `columns_for(rows)` (drops `For` when constant and `Need by` when constant), `row_cells(view, columns, labels=None, *, technical=False)`,
`summary_line(shown, total, *, short_only=False, work_package=None, text="")` (`Showing N of M lines · short only · for CWP-01`), `mto_page(detail, labels=None, *, technical=False) -> Page`, `mto_lines(detail, labels=None, *, technical=False, width=None) -> list[str]`.
And `packages/tl-tui/src/tl_tui/widgets/mto_screen.py`: `MtoLinesScreen(client: ClientInterface, project: str, *, work_package: str | None = None)`, `LOG_NAME` "MTO lines", bindings `1` and `2` (`Binding("1", "all_lines")`, `Binding("2", "short_only")`; no-op while the filter box has focus);
`load_rows` calls `list_materials_mto_lines(project, work_package=..., short_only=..., limit=MAX_VIEW_ROWS)` (`from tl_mod_materials.limits import MAX_VIEW_ROWS`); `panel_text` calls `get_materials_mto_line(project, row.key)`; `row_key` the key; `row_record` `(key, item_title)`; `keep_columns` Number and Subject.

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`, `packages/tl-tui/src/tl_tui/materials_text.py` (signatures: `grep -n "^def \|^[A-Z_]* ="`; read `lot_page` for how a Page with tables is built)
- `packages/tl-tui/src/tl_tui/tag_text.py` (shape of a text module), `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (shape of the screen)
- `dev/accept/P2-I3/T04b.py` lines 270-292 and `dev/accept/P2-W0/RM-S3.py` lines 381-405 (seed copy + `EmbeddedClient`; `run_test`, `settle`, `screen_text`, `TlApp`)
may explore: `widgets/log_screen.py`, `layout.py` lines 99-146

## Allowed paths
- `packages/tl-tui/src/tl_tui/mto_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/mto_screen.py` (create)
- `dev/accept/P2-I3/T06d.py` (create), `docs/reports/P2-I3/T06d.md` (create)
Not here: `materials_text.py`, `app.py`, `client.py`, `log_screen.py`, `layout.py`, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06d.py
```
`T06d.py` (you write it; exit 0; one `PASS <check>` per line): (1) over a temp copy of the seed ledger (project `P123`, MTO `ISO-1234@A/MTO`, three lines, work package `P123-CWP-PIP-0001`): for widths 80 and 170 print `mto_lines(detail, width=w)` for the first line and the first rows of the log as joined cells;
assert no `None`, no standalone `-`, `—` for empty, every table line within the width, the sections in the order Source, Coverage, Reservations, Open receipts, Document `ISO-1234` and Revision `A` parsed, `Short N` state for a short line and `Covered` for a hand-built one with short 0, `No reservations` and `No open receipts`
on a hand-built detail with none, `columns_for` drops `For` when every row has the same work package; `import tl_tui.mto_text` leaves `textual` out of `sys.modules` (fresh subprocess).
(2) the screen: push `MtoLinesScreen(client, "P123")` on `TlApp` at (80, 30) and (170, 40); `screen_text` shows an MTO line key; `down` shows the panel with `Coverage`; `2` changes the summary to `short only`, `1` restores it; Esc closes; save
`app.export_screenshot(title="MTO lines")` to `.accept/shots/T06d-mto-<w>.svg`.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the two screenshot paths. Commit subjects `P2-I3-T06d: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if a contract line needs `textual` in the text module, or if the seed ledger has no take-off lines.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
