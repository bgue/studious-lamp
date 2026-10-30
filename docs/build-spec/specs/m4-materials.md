# Spec — M4 materials, first increment: item library, locations, receipts, ledgered stock, MTO, reservations (P2-I3)

Status: v0.2, 2026-10-30, plan check (Code 92, F1–F11) and owner answers 14–18 applied. Design: `module-designs/materials.md`. Plan:
`08-phase2-plan.md` I3 (wave 1, alternating with P2-I1; I3 owns the registries and merges last). Owner decisions:
`module-designs/OWNER-DECISIONS-2026-10-30.md`. Depends on: Phase 2 wave 0, all of it on the trunk before S1
starts (`specs/wave0.md`; plan check F1): W0-B1 (frozen readiness contract `tl_core/readiness/types.py`, `load_checks`,
`check_readiness_contract`, reserved prefixes, the `materials.*` keys, `schema/settings/access-words.yaml`); **W0-B2**
(load and publish targets by entry point, incl. company-scope load targets), which replaces the old dependency on
P2-I1 S1 (plan check F2); the roles MVP (`P2-RM`, with company grants for materials, `wave0.md` §2) and offline classes
(`P2-OC`); ADR-0022 (drafted by the orchestrator in wave 0; 0021 is now the roles ADR) recording P2-Q5 option B,
movements as events. Contracts used: `phase2-contracts-draft.md`
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
| `materials.StockLot` | project; module-built `P123-RCPT-0031@1` (receipt @ line) | `cur_materials_lot`: `project_item_id`, `heat_no`, `receipt_id`, `receipt_line`, `uom`; projected `issued_net` (Σ issue − Σ return) | none | `draft_only`: issue, transfer and return are captured offline as drafts and posted on sync (owner answer 17); see below |
| `materials.MTO` | project; module-built `ISO-1234@A/MTO` | `cur_materials_mto`: `derived_document_id`, `revision_id`, `line_count` | none | `none`: published on the server |
| `materials.MTOLine` | project; module-built `ISO-1234@A/MTO/001` | `cur_materials_mto_line`: `mto_id`, `line_no`, `project_item_id`, `qty`, `uom`, `tag_id` (null), `work_package_id` (an `awp.CWP` or `awp.IWP` id, checked by type string; no import of awp); projected `reserved_qty`, `issued_qty` | none | `none` |

Projection tables (non-record classes, generated DDL): `cur_materials_movement` (one row per movement event: `seq`,
`lot_id`, `kind`, `qty`, `uom`, `direction`, `from_location_id`, `to_location_id`, `cost_code_id`, `mto_line_id`,
`iwp_id`, `requisition_id`, `person`, `reason`, `actor`, `recorded_at`, `correlation_id`); `cur_materials_stock`
(`lot_id`, `location_id`, `on_hand`, `reserved`; available = on_hand − reserved, a view column);
`cur_materials_reservation` (`lot_id`, `location_id`, `mto_line_id`, `qty`). Rows at zero are deleted.

**Movements are events, not records** (P2-Q5 B, contracts T-5): one event type `StockLot.Moved` on the lot's stream,
`kind ∈ receive | issue | transfer | return | adjust | scrap | reserve | unreserve`. Offline (owner answer 17):
`StockLot` is `draft_only` with `offline_drafts = {IssueStock, TransferStock, ReturnStock}` (offline spec §5.3, no
per-kind class needed); a draft is posted on sync through the same checks, and one that would make a balance negative
is refused (owner answer 16) and shown on the Phase 3 conflict screen. Reserve and unreserve are `user` commands not
listed, so they stay online (`not_drafting`); adjust and scrap are `controller`, always central (owner answer 6);
receive happens only inside an accepted receipt.

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

Words are `materials.<area>.<verb>`; the default role column is the data the roles spec seeds. The roles MVP lands in
wave 0, so there is no interim shim: each word is a row of `schema/settings/access-words.yaml` (W0-B1) naming its
role-table word (plan check F1). `materials.library.edit` is held by a **company-level materials superuser**, else an
admin (owner answer 14): the roles MVP allows a grant with project `company` for modules that declare
`ModuleSpec.company_roles` (materials only; `wave0.md` §2).

| Command | Word | Default | Events |
|---|---|---|---|
| `DefineItem`, `ReviseItem`, `RetireItem` {reason} | `materials.library.edit` | company superuser, else admin | `Record.Created`, `ItemMaster.Defined`, `.Revised`, `.Retired` |
| `AdoptItem` {item_code} | `materials.item.adopt` | user | `Record.Created`, `ProjectItem.Defined` |
| `DefineLocation` {code, title, kind, parent_code?}, `ReviseLocation`, `RetireLocation` (refused while stock ≠ 0) | `materials.location.configure` | superuser | `InventoryLocation.Defined`, `.Revised`, `.Retired` |
| `RecordPoLine`, `UpdatePoLine` {promised_date?, qty_ordered?} | `materials.po.edit` | user | `POLineRef.Defined`, `.Updated` |
| `CreateReceipt` {po_line?, supplier_text, delivery_ref?, received_on, location_code, lines[≤ 50]} | `materials.receive` | user | `Numbering.Allocated`, `Record.Created`, `Receipt.Defined` |
| `ReviseReceipt` (Received only), `InspectReceipt` {notes?} | `materials.receive` | user | `Receipt.Revised`; `Receipt.Inspected`, `Workflow.Transitioned` |
| `AcceptReceipt` {expected_version}, `RejectReceipt` {reason} (owner answer 15: any user accepts) | `materials.receipt.decide` | user | above; `Receipt.Rejected`, `Workflow.Transitioned` |
| `VoidReceipt` {reason} | `materials.void` | superuser | `Record.Voided` |
| `IssueStock`, `TransferStock`, `ReturnStock` {movements[≤ 200]} | `materials.move` | user | `StockLot.Moved` × n |
| `ReserveStock`, `UnreserveStock` {movements[≤ 200]} | `materials.reserve` | user | `StockLot.Moved` × n |
| `AdjustStock`, `ScrapStock` {movements[≤ 200], each with reason} (scrap = disposal of damaged or nonconforming items, owner answer 15) | `materials.adjust` | superuser | `StockLot.Moved` × n |
| `PublishDerivedMto` {derived_document, work_package_number?, skip_existing} | `materials.mto.publish` | superuser | `Record.Created`, `MTO.Defined`, `MTOLine.Defined` × n, `Link.Added`, documents' `Published` |
| `AssignMtoLines` {mto_lines[≤ 500], work_package_number} (refused when a line has reservations) | `materials.mto.assign` | user | `MTOLine.Assigned` |
| all reads | `materials.view` | viewer | — |

Every handler: `require_project`, `require_visible` on each id, `correlated(cmd)`. `post_movements(uow, movements,
*, actor, source, by_module=False)` is the public surface (contracts §4) for P2-I4-A fulfilment; `by_module` skips
the lot type's allow-list, never the access word of the calling command. There is no direct `Receive` command:
stock enters only through `AcceptReceipt` (divergence 3). Compensation of an MTO publication runs through the
documents module's `CompensatePublication` and the `mto` publish target (S4, registered on W0-B2's publish targets); it refuses when a line has a
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
(`mart_materials`; silver adds `cur_materials_movement`, `cur_materials_stock`): out of this increment's scope and
demo (plan check F6).
**Imports** through the loader framework (wave 0 W0-B2), no new parser: targets `materials.item_master` (company scope:
code, description, category, uom, size, rating, material, consumable), `materials.location` (parents first),
`materials.po_line` (P2-Q4 A stub, replacing the plan's derivation `po_lines` kind: divergence 2); loaders
`mat-items`, `mat-locations`, `mat-po-lines`. `tl load` stays admin. **MTO** stays on the derivation pipeline
(ADR-0014): W0-B2 adds publish targets by entry point to the documents module so it never imports materials; S4
registers the `mto` target.

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
| ItemMaster | Active | Retire; Adopt into this project | `RetireItem`; `AdoptItem` | `materials.library.edit` (company superuser, else admin); `materials.item.adopt` (user) |
| InventoryLocation | Active | Edit; Retire | `ReviseLocation`; `RetireLocation` | `materials.location.configure` (superuser) |

Forms: movement actions take `qty`, and as needed `from`/`to` location (default: the highlighted row's location, a
form default, not logic), cost code, MTO line, reason; Reserve from a lot asks lot and location, qty defaulting to
the line's short figure as the view gives it.

## 7. Logs and record screens (log standard, `tui-layout` skill)

`LogScreen` subclasses opened from the navigation panel ("Materials") and the palette, no F-key. The tables below are
the contract for TUI and web alike; web twins are unconditional, one `WebLog` page per log, filed for the first web
increment (P2-WEB1) as in `m3-wbs-cwp.md` §8 (plan check F9).
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
**Receipt entry form** (`ReceiptEntryScreen`, a form, not a log; its own ticket T06e, plan check F4): PO line (completion from `/po-lines?q=`), Supplier,
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

Conventions as `m3-wbs-cwp.md` §10, with `P2-I3` for the increment: B = builder piece (Sonnet, `review: full`), H =
Haiku ticket; Allowed paths include `docs/reports/P2-I3/<id>.md` and `dev/accept/P2-I3/<id>.py`; tests deferred to
**T11** at C3 (plan check F3); S3's acceptance leaves the seed ledger `.accept/p2-i3.db` (library, location tree, two
lots, an MTO); every acceptance starts with `just check` and ends with `just gate <existing dirs touched>`. **Gate**:
schema merges approved by the owner, or the orchestrator where P2-Q10 delegates them. **Sec**: security review rows,
range `<trunk at wave-1 base>..<P2-I3 head>`, run only if the owner asks (plan check F7).

| ID | Kind | Rev | Sec | Depends | Title, Allowed paths | Acceptance commands |
|---|---|---|---|---|---|---|
| S1 | B | full; Gate: owner | Y | wave 0, ADR-0022 | LinkML `schema/modules/materials/**`; `schema/fixtures/workflows/materials-receipt.yaml`; `schema/fixtures/files/materials-receipt.yaml`; RCPT line in `schema/fixtures/numbering/patterns.yaml`; `schema/fixtures/standards/co.acme.materials@1.0.0.yaml` (`ItemCategory`, `LocationKind`, `ConditionCode`, `MovementReason`); `tl:offline` per §2; `just gen`; pinned lists | `uv run python dev/accept/P2-I3/S1.py` (8 types in `OFFLINE_CLASSES`, StockLot `draft_only`; edition loads twice, no change) |
| S2 | B | full | Y | S1, W0-B2 (plan check F2) | New package `packages/tl-modules/materials/**` (`module.py` with `company_roles` and `offline_drafts`, `names.py`, `limits.py`, `projectors/` incl. stock, reservation, movement and MTO-line quantity columns, `handlers/{items,locations,po_lines}.py`, `targets.py`, `views.py`), stubs `mto.py` (`MTO_COMMANDS = ()`, `MTO_RULES = ()`) that `commands.py` and `actions.py` splat, root `pyproject.toml` entry points. Guards: depth bound, retire with stock, company-scope target | `uv run python dev/accept/P2-I3/S2.py`; `uv run tl load targets` lists the three materials targets, `materials.item_master` scope `company` |
| S3 | B | full | Y | S2 | Receipts (`handlers/receipts.py`), `api.py` `post_movements` and movement commands (`handlers/movements.py`), `actions.py`, `commands.py` `MATERIALS_COMMANDS`, proposable; references for T03–T08. Guards: MTR guard, negative balance, reservation over line qty, consumable cost code, word per row | `uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db` (incl. two concurrent issues with `TL_PG_URL`) |
| S4 | B | full | Y | S2; beside S3 (plan check F2) | `mto` publish target on W0-B2's `throughline.publish_targets`, `AssignMtoLines`, compensation refusals; only `tl_mod_materials/mto.py`, `handlers/mto.py` and the package `pyproject.toml` entry point, so S3 and S4 share no file. Guards: create-only, compensation with a reservation or an issue | `uv run python dev/accept/P2-I3/S4.py` (publish, compensate, republish; refusal with a reservation) |
| T01 | H | lite | — | S2 | Samples, mappings and loaders, one ticket (plan check F11): `tl_mod_materials/samples/` (50 items, locations, PO lines CSVs), `loaders/mappings/*`, `loaders/materials.py` (`mat-items`, `mat-locations`, `mat-po-lines`), package entry points | `uv run tl load loaders` lists the three; `tl load open --company …/items.csv` then `plan` reports 50 new |
| T03 | H | full | Y | S3, W0-B1 | Readiness check `tl_mod_materials/readiness.py` and entry point (§4) | `uv run python dev/accept/P2-I3/T03.py` (`check_readiness_contract(load_checks()["materials_reserved"], world)` passes) |
| T04a | H | full | Y | S3 | API read routes `packages/tl-api/src/tl_api/routes/materials.py`, router line, walk-list entries | `uv run python dev/accept/P2-I3/T04a.py`; `just gate packages/tl-api/tests/test_confidentiality_walk.py` |
| T04b | H | full | — | T04a | `ApiClient` and TUI client methods (`client.py`, `embedded.py`, `remote.py`, fake) | `uv run python dev/accept/P2-I3/T04b.py` |
| T05 | H | full (write verbs, plan check F5) | — | S3, S4 | CLI `tl mat item\|loc\|po\|receipt\|stock\|lot\|move\|mto\|report` (`packages/tl-cli/src/tl_cli/mat.py`) and `tl_mod_materials/reports.py` | `uv run tl mat stock --db .accept/p2-i3.db`; `uv run tl mat report heat_trace H-7781 --db .accept/p2-i3.db` |
| T06a | H | full | — | T04b | Stock by location and movement log; shared renderer `details/materials.py` and `tl_tui/materials_text.py` (`widgets/stock_screen.py`, `widgets/movement_log.py`) | `uv run python dev/accept/P2-I3/T06a.py` (80 and 170 columns) |
| T06b | H | full | — | T06a (plan check F4) | Receipt log (`widgets/receipt_log.py`) | `uv run python dev/accept/P2-I3/T06b.py` |
| T06e | H | full | — | T06b (plan check F4) | `ReceiptEntryScreen` split from T06b: 50-row lines grid, `CreateReceipt` then `AttachFile` slot `mtr`, failed-upload status line (`widgets/receipt_entry.py`) | `uv run python dev/accept/P2-I3/T06e.py` (two lines saved, MTR attached) |
| T06c | H | full | — | T06a (plan check F4) | Item library and locations (`widgets/item_library.py`, `widgets/location_tree.py`) | `uv run python dev/accept/P2-I3/T06c.py` |
| T06d | H | full | — | T06a, S4 (plan check F4) | MTO lines and shortages log (`widgets/mto_log.py`) | `uv run python dev/accept/P2-I3/T06d.py` |
| T07 | H | full | Y | T04a | MCP read tools and `propose_reservation` (`packages/tl-mcp/src/tl_mcp/materials_tools.py`), MCP walk entries | `uv run python dev/accept/P2-I3/T07.py`; `just gate packages/tl-mcp` |
| T08 | H | lite | — | T04b, T07 (plan check F8) | `MaterialsDesk` (`packages/tl-sim/src/tl_sim/client.py`) and `actors/materials_coordinator.py` | `uv run python dev/accept/P2-I3/T08.py` |
| T11 | tests (Sonnet) | full | — | S1–S4, T01–T08 | The increment's tests (list below) and the mutants of S2–S4; Allowed: those test paths only | `just gate packages/tl-modules/materials packages/tl-modules/documents packages/tl-api packages/tl-tui packages/tl-mcp packages/tl-cli packages/tl-sim packages/tl-schema`; `just gate-pg packages/tl-modules/materials`; mutation 3 lines |
| T09 | H | full | — | T11, T06a–e, T07, T08; P2-I1 merged (plan check F10) | `dev/demos/P2-I3.sh`, `dev/demos/p2_i3_demo.py` (§10) | `just demo P2-I3` |
| T10 | H | lite | — | T05, T06a–e (plan check F8) | Docs: package `README.md`, `AGENTS.md`, `docs/runbooks/materials.md`, `docs/modules/materials/` | — |

**Tests (T11)**, by origin: S1 `packages/tl-schema/tests/test_materials_schema.py`; S2
`packages/tl-modules/materials/tests/test_items.py`, `test_locations.py`, `test_targets.py`, `test_projection_rebuild.py`
(both adapters, property test); S3 `test_receipts.py`, `test_movements.py` (two concurrent issues on Postgres),
`test_actions.py`, `test_api_surface.py`; S4 `test_mto.py`; T01 `test_samples.py`, `test_loaders.py`; T03
`test_materials_reserved.py` (calls `check_readiness_contract`); T04a `packages/tl-api/tests/test_api_materials.py`;
T04b `packages/tl-tui/tests/test_client_materials.py`; T05 `packages/tl-cli/tests/test_cli_mat.py`, `test_reports.py`;
T06a–e `packages/tl-tui/tests/test_{stock_screen,receipt_screens,item_library,mto_log}.py` (80, 170 columns; plain
walk); T07 `packages/tl-mcp/tests/test_materials_tools.py`; T08 `packages/tl-sim/tests/test_materials_coordinator.py`.

Totals: **4 pieces, 15 tickets** (14 Haiku, T11 Sonnet). Checkpoints: C1 = S1, S2; C2 = S3, S4, T04a–b; C3 = all
tickets (T11 last); C4 = T09 green on both adapters, `just tour` once, security review only if the owner asks.
Registry glue (`MATERIALS_COMMANDS` splat, `add_typer`, `MCP_ACTIONS`, nav entry) by the supervisor; I3 merges last
in wave 1 and regenerates the pinned lists.

## 10. Demo clauses (`just demo P2-I3`, SQLite then Postgres, one PASS each)

1. An admin loads `co.acme.materials@1.0.0` (twice: no change) and the 50-item library with `tl load --company`
(plan, load, reconcile 0 mismatches); a company materials superuser's `DefineItem` is accepted, a project user's is
refused. 2. A superuser loads the location tree
project → warehouse → laydown L2 → toolcrib → gang box; a user's `DefineLocation` is refused. 3. A receipt of two
flange lines, heat `H-7781`, against PO line `4471-3`; Accept without the MTR is refused with the fixed message;
with it, two lots are on hand at L2. 4. Issue to a crew against a cost code (a consumable without one is refused),
transfer, return one, a superuser adjust with a reason; a user's adjust and an over-issue are refused; stock equals
the sum of movements and a rebuild gives the same rows. 5. `heat_trace H-7781` shows lots, receipt, MTR, locations,
issues. 6. A derived `mto` document is published into an MTO for `P123-CWP-PIP-0001` (the driver creates that CWP
through the awp commands; P2-I1 is merged before this demo runs, plan check F10); compensation removes it;
republished. 7. A reservation against an MTO line; over-reserving is refused; `shortages` lists the rest; the
`materials_reserved` check passes `check_readiness_contract` (its `ok` on a real IWP is a P2-I2 demo clause).
8. API, TUI (stock, receipts, MTO lines at 170 columns) and MCP agree; an agent's `propose_reservation` waits for a
person. 9. A quantity with a non-ASCII digit, a negative, 4 decimals or over the bound is refused with a fixed
message. 10. The item library shows the 50 items with project counts, and the locations screen shows the five-level
tree with lot counts, at 170 columns (plan check F6). 11. The movement log lists the clause-4 movements in order with
kind, from, to and by, and filtered by kind `issue` shows one row (plan check F6).

## 11. Divergences, risks, owner answers

Divergences from the plan and contracts: (1) roles as access words with default roles; adjust, scrap, locations and
MTO publication are materials **superuser** (owner decision 1; P2-Q3 A superseded); the library a company materials
superuser, else admin (owner answer 14). (2) Item, location and
PO-line imports through loader targets, not module readers or a derivation `po_lines` kind. (3) No `Receive`
command: stock enters only through an accepted receipt. (4) No negative balance, adjust included (contracts §4
allowed an admin adjust below zero; owner answer 16). (5) Reservations name an MTO line; `iwp_id` is optional and copied (contracts:
required), because P2-I3 runs before IWPs exist. (6) Deferred from plan T02: `CatalogItem`, `SerializedItem`,
`Equipment`, company aggregation views (owner answer 18). (7) One UOM per item, no registry conversion.
(8) MTO publication needs publish targets by entry point in documents, built in wave 0 (W0-B2).
Risks: R-P2-7 stock correctness (property-tested rebuild, concurrent-issue test, both in T11: until then the S3
acceptance script carries them); R-P2-4 pinned lists and four new record tables; R-P2-16 feed noise
(`feed_policy: none`); the Phase 2 decisions ADR takes the number after ADR-0022.
Owner answers applied (`OWNER-DECISIONS-2026-10-30.md`): 14 company item library kept by a company-level materials
superuser, else an admin; 15 any user accepts a receipt, a superuser scraps (disposes of) damaged or nonconforming
items; 16 stock never goes negative; 17 issue, transfer, return `draft_only`, posted on sync; 18 `CatalogItem`,
`SerializedItem`, `Equipment` deferred. Open: whether `RejectReceipt` of a nonconforming delivery is a disposal
(superuser) or a refusal of delivery (`user`, as specified); default `user`.
