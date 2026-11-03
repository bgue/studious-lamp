# P2-WEB1 M4 twins (T12, T12b, T13, T13b, T14, T14b; T17 seeds their data): what differs from TWINS.md

Status: staged. Nothing here is dispatchable until the ACTIVATION list is true (supervisor r9, after the orchestrator merged p2/i3).
The recipe is `TWINS.md`; this file only states what the six materials pages change. Each page is the web twin of one P2-I3 screen
(`widgets/stock_screen.py`, `movement_screen.py`, `receipt_log.py`, `mto_screen.py`, `item_library.py`, `location_screen.py`) and uses
its text module (`tl_tui/materials_text.py`, `receipt_text.py`, `mto_text.py`, `item_text.py`, `location_text.py`), reached as
`present.<module>`. Contract of the modules: `docs/tickets/P2-I3/text-contracts.md` (on p2/i3).

## ACTIVATION (supervisor; in this order)
1. Orchestrator merges `p2/i3` into `p2/web1` (asked in the r8 relay NOTE). A conflict goes to the r9 round, never to a ticket.
2. Seam (r9, one commit, <= 50 diff lines or a Haiku ticket if over): in `reads.py` the ten mirrors `list_materials_stock get_materials_lot
   list_materials_movements list_materials_receipts get_materials_receipt list_materials_locations list_materials_mto_lines
   get_materials_mto_line list_materials_items list_materials_item_projects` (MIRRORS 32 -> 42, same names and keyword arguments as
   `ClientInterface`, route functions of `tl_api.routes.materials`), `present` re-exports of the five text modules, six empty page stubs
   (`stock movements receipts mto items locations`) named in `PAGE_MODULES`, six WALK markers (`T12 rows` ... `T14b rows`), the mirror
   cases (the three single-record reads join `ABSENT`; `list_materials_item_projects` answers `[]`).
3. T17 merged (the seed). 4. The Open link question (OPEN Q5) answered.

## Differences from TWINS.md
- Fake: `FakeMaterialsSupport` (`packages/tl-tui/tests/fakes_materials.py`) seeded by `seed_materials(fake, "P123")` of T17
  (`packages/tl-tui/tests/fakes_materials_seed.py`), both loaded by path as `load_fake()` loads `fakes_awp.py`. Patch the mirrors the page reads.
- Columns: `columns()` returns the module's full tuple (`STOCK_COLUMNS`, `MOVEMENT_COLUMNS`, `RECEIPT_COLUMNS`, `MTO_COLUMNS`, `ITEM_COLUMNS`,
  `LOCATION_COLUMNS`); the web log drops a constant column itself (`columns_for` is not used). `drop_order` = the module's `*_DROP`. Cells are
  `<x>_cells(row, <columns>, ...)` / `row_cells(row, <columns>)` as the module defines them (read its signature; `technical=self.technical`).
- Filters are query strings read in `load_rows` (recipe 4); a value that is not in the allowed set means absent. They narrow the server list.
- Numbers (`row_record[0]`) must be unique per row and are the panel URL: pinned per ticket.
- A 404 from any read (`body_for(exc)[0] == 404`; the materials errors map to `materials_*_not_found`, not only `record_not_found`) is the one
  404 page: do not catch it, except where the ticket says. Quantities are shown by the module's `qty_text`; never format a number yourself.
- Read only: `actions_for` returns `[]`. No `|safe`, no new template or CSS. Gate: the three walk tests as in TWINS.md.
