# P2-I3-S2 — Materials package: module, projectors, library, locations, PO lines, load targets

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core-module
Depends on: S1 (merged, 485f3b4); W0-B2 and the roles MVP (on the trunk); skeleton package at 2aef8fb
Branch: `p2/i3-s2-package`

## Goal
After this piece `tl-mod-materials` is a working module on the ADR-0010 seam: it loads by entry point, every
materials event projects (all eight record types and the stock, reservation and movement tables), the library,
location tree and PO-line commands work, the three load targets are listed by `tl load targets`, and `mto.py`
exposes the stubs S4 fills. Receipts, movements, actions (S3) and MTO publishing (S4) are not here, but their
events already project, so S3/S4 only append events.

## Brief references
`docs/build-spec/specs/m4-materials.md` §2 (types, projections, rules), §3 (commands, words; rows of S2 only),
§5 (views, imports), §9 row S2. `docs/adr/0022-inventory-movements-as-events.md`. S1 report
`docs/reports/P2-I3/S1.md` (read "Deviations" and "Open questions"): S1 added `scope` to projection tables and receipt
lines, `row_id` on `cur_materials_receipt_line`, `last_seq` on records, unique indexes in place of composite keys on
`cur_materials_stock` and `cur_materials_reservation`. Table names: `cur_materials_{item_master,project_item,location,
po_line,receipt,receipt_line,lot,mto,mto_line,movement,stock,reservation}`; code lists in
`schema/fixtures/standards/co.acme.materials@1.0.0.yaml` (uom list is `StockUom`, not `UnitOfMeasure`).

**Decisions (override the spec where they differ; orchestrator, 2026-11-01)**
1. *`available`* is a stored column of `cur_materials_stock`. The stock projector writes `available = on_hand - reserved`
   in the same write as both.
2. *Decimal everywhere.* Quantity columns are NUMERIC (REAL on SQLite). Projectors and handlers never use SQL arithmetic
   (`on_hand + :delta`): read the row with `Decimal(str(x))`, compute in `Decimal`, quantize to 3 places, write the computed
   value. The never-negative checks (retire-with-stock here, S3's movements later) are Decimal comparisons. Bind
   as `projectors/cost_code.py` binds amounts. Event quantities are text (`"12.500"`).
3. *Zero rows.* A stock row with `on_hand = 0` and `reserved = 0`, and a reservation row at `qty = 0`, are deleted by
   the projector in the same write.
4. *`RecordPoLine`* takes `{po_number, line_no, item_code, qty_ordered, uom, promised_date?, supplier_text?}`. When the
   project has no `ProjectItem` for `item_code` it adopts it in the same unit of work (module-written, `by_module=True`,
   source `rule`; the library item must exist and not be retired; `uom` must equal its `base_uom`). Key `<po>-<line>`.
5. *Tree rules.* One root per project (kind `project`, no parent); a second root is refused. `DefineLocation` needs an active
   parent in the same project, `depth = parent depth + 1` and `<= 5`. `ReviseLocation` changes title and kind only (no
   re-parenting). `RetireLocation` is refused while any stock row at the location is not zero (Decimal) or an active child exists.
6. *Company scope.* `ItemMaster` is a company-scope record (key = `code`, unique per company). `ReviseItem` makes
   `ProjectItem.category/uom/consumable` follow in every project (the ItemMaster projector updates the copies), and
   `base_uom` cannot change once any `ProjectItem` or lot uses it.

## Interfaces (what S3, S4, T01b and the tickets import; keep these names)
- Package `tl_mod_materials` (`src/` exists; add to it): `names.py` (type, table, event and relation constants, as
  `tl_mod_cost/names.py`), `limits.py` (every bound of §2), `errors.py`, `common.py`, `module.py:spec()`
  (`ModuleSpec` with `company_roles=True`, `offline_drafts={"materials.StockLot": frozenset({"IssueStock", "TransferStock",
  "ReturnStock"})}`, `command_words` from `MATERIALS_COMMANDS`, `generic_commands` per §3 last paragraph, none for `proposable`
  yet), `projectors/` (one module per record type plus `stock.py` for movement, stock and reservation), `handlers/{items,
  locations,po_lines}.py`, `views.py`, `targets.py`.
- `commands.py`: `MATERIALS_COMMANDS: tuple[CommandSpec, ...]` = the nine S2 commands (`DefineItem`, `ReviseItem`,
  `RetireItem`, `AdoptItem`, `DefineLocation`, `ReviseLocation`, `RetireLocation`, `RecordPoLine`, `UpdatePoLine`) `+ MTO_COMMANDS`;
  S3 appends its own commands in a later piece (do not create `actions.py` or a receipts/movements handler).
  Words are rows of `schema/settings/access-words.yaml` (`materials.library.edit`, `.item.adopt`, `.location.configure`,
  `.po.edit`); none is invented here.
- `mto.py`: `MTO_COMMANDS: tuple[CommandSpec, ...] = ()`, `MTO_RULES: tuple[()] = ()`. S4 owns this file and `handlers/mto.py` afterwards.
- `views.py` (viewer-filtered, default viewer lowest clearance, class filter before LIMIT and count; copy `tl_mod_cost/views.py`):
  `items(conn, *, project=None, viewer=...)`, `locations_tree`, `po_lines(conn, scope, q=)`, `stock(conn, scope, *, lot=, location=,
  item=, heat=, subtree=)`, `lot_detail`, `movements(conn, scope, *, lot=, since=, until=, kind=)`. S3 adds `receipts`, `receipt_detail`,
  `mto_lines`, `reservations_for_iwp`, `mto_lines_for`; leave them out.
- Entry points in the package `pyproject.toml`: `throughline.modules` `materials = "tl_mod_materials.module:spec"`;
  `throughline.load_targets` `materials_item_master` (scope `company`), `materials_location`, `materials_po_line` (scope `project`),
  via the generic column-mapping form of W0-B2; each column mapping plans through the command above, so the loader and
  the command share one check. Loaders (`mat-items` ...) are T01b's, not here.
- Projection semantics S3/S4 rely on (events from S1 `events.yaml`; `StockLot.Moved.kind`):
  receive `+to`; issue `-from`, consuming the reservation of `mto_line_id` first (reservation and `stock.reserved` fall by the part consumed;
  `mto_line.issued_qty +`, `lot.issued_net +`); return `+to`, `issued_net -`; transfer `-from +to` (reserved stays); adjust by `direction`; scrap `-from`;
  reserve `+reserved`, reservation row `+`, `mto_line.reserved_qty +`; unreserve the inverse. `Receipt.Accepted` sets `receipt_line.lot_id`
  and adds the lines' `qty` to `po_line.qty_received` (a Void after Accepted is S3's). One `cur_materials_movement` row per `Moved`, `seq` = event seq.

## Context (<= 10 files)
- the Brief references above; `packages/tl-modules/cost/src/tl_mod_cost/{module.py,names.py,commands.py,views.py,projectors/cost_code.py}` (form to copy)
- `packages/tl-modules/legacy/src/tl_mod_legacy/{model.py,targets.py}` and `legacy/pyproject.toml` (target protocol and entry points)
- `packages/tl-core/src/tl_core/modules.py` (`ModuleSpec`); `schema/modules/materials/*.yaml` (payloads, columns)
may explore: `packages/tl-modules/legacy/tests/test_load_targets.py`, `dev/accept/P2-W0/*.py` (form of an acceptance script)

## Allowed paths
- `packages/tl-modules/materials/**` except `tests/` (create; `pyproject.toml` already there: add entry points only)
- root `pyproject.toml` (`[tool.pyright] extraPaths`: `packages/tl-modules/materials/tests`, one line), `uv.lock` (`uv lock`)
- `packages/tl-cli/pyproject.toml`, `packages/tl-api/pyproject.toml` (`"tl-mod-materials",` in `dependencies`, as `tl-mod-cost`; nothing else)
- Consequential pins only, listed in the report: tests that enumerate installed modules, entry points or record types (grep `tl_mod_cost` in `tests/` and `packages/*/tests/`)
- `dev/accept/P2-I3/S2.py` (create), `docs/reports/P2-I3/S2.md` (create)
Not here: `schema/**`, `generated/**`, `tl_api/{auth,app,commands}.py`, `openapi.json`, `actions.py`, MTO or receipt handlers.

## Acceptance (run once; no pytest; tests are T11's)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
uv run python dev/accept/P2-I3/S2.py
uv run tl load targets
just gate <the test dirs of the pins you changed, plus packages/tl-modules/legacy>
```
`S2.py` (SQLite temp ledger, then `TL_PG_URL` when set; exit 0; one `PASS <check>` each; written from §2, not from your code):
module loads with `company_roles`; `DefineItem` (company) then `AdoptItem` then `ReviseItem` updates the copy; retired item refused for adopt;
locations: depth 5 allowed, 6 refused, second root refused, retire refused with stock `0.001` and allowed at zero; `RecordPoLine` auto-adopts and
checks uom, `UpdatePoLine` changes qty; replay: append by hand (ledger API) a `Receipt.Accepted`, `StockLot.Defined`, `Moved` receive 12.500,
reserve 4.000, issue 3.000 with the line, transfer 2.000, then assert stock, `available`, reservation, movement and `mto_line` rows, `Decimal` exact
(0.1 + 0.2 style sum: three moves of `0.100` give `0.300`), zero rows deleted; `rebuild-projections` gives identical rows; `tl load targets` shows the
three targets with scope `company` for `materials_item_master`; a non-member (viewer clearance) read of a record hidden by class returns nothing.

## Tests to add
None (deferred to T11: `test_items.py`, `test_locations.py`, `test_targets.py`, `test_projection_rebuild.py`).

## Mutation guards (sentinel + at most 5; report in 3 lines)
Depth bound (5 to 6); retire-with-stock check removed; company-scope target set to `project`; `available` written as `on_hand`; zero-row delete removed.
Name each guard's file:line in the report for T11.

## Report requirements
Piece report (<= 60 lines): deviations first; pins changed; acceptance output (<= 5 lines per command); builder return <= 15 lines.
Do not discuss the commit attribution lines. No model names in any committed file. Commit subjects `P2-I3-S2: ...`.

## Escalation triggers
Stop and write *Blocked* if: a column of S1 cannot hold a value the projector needs; W0-B2's generic mapping cannot do a company target;
the roles MVP rejects `company_roles`; a core (`tl_core`) change is needed; a pin outside the listed kinds breaks.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
