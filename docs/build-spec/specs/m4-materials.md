# Spec — M4 materials, first increment: item library, locations, receipts, ledgered stock, MTO, reservations (P2-I3)

Status: v0.1, 2026-10-30, spec for builders and implementers. Design: `module-designs/materials.md`. Plan:
`08-phase2-plan.md` I3 (wave 1, alternating with P2-I1; I3 owns the registries and merges last). Owner decisions:
`module-designs/OWNER-DECISIONS-2026-10-30.md`. Depends on: Phase 2 wave 0 (W0-B1: frozen readiness contract
`tl_core/readiness/types.py`, reserved prefixes, the `materials.*` keys in `platform.yaml`, R-P2-3 fix); **P2-I1 S1**
(load targets by entry point, incl. company-scope targets; `specs/m3-wbs-cwp.md` §10); an ADR (next free number,
0021 at the time of writing; written by the orchestrator before C1) recording P2-Q5 option B, movements as events;
the core specs **roles**, **offline**, **web** written beside this one. Contracts used: `phase2-contracts-draft.md`
§1 (readiness check), §4 (movements API), §6 (`MaterialsDesk`), §7.

## 1. Objective and user stories

The `materials` module on the ADR-0010 seam: a company item library, project items, a location tree, PO-line
mirrors, receipts with heat numbers and MTRs, stock as the projection of movement events, MTO lines published from
derived documents, reservations against MTO lines, and the `materials_reserved` readiness check. Out of scope:
toolcrib screen, `SerializedItem` and `Equipment` (P2-I4-B), `CatalogItem` (supplier part numbers, with P2-Q4 B),
receiving inspection and NCR links (Phase 3), UOM conversion (later), vendor guest links (Phase 3).
- **Materials coordinator (materials user):** I receive a delivery against a PO line, type the heat number, attach
  the MTR, and once I accept it the stock is on hand at the laydown.
- **Workface planner (materials user):** I reserve the MTO lines of a work package from lots in stock and see which
  lines are short.
- **Foreman (materials user):** material is issued to my crew against a cost code; what comes back is returned.
- **Materials superuser:** I set up the location tree, adjust a count with a reason, scrap damaged stock, publish
  MTOs. **Admin:** I load the company item library.
- **QC and cost controller (viewer):** I trace a heat number to its MTR and see consumables by cost code.

## 2. Record types

Confidentiality `internal` for all; no `ConfidentialSource`; MTR files are internal. Schema
`schema/modules/materials/{module,item,location,po_line,receipt,lot,mto,movement,events}.yaml`. Quantities: text
in events (`"12.500"`), `Decimal` in Python, `> 0`, at most 3 decimals, `≤ 1 000 000 000`, ASCII digits only; UOM
from `UnitOfMeasure` (co.acme.standards); one UOM per item, no conversion.

| Type | Scope, key | Typed fields (table) | States | Offline (reason) |
|---|---|---|---|---|
| `materials.ItemMaster` | `company`; typed `code` `^[A-Z0-9][A-Z0-9._\-]{0,39}$` | `cur_materials_item_master`: `code`, `category` (`ItemCategory`), `base_uom`, `size_text`, `rating_text`, `material_code` (`MaterialCode`, optional), `consumable` (bool), `retired` | none (Active / Retired flag) | `none`: company library, one steward |
| `materials.ProjectItem` | project; module-built `<code>` | `cur_materials_project_item`: `item_master_id`, copies of `category`, `uom`, `consumable` (the projector follows master revisions) | none | `none`: made centrally by adoption, receipt or publication |
| `materials.InventoryLocation` | project; typed `code` `^[A-Z0-9][A-Z0-9.\-]{0,15}$` | `cur_materials_location`: `code`, `kind` (`LocationKind`: project, warehouse, laydown, toolcrib, gang_box), `parent_id`, `depth` (0..5), `retired` | none | `none`: the tree must stay one tree |
| `materials.POLineRef` | project; typed `<po>-<line>` | `cur_materials_po_line`: `po_number` (≤ 30), `line_no`, `project_item_id`, `qty_ordered`, `uom`, `promised_date`, `supplier_text` (≤ 120); projected `qty_received` | none (mirror) | `none`: mirror of the ERP (P2-Q4 A) |
| `materials.Receipt` | project; allocator `P123-RCPT-0031` (`{project}-{type}-{seq:4}`, `type_code: RCPT`, gap-free) | `cur_materials_receipt`: `po_line_id`, `supplier_text`, `delivery_ref` (≤ 60), `received_on`, `location_id`, `inspected_by`, `inspected_on`, `decided_by`, `decided_on`, `rejection_reason`; child `cur_materials_receipt_line`: `receipt_id`, `line_no` (1..50), `project_item_id`, `qty`, `uom`, `heat_no` (`^[A-Za-z0-9][A-Za-z0-9./\-]{0,39}$` or null), `condition` (`ConditionCode`), `serials_text` (≤ 2 000), `lot_id` (set at Accept) | workflow `materials-receipt.yaml` | `draft_only`: a remote laydown can capture a draft receipt with photos; number and Accept (which creates stock) are central until reserved ranges exist (Phase 3) |
| `materials.StockLot` | project; module-built `P123-RCPT-0031@1` (receipt @ line) | `cur_materials_lot`: `project_item_id`, `heat_no`, `receipt_id`, `receipt_line`, `uom`; projected `issued_net` (Σ issue − Σ return) | none | `none` for the record; movement offline classes below |
| `materials.MTO` | project; module-built `ISO-1234@A/MTO` | `cur_materials_mto`: `derived_document_id`, `revision_id`, `line_count` | none | `none`: published on the server |
| `materials.MTOLine` | project; module-built `ISO-1234@A/MTO/001` | `cur_materials_mto_line`: `mto_id`, `line_no`, `project_item_id`, `qty`, `uom`, `tag_id` (null), `work_package_id` (an `awp.CWP` or `awp.IWP` id, checked by type string; no import of awp); projected `reserved_qty`, `issued_qty` | none | `none` |

Projection tables (non-record classes, generated DDL): `cur_materials_movement` (one row per movement event: `seq`,
`lot_id`, `kind`, `qty`, `uom`, `direction`, `from_location_id`, `to_location_id`, `cost_code_id`, `mto_line_id`,
`iwp_id`, `requisition_id`, `person`, `reason`, `actor`, `recorded_at`, `correlation_id`); `cur_materials_stock`
(`lot_id`, `location_id`, `on_hand`, `reserved`; available = on_hand − reserved, a view column);
`cur_materials_reservation` (`lot_id`, `location_id`, `mto_line_id`, `qty`). Rows at zero are deleted.

**Movements are events, not records** (P2-Q5 B, contracts T-5): one event type `StockLot.Moved` on the lot's stream,
`kind ∈ receive | issue | transfer | return | adjust | scrap | reserve | unreserve`. Offline class per kind
(proposed; needs the offline spec to allow a class per command for event-only kinds, else StockLot stays `none`
and P2-I4-B re-asks): issue, transfer, return `full` (deltas commute; a merge that would drive a balance negative
goes to the Phase 3 conflict screen, not a refusal); receive, adjust, scrap, reserve, unreserve `none` (stock
enters only by an accepted receipt; the rest feed readiness or need a superuser).

**Receipt workflow** (`schema/fixtures/workflows/materials-receipt.yaml`, no `roles` guard, module commands only):
Received → Inspected → Accepted | Rejected; Received → Rejected; Received, Inspected → Void. File slots
(`schema/fixtures/files/materials-receipt.yaml`): `mtr` (many; PDF and images; 50 MB), `certificate`,
`packing_slip`, `photo` (`capture_hint: camera`); no `required_in_states` (the MTR rule is conditional, below).
`expected_links` at Accepted: a receiving inspection (`n_a` until Phase 3 quality, P2-Q8 A).

**Rules** (fixed messages naming a line or movement index, never cell text):
- *Accept*: every line's item exists and is not retired; when any line's category is in
  `materials.receipt.mtr_required_categories` (project setting, W0-B1) the `mtr` slot holds an available file, else
  `an MTR is required for <n> lines; attach it in the MTR slot`. In one unit of work: one `StockLot` per line
  (`Record.Created`, `StockLot.Defined`, `by_module`), one `StockLot.Moved` kind `receive` into the receipt's
  location, then `Receipt.Accepted` {lots[{line, lot_id}]} and `Workflow.Transitioned`. Lines change only in Received.
- *Movements* (`post_movements`, contracts §4): a batch of 1..200 of one kind, all or nothing. issue: `from`
  required; `qty ≤ available(lot, from) + reserved(lot, from, mto_line)`; consumes that reservation first;
  `cost_code_id` required when the item is consumable; no `to` (consumed; `person` optional). transfer: `from ≠ to`,
  both active and in the project, `qty ≤ available(lot, from)`. return: `to` required, `qty ≤ issued_net`. adjust:
  `direction in | out`, `reason` required; out `≤ available`. scrap: `qty ≤ available`, `reason` required. reserve:
  `location`, `mto_line_id` required, lot item = line item, `qty ≤ available`, total reserved on the line ≤ its qty;
  `iwp_id` is copied from the line when its work package is an IWP. unreserve: `qty ≤ reserved(lot, loc, line)`.
  **No movement may make a balance negative** (adjust included). Checks read projection rows inside the append's
  unit of work under the ledger writer lock. `uom` must equal the lot's. Events carry `feed_policy: none`.

**Links** (no new relation): MTO `derived_from` the document revision and the derived document; MTOLine `belongs_to`
its MTO and its work package, `references` its tag; Receipt `references` its PO line; StockLot `derived_from` its
receipt; all module-written (`by_module=True`, source `rule` or `import`), kept in step with the typed columns.

## 3. Commands, access words, events

Words are `materials.<area>.<verb>`; the default role column is the data the roles spec seeds. Until that spec is on
the trunk: viewer and user words → today's `user`, superuser words → `admin`. Company-scope words have no module
role yet (roles are per project), so `materials.library.edit` is admin until the roles spec gives company grants.

| Command | Word | Default | Events |
|---|---|---|---|
| `DefineItem`, `ReviseItem`, `RetireItem` {reason} | `materials.library.edit` | admin | `Record.Created`, `ItemMaster.Defined`, `.Revised`, `.Retired` |
| `AdoptItem` {item_code} | `materials.item.adopt` | user | `Record.Created`, `ProjectItem.Defined` |
| `DefineLocation` {code, title, kind, parent_code?}, `ReviseLocation`, `RetireLocation` (refused while stock ≠ 0) | `materials.location.configure` | superuser | `InventoryLocation.Defined`, `.Revised`, `.Retired` |
| `RecordPoLine`, `UpdatePoLine` {promised_date?, qty_ordered?} | `materials.po.edit` | user | `POLineRef.Defined`, `.Updated` |
| `CreateReceipt` {po_line?, supplier_text, delivery_ref?, received_on, location_code, lines[≤ 50]} | `materials.receive` | user | `Numbering.Allocated`, `Record.Created`, `Receipt.Defined` |
| `ReviseReceipt` (Received only), `InspectReceipt` {notes?} | `materials.receive` | user | `Receipt.Revised`; `Receipt.Inspected`, `Workflow.Transitioned` |
| `AcceptReceipt` {expected_version}, `RejectReceipt` {reason} | `materials.receipt.decide` | user | above; `Receipt.Rejected`, `Workflow.Transitioned` |
| `VoidReceipt` {reason} | `materials.void` | superuser | `Record.Voided` |
| `IssueStock`, `TransferStock`, `ReturnStock` {movements[≤ 200]} | `materials.move` | user | `StockLot.Moved` × n |
| `ReserveStock`, `UnreserveStock` {movements[≤ 200]} | `materials.reserve` | user | `StockLot.Moved` × n |
| `AdjustStock`, `ScrapStock` {movements[≤ 200], each with reason} | `materials.adjust` | superuser | `StockLot.Moved` × n |
| `PublishDerivedMto` {derived_document, work_package_number?, skip_existing} | `materials.mto.publish` | superuser | `Record.Created`, `MTO.Defined`, `MTOLine.Defined` × n, `Link.Added`, documents' `Published` |
| `AssignMtoLines` {mto_lines[≤ 500], work_package_number} (refused when a line has reservations) | `materials.mto.assign` | user | `MTOLine.Assigned` |
| all reads | `materials.view` | viewer | — |

Every handler: `require_project`, `require_visible` on each id, `correlated(cmd)`. `post_movements(uow, movements,
*, actor, source, by_module=False)` is the public surface (contracts §4) for P2-I4-A fulfilment; `by_module` skips
the lot type's allow-list, never the access word of the calling command. There is no direct `Receive` command:
stock enters only through `AcceptReceipt` (divergence 3). Compensation of an MTO publication runs through the
documents module's `CompensatePublication` and the `mto` publish target (S4); it refuses when a line has a
reservation or an issue. Proposable: `propose_reservation` → `ReserveStock` (accepting person needs
`materials.reserve`). Generic allow-list: Receipt `{SetPsetValues, AddLink, SuggestLink, AttachFile} ∪ LINK_LIFE`
with guards (uploads only in Received or Inspected, plus `certificate`/`photo` when Accepted; nothing once Rejected
or Void); StockLot, MTO, MTOLine, ProjectItem, POLineRef `{AddLink, SuggestLink} ∪ LINK_LIFE`; ItemMaster and
InventoryLocation none; `TransitionWorkflow`, `UpdateRecord`, `VoidRecord` on nothing. Webhooks: `Receipt.Accepted`,
`Receipt.Rejected`, `StockLot.Moved` (a subscriber filters `kind`; the design's `Stock.Reserved` is `kind: reserve`;
its proposed `Stock.Short` is not added: the readiness result carries shortages).

## 4. Readiness check `materials_reserved` (contracts §1)

Plugin under `throughline.readiness_checks`, `version "1"`, `watches = {materials.StockLot, materials.MTOLine,
materials.Receipt}`. Lines = MTO lines whose `work_package_id` is the IWP. None → `n_a` (`no material take-off lines
on this work package`). A line is covered when `reserved_qty + issued_qty ≥ qty`. All covered → `ok`. Otherwise
`pending` when every short line's item has an open receipt (Received or Inspected) or a PO line promised on or before
`planned_start`, else `blocked`. `resolve_via`: short lines first, then those open receipts, ≤ 50; `count_ok` /
`count_total` = covered / lines. One query per kind of row, no per-line loop. It ships against the frozen contract
and passes `check_readiness_contract`; the IWP engine (P2-I2) finds it by entry point.

## 5. Views, routes, reports, imports

Views (`tl_mod_materials/views.py`, viewer-filtered): `stock(conn, scope, *, lot=, location=, item=, heat=,
subtree=)`, `lot_detail`, `movements(conn, scope, *, lot=, since=, until=, kind=)`, `receipts`, `receipt_detail`,
`items(conn, *, project=None)`, `locations_tree`, `po_lines(conn, scope, q=)`, `mto_lines(conn, scope, *,
work_package=, short_only=)`, `reservations_for_iwp(conn, iwp_id)`, `mto_lines_for(conn, record_id)` (contracts §4).
API GET (`materials.view`): `/projects/{p}/materials/stock`, `/lots/{key:path}`, `/movements`, `/receipts`,
`/receipts/{number}`, `/locations`, `/po-lines`, `/mto-lines`, `/reports/{name}`; `/companies/items`; writes are
`POST /commands/<Name>` from `MATERIALS_COMMANDS`. Every GET joins the confidentiality walking test (five readers).
Reports (`tl mat report`, API, CSV with formula-safe cells): `stock_on_hand`, `movement_log` (period),
`mto_status` (per work package and item: required, received, reserved, issued), `shortages`, `heat_trace` (heat →
lots → receipt → MTR file → locations → issues), `consumables_by_cost_code` (period). Marts are P2-I6
(`mart_materials`; silver adds `cur_materials_movement`, `cur_materials_stock`).
**Imports** through the loader framework (P2-I1 S1), no new parser: targets `materials.item_master` (company scope:
code, description, category, uom, size, rating, material, consumable), `materials.location` (parents first),
`materials.po_line` (P2-Q4 A stub, replacing the plan's derivation `po_lines` kind: divergence 2); loaders
`mat-items`, `mat-locations`, `mat-po-lines`. `tl load` stays admin. **MTO** stays on the derivation pipeline
(ADR-0014): S4 adds publish targets by entry point to the documents module so it never imports materials.

## 6. Allowed actions per state and role (`tl_mod_materials/actions.py`)

One `RULES` table drives offers, `require_state` and the word-equals-access test. Agents are offered nothing.

| Type | States / condition | Label | Command | Word (default) |
|---|---|---|---|---|
| Receipt | Received | Edit; Inspect; Reject | `ReviseReceipt`; `InspectReceipt`; `RejectReceipt` | `materials.receive` (user); `…receipt.decide` (user) |
| Receipt | Inspected, MTR present or not required | Accept | `AcceptReceipt` | `materials.receipt.decide` (user) |
| Receipt | Inspected | Reject | `RejectReceipt` | `materials.receipt.decide` (user) |
| Receipt | Received, Inspected | Void | `VoidReceipt` | `materials.void` (superuser) |
| StockLot | available > 0 at some location | Issue; Transfer; Reserve | `IssueStock`; `TransferStock`; `ReserveStock` | `materials.move`; `…move`; `materials.reserve` (user) |
| StockLot | issued_net > 0 | Return | `ReturnStock` | `materials.move` (user) |
| StockLot | has a reservation | Unreserve | `UnreserveStock` | `materials.reserve` (user) |
| StockLot | on hand > 0 | Adjust; Scrap | `AdjustStock`; `ScrapStock` | `materials.adjust` (superuser) |
| MTOLine | short | Reserve from a lot | `ReserveStock` | `materials.reserve` (user) |
| MTOLine | no reservation | Assign to work package | `AssignMtoLines` | `materials.mto.assign` (user) |
| ItemMaster | Active | Retire; Adopt into this project | `RetireItem`; `AdoptItem` | `materials.library.edit` (admin); `materials.item.adopt` (user) |
| InventoryLocation | Active | Edit; Retire | `ReviseLocation`; `RetireLocation` | `materials.location.configure` (superuser) |

Forms: movement actions take `qty`, and as needed `from`/`to` location (default: the highlighted row's location, a
form default, not logic), cost code, MTO line, reason; Reserve from a lot asks lot and location, qty defaulting to
the line's short figure as the view gives it.

## 7. Logs and record screens (log standard, `tui-layout` skill)

`LogScreen` subclasses opened from the navigation panel ("Materials") and the palette, no F-key. The tables below are
the contract for TUI and web alike (web core spec decides the shared form; web twins as in `m3-wbs-cwp.md` §8).
Stateless rows (stock, movements) have no State column: a lot has no workflow and a movement is not a record.
**Stock by location** (home). Columns: Lot (heat, else lot key), Subject (item description), Location, On hand,
Reserved, Available, UOM (numbers right-aligned; UOM dropped when constant). Keys `/`, `l` location subtree, `i`
item, `h` heat, `z` include zero rows. Panel: `H-7781 · Flange WN 6" 150# A105`; second line `Lot
P123-RCPT-0031@1 · received 2026-10-28`; summary `Laydown L2 · 12 on hand · 4 reserved · 8 available`. Sections:
Quantities (table Location, On hand, Reserved, Available); Reservations (table MTO line, For, Location, Qty; `No
reservations`); Movements (last 10: Date, Kind, Qty, From, To, By, For); Traceability (Receipt, PO line, Heat, MTR
`✓`/`—`); Links (n). Enter opens the lot's record screen (all movements on its History tab).
**Receipt log.** Number, Subject, State, Received, Location, Lines, MTR (`✓`/`—`/`n/a`). Keys `o` open (not
decided), `m` missing MTR. Panel `P123-RCPT-0031 · Flanges from Acme Valves`; `Inspected · since 2026-10-28`; summary
`PO 4471-3 · 2 lines · laydown L2 · heat H-7781`. Sections: Lines (table Line, Item, Qty, UOM, Heat, Condition);
Delivery (Supplier, PO line, Delivery ref, Received on, Received by); Inspection (Inspected by, Inspected on,
Receiving inspection `n/a until quality inspections exist`); Files (MTR first, amber `required to accept` when
missing and required); Timeline.
**Receipt entry form** (`ReceiptEntryScreen`, a form, not a log): PO line (completion from `/po-lines?q=`), Supplier,
Delivery ref, Received on (today), Location; a lines grid (Item code, Qty, UOM shown read-only, Heat, Condition,
Serials) of up to 50; MTR file path. `Ctrl+S` sends `CreateReceipt`, then `AttachFile` slot `mtr`; a failed upload
leaves the receipt and says so in the status line.
**Item library** (company). Number (code), Subject, State (`Active`/`Retired`), Category, UOM, Projects (count among
projects the viewer reads). Panel summary `Flanges · EA · used in 3 projects`; sections Specification (Size, Rating,
Material, Consumable), Projects (table Project, On hand, Reserved).
**Locations.** Number (code), Subject (name indented by depth), Kind, Lots, Lines on hand. Panel summary `Laydown
under P123 › Warehouse 1 · 14 lots`; sections Contents (table Lot, Item, On hand), Children.
**MTO lines and shortages.** Number (line key), Subject (item), For (work package number), Required, Reserved,
Issued, Short, Need by (the work package's planned start; `—` when none). Views `1` all lines, `2` short only.
Panel summary `For P123-CWP-PIP-0001 · short 4 EA · 2 open receipts`; sections Source (MTO, document revision),
Coverage (table Lot, Location, Reserved), Open receipts (table Number, State, Qty).
**Movement log** (read only). Date, Kind, Lot, Item, Qty, From, To, By, For. Keys `k` kind, `p` period. Enter opens
the lot.

## 8. Integration points

Documents: MTR, certificates and photos are files in receipt slots; MTOs come from derived documents of a document
revision (P1-I3 schema `mto`, `target_kind: mto`). Tags: an MTO row that names a tag gives the line `references`
the `engineering.Tag`. Cost: consumable issues carry `cost_code_id` (`cost.CostCode`); `consumables_by_cost_code`
reads them; the cost mirror is never written (ADR-0015 §1, R-P2-9). Schedule: none in this increment. AWP:
`work_package_id` names a CWP or IWP by type string; the readiness check (§4); P2-I2's engine raises the shortage
constraint from a `blocked` result with the lines as `resolve_via`. Requisitions (P2-I4-A): `requisition_id` column
and `post_movements(by_module=True)`. Quality (Phase 3): expected receiving inspection. MCP read tools
`stock_on_hand`, `get_lot`, `heat_trace`, `mto_status`; proposable `propose_reservation`. Threads:
`threads.enabled_types` gains `materials.Receipt`, `materials.StockLot`.

## 9. Pieces and tickets

Every ticket's Allowed paths include its report `docs/reports/P2-I3/<id>.md`. B = builder piece (`review: full`,
sentinel + ≤ 5 targeted mutants on the named guards); H = Haiku ticket.

| ID | Kind | Rev | Depends | Title, Allowed paths | Tests it adds |
|---|---|---|---|---|---|
| S1 | B | full (schema, human gate) | W0-B1, ADR P2-Q5 | LinkML `schema/modules/materials/**`; `schema/fixtures/workflows/materials-receipt.yaml`; `schema/fixtures/files/materials-receipt.yaml`; RCPT line in `schema/fixtures/numbering/patterns.yaml`; `schema/fixtures/standards/co.acme.materials@1.0.0.yaml` (`ItemCategory`, `LocationKind`, `ConditionCode`, `MovementReason`); offline annotations; `just gen` | `packages/tl-schema/tests/test_materials_schema.py`; pinned lists regenerated |
| S2 | B | full | S1, P2-I1 S1 | New package `packages/tl-modules/materials/**` (`module.py`, `names.py`, `limits.py`, `projectors/` incl. stock, reservation, movement and MTO-line quantity columns, `handlers/items.py`, `locations.py`, `po_lines.py`, `targets.py`, `views.py`), root `pyproject.toml` entry points; item, location, PO commands; load targets. Mutants: depth bound, retire with stock, company-scope target | `packages/tl-modules/materials/tests/test_items.py`, `test_locations.py`, `test_targets.py`, `test_projection_rebuild.py` (both adapters, property test) |
| S3 | B | full | S2 | Receipts (`handlers/receipts.py`), `api.py` `post_movements` and movement commands (`handlers/movements.py`), `actions.py`, `commands.py` `MATERIALS_COMMANDS`, proposable, provided tests for T03–T08. Mutants: MTR guard, negative balance, reservation over line qty, consumable cost code, word per row | `…/tests/test_receipts.py`, `test_movements.py` (incl. two concurrent issues on Postgres), `test_actions.py`, `test_api_surface.py` |
| S4 | B | full | S3 | Publish targets by entry point (`throughline.publish_targets`) in `packages/tl-modules/documents/src/tl_mod_documents/derivation/**` (built-ins tags, documents; same shape as load targets), target `mto` and `AssignMtoLines` in materials, compensation refusal rules. Mutants: unknown kind, create-only, compensation with a reservation | `packages/tl-modules/documents/tests/test_publish_targets.py`, `packages/tl-modules/materials/tests/test_mto.py` |
| T01 | H | lite | S1 | Samples (not gated): `packages/tl-modules/materials/src/tl_mod_materials/samples/` item library (50 items), locations, PO lines CSVs; loader mappings `tl_mod_materials/loaders/mappings/` | `…/tests/test_samples.py` (provided) |
| T02 | H | lite | S2, T01 | Loaders `mat-items`, `mat-locations`, `mat-po-lines` (`tl_mod_materials/loaders/*.py`, package entry points) | `…/tests/test_loaders.py` (provided) |
| T03 | H | full | S3, W0-B1 | Readiness check `tl_mod_materials/readiness.py` + entry point (§4) | `…/tests/test_materials_reserved.py` (calls `check_readiness_contract`) |
| T04a | H | full | S3 | API read routes `packages/tl-api/src/tl_api/routes/materials.py`, router line, walk entries | `packages/tl-api/tests/test_api_materials.py`, `test_confidentiality_walk.py` lists |
| T04b | H | full | T04a | `ApiClient` and TUI client methods (`client.py`, `embedded.py`, `remote.py`, fake) | `packages/tl-tui/tests/test_client_materials.py` |
| T05 | H | lite | S4 | CLI `tl mat item\|loc\|po\|receipt\|stock\|lot\|move\|mto\|report` (`packages/tl-cli/src/tl_cli/mat.py`) and `tl_mod_materials/reports.py` | `packages/tl-cli/tests/test_cli_mat.py`, `…/tests/test_reports.py` |
| T06a | H | full | T04b | Stock by location and movement log (`widgets/stock_screen.py`, `widgets/movement_log.py`, `tl_tui/materials_text.py`, `details/materials.py`) | `packages/tl-tui/tests/test_stock_screen.py` (80, 170 cols; plain walk) |
| T06b | H | full | T04b | Receipt log and `ReceiptEntryScreen` (`widgets/receipt_log.py`, `widgets/receipt_entry.py`) | `packages/tl-tui/tests/test_receipt_screens.py` |
| T06c | H | full | T04b | Item library and locations (`widgets/item_library.py`, `widgets/location_tree.py`) | `packages/tl-tui/tests/test_item_library.py` |
| T06d | H | full | T04b, S4 | MTO lines and shortages log (`widgets/mto_log.py`) | `packages/tl-tui/tests/test_mto_log.py` |
| T07 | H | full | T04a | MCP read tools and `propose_reservation` (`packages/tl-mcp/src/tl_mcp/materials_tools.py`) | `packages/tl-mcp/tests/test_materials_tools.py`, MCP walk entries |
| T08 | H | lite | T05 | `MaterialsDesk` (`packages/tl-sim/src/tl_sim/client.py`) and `actors/materials_coordinator.py` | `packages/tl-sim/tests/test_materials_coordinator.py` |
| T09 | H | full | T06a–d, T07, T08 | `dev/demos/P2-I3.sh`, `dev/demos/p2_i3_demo.py` (§10) | the demo |
| T10 | H | lite | T09 | Docs: package `README.md`, `AGENTS.md`, `docs/runbooks/materials.md`, `docs/modules/materials/` | — |

Totals: **4 pieces, 15 tickets**; over 10 tickets, so the plan check (skill rule 8) runs before dispatch.
Checkpoints: C1 = S1, S2; C2 = S3, S4, T04a–b; C3 = all tickets; C4 = T09 green on both adapters, SR1 closed.
Registry glue (`MATERIALS_COMMANDS` splat, `add_typer`, `MCP_ACTIONS`, nav entry) by the supervisor; I3 merges last
in wave 1 and regenerates the pinned lists.

## 10. Demo clauses (`just demo P2-I3`, SQLite then Postgres, one PASS each)

1. An admin loads `co.acme.materials@1.0.0` (twice: no change) and the 50-item library with `tl load --company`
(plan, load, reconcile 0 mismatches); a user's `DefineItem` is refused. 2. A superuser loads the location tree
project → warehouse → laydown L2 → toolcrib → gang box; a user's `DefineLocation` is refused. 3. A receipt of two
flange lines, heat `H-7781`, against PO line `4471-3`; Accept without the MTR is refused with the fixed message;
with it, two lots are on hand at L2. 4. Issue to a crew against a cost code (a consumable without one is refused),
transfer, return one, a superuser adjust with a reason; a user's adjust and an over-issue are refused; stock equals
the sum of movements and a rebuild gives the same rows. 5. `heat_trace H-7781` shows lots, receipt, MTR, locations,
issues. 6. A derived `mto` document is published into an MTO for `P123-CWP-PIP-0001` (P2-I1 on the trunk, else no
work package); compensation removes it; republished. 7. A reservation against an MTO line; over-reserving is
refused; `shortages` lists the rest; the `materials_reserved` check passes its contract test and, with P2-I2 on the
trunk, turns `ok`. 8. API, TUI (stock, receipts, MTO lines at 170 columns) and MCP agree; an agent's
`propose_reservation` waits for a person. 9. A quantity with a non-ASCII digit, a negative, 4 decimals or over the
bound is refused with a fixed message.

## 11. Divergences, risks, owner questions

Divergences from the plan and contracts: (1) roles as access words with default roles; adjust, scrap, locations and
MTO publication are materials **superuser** (owner decision 1; P2-Q3 A superseded), the library admin. (2) Item, location and
PO-line imports through loader targets, not module readers or a derivation `po_lines` kind. (3) No `Receive`
command: stock enters only through an accepted receipt. (4) No negative balance, adjust included (contracts §4
allowed an admin adjust below zero). (5) Reservations name an MTO line; `iwp_id` is optional and copied (contracts:
required), because P2-I3 runs before IWPs exist. (6) Deferred from plan T02: `CatalogItem`, `SerializedItem`,
`Equipment`, company aggregation views (to P2-I4-B or later). (7) One UOM per item, no registry conversion.
(8) MTO publication needs publish targets by entry point in documents (S4), since documents must not import materials.
Risks: R-P2-7 stock correctness (property-tested rebuild, concurrent-issue test); R-P2-4 pinned lists and four new
record tables; S4 and P2-I1 S1 change two Phase 1 packages (run the documents, legacy and P1-I3/P1-I8 demos);
R-P2-16 feed noise (`feed_policy: none`); `phase2-owner-questions.md` says its answers become ADR-0016, a number now
taken: the Phase 2 decisions ADR and the P2-Q5 ADR take the next free numbers.
Owner questions: Q-M4-1 who keeps the company item library: admin (proposed) or a company-scope materials superuser
(the roles spec must then allow company grants)? Q-M4-2 is accepting a receipt a `user` act (proposed) or does it
need a superuser or QC word? Q-M4-3 confirm no negative stock, even by adjust. Q-M4-4 may issue, transfer and return
be captured offline (`full`, proposed) once replicas exist? Q-M4-5 confirm deferring `SerializedItem`, `Equipment`
and `CatalogItem` to P2-I4-B or later.
