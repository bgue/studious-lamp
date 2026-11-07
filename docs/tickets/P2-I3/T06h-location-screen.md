# P2-I3-T06h — location_text.py and LocationScreen (storage locations)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06a (merged), T06f (merged: StockScreen), T04b (merged), T06d (merged; the freshest precedent)
Branch: `p2/i3-t06h-location-screen`

## Goal
The storage locations as a Textual-free text module plus a read-only `LogScreen` in tree order, unregistered. Screenshots `.accept/shots/T06h-locations-<w>.svg`.

## Brief references (pasted)
> Contract: `docs/tickets/P2-I3/text-contracts.md` "Shape every module follows", "Locations (`location_text`)" and "Screens". Layout rules: skill `tui-layout`.
> `LOCATION_COLUMNS = ("Number", "Subject", "Kind", "Lots", "Lines")`; Number = `code`; Subject = `title` indented two spaces per `depth` (a leading-space cell is fine; no tree glyphs); Kind = word (`humanize(kind)`, `warehouse` becomes `Warehouse`); Lots, Lines = counts as text.
> `LOCATION_DROP = ("Lines", "Kind", "Lots")` (least needed first); `RIGHT = frozenset({"Lots", "Lines"})`. `columns_for(rows)` drops Kind, Lots and Lines when every row has the same value; Number and Subject never drop. There is no State column: a retired location shows `(retired)` after its title in Subject.
> `LOCATION_KEYS = "s stock here  / filter  F5 reload  Esc close"`; `summary_line(shown, total, *, text="")` reads `Showing 9 of 9 locations` plus `· filter "x"` when set.
> `location_page(location, locations, stock, labels=None, *, technical=False) -> Page`: identity `code · title`; state `Active` or `Retired`; summary `<Kind> under <parent path> · N lots` (root: `<Kind> · N lots`; parent path = the `code`s from the root down to the parent, joined ` › `, found by following `parent_code` through `locations`, the rows already loaded; stop on a cycle or a missing parent; N lots = `location.lots`); sections **Contents** (table `Lot, Item, On hand` from `stock`, the `StockRowView`s at this location: Lot = `heat_no or lot` as the stock log shows it, Item = `item_code`, On hand = `qty_text` plus space plus `unit_label(uom)`; note `No stock here`) and **Children** (table `Code, Title` of the locations whose `parent_code` is this code, in tree order; note `No child locations`); `technical` adds an Id line to a first section `Location` only when set (otherwise no such section). `location_lines(location, locations, stock, labels=None, *, technical=False, width=None) -> list[str]` is `plain_lines`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views.LocationView: id code title kind parent_code(str|None) depth(int) retired(bool) lots(int) lines(int)
# tl_mod_materials.views.StockRowView: lot heat_no item_code item_title location location_title on_hand reserved available uom
# ClientInterface: list_materials_locations(self, project: str, *, limit: int = 1000) -> list[LocationView]
#                  list_materials_stock(self, project, *, lot=None, location=None, item=None, heat=None, subtree=False, limit=1000) -> list[StockRowView]
# tl_tui.materials_text: qty_text(Decimal) -> str
# tl_tui.layout: EMPTY Page Prop Section TableRow identity_line join_facts plain_lines prop shown(as _shown) Panel render
# tl_tui.display: Labels humanize mode_of    tl_tui.text: unit_label
# tl_tui.widgets.stock_screen.StockScreen(client, project, *, location: str | None = None)
# shape to copy: tl_tui/mto_text.py and widgets/mto_screen.py (whole)
```
`LocationScreen(client: ClientInterface, project: str)` in `widgets/location_screen.py`: `LOG_NAME` "Locations", `KEY_HINTS` = `LOCATION_KEYS`, `KEY_CELLS` ("s stock here", "/ filter"), `BINDINGS` for `s` (does nothing while `isinstance(self.focused, Input)` or no row is highlighted) that does `self.app.push_screen(StockScreen(self.client, self.project, location=row.code))`;
`drop_order` = `LOCATION_DROP`, `keep_columns` = Number, Subject. `load_rows`: `list_materials_locations(project, limit=MAX_VIEW_ROWS)` (`from tl_mod_materials.limits import MAX_VIEW_ROWS`), kept in `self.views`. `panel_text`: `list_materials_stock(project, location=row.code, limit=MAX_VIEW_ROWS)` (no subtree), errors via `CLIENT_ERRORS`/`describe_error`/`self.say`
and the panel text `This location could not be read.`. `row_key` = `row.code`; `row_record` = `(row.code, row.title)`; `actions_for` returns `[]`; `open_row` does nothing.

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`, `packages/tl-tui/src/tl_tui/mto_text.py` and `packages/tl-tui/src/tl_tui/widgets/mto_screen.py` (whole; the shape)
- `dev/accept/P2-I3/T06d.py` (whole: seed copy, `EmbeddedClient`, `TlApp` host, `settle`, `screen_text`, screenshot save; copy its helpers)
may explore: `widgets/log_screen.py`, `widgets/stock_screen.py` (constructor only), `layout.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/location_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/location_screen.py` (create)
- `dev/accept/P2-I3/T06h.py` (create), `docs/reports/P2-I3/T06h.md` (create)
Not here: `materials_text.py`, `stock_screen.py`, `app.py`, `client.py`, `log_screen.py`, `layout.py`, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06h.py
```
`T06h.py` (you write it; exit 0; one `PASS <check>` per line): (1) text, over a temp copy of the seed ledger (project `P123`, nine locations, root `P123`, `WH1`, `L1`): for widths 80 and 170 print `location_lines(...)` for `WH1` and for a leaf with stock, and the first rows as joined cells; assert no `None`, no standalone `-`,
the summary of `L1` names `P123 › WH1`, the root summary has no `under`, sections in the order Contents, Children, `No child locations` on a leaf, `No stock here` on a hand-built empty one, a child indented in Subject, every table line within the width; `import tl_tui.location_text` leaves `textual` out of `sys.modules` (fresh subprocess).
(2) screen: push `LocationScreen(client, "P123")` on `TlApp` at (80, 30) and (170, 40); `screen_text` shows `WH1` and the keys row; `down` shows the panel with `Contents`; press `s` on a location and assert a `StockScreen` is the top screen, Esc returns; Esc closes; save
`app.export_screenshot(title="Locations")` to `.accept/shots/T06h-locations-<w>.svg`.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the screenshot paths. Commit subjects `P2-I3-T06h: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if a contract line needs `textual` in the text module, or if a name listed under Interfaces is missing.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
