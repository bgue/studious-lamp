# P2-I3-S1 — Materials schema: eight record types, projections, events, fixtures, standards edition

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: schema
Depends on: Phase 2 wave 0 (on the trunk); ADR-0022 (movements as events, P2-Q5 B; orchestrator drafts it, read it if it exists)
Branch: `p2/i3-s1-schema`
Approver (schema): the orchestrator under P2-Q10 (line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the `materials` module exists as LinkML on the ADR-0010 seam: eight record types with their offline
classes, the projection tables (movement, stock, reservation, receipt line), the event payload classes, the receipt
workflow and file-slot fixtures, the `RCPT` numbering pattern and the standards edition `co.acme.materials@1.0.0`.
`just gen` output is committed and the pinned lists agree. No Python package yet (S2).

## Brief references
`docs/build-spec/specs/m4-materials.md` **§2 (types, projections, movement events, workflow, rules), §3 (the events
column), §9 row S1**: read §2 and §3 in full; they are authoritative except for the decisions below. Analogs to copy
the form from: `schema/modules/cost/*.yaml` (module, current-state classes, events), `schema/modules/documents/revision.yaml`
(workflow, file slots, links), `schema/fixtures/workflows/documents-revision.yaml`, `schema/fixtures/files/documents-revision.yaml`,
`schema/fixtures/standards/co.acme.documents@1.0.0.yaml`, the `documents.Transmittal` row of `schema/fixtures/numbering/patterns.yaml`.

**Decisions (override the spec where they differ)**
1. *Code lists* in `schema/fixtures/standards/co.acme.materials@1.0.0.yaml` (title, owner, `effective_from` as in the
   documents edition). `ItemCategory` (extensible): `pipe fitting flange valve bolting structural plate cable instrument
   electrical insulation paint consumable concrete other`. `LocationKind` (closed): `project warehouse laydown toolcrib
   gang_box`. `ConditionCode` (closed): `good damaged wrong_item nonconforming`. `MovementReason` (extensible):
   `count_correction damaged lost found wrong_item expired other`. Labels are plain English, one line each.
2. *Unit of measure (divergence D2).* `co.acme.standards` `UnitOfMeasure` is closed and has no `EA`. Add a fifth list
   `StockUom` (closed) to the materials edition: `EA SET BOX ROLL L m kg lb m3`, each with `attributes: {ucum: ...,
   dimension: ...}` as `UnitOfMeasure` does (`EA` ucum `1`, dimension count). `uom` / `base_uom` columns use `StockUom`,
   never `UnitOfMeasure`. Do not edit `co.acme.standards@1.0.0.yaml`.
3. *Pin of record keys.* Typed key columns carry the regexes of §2 as LinkML `pattern`; quantities are text in events
   (`"12.500"`) and `Decimal`-compatible columns in tables (store as text with a `pattern` of at most 3 decimals if the
   generator has no decimal type; copy what `cost.CostCode` does for amounts).
4. *Events.* One payload class per event of §3 (list below). `StockLot.Moved` is the single movement event, `kind` one of
   `receive issue transfer return adjust scrap reserve unreserve`; every materials event of `StockLot.Moved` carries
   `feed_policy: none` (copy the form from `schema/modules/correspondence/events.yaml`). Webhook-visible types
   (`Receipt.Accepted`, `Receipt.Rejected`, `StockLot.Moved`) need no extra schema.
5. *Offline classes* exactly as the §2 table: `ItemMaster`, `ProjectItem`, `InventoryLocation`, `POLineRef`, `MTO`,
   `MTOLine` `none`; `Receipt` and `StockLot` `draft_only`. Add the one-line reason in the class description.
6. *Out of scope:* `CatalogItem`, `SerializedItem`, `Equipment`, UOM conversion, `mart_*` tables, any Python.

| Event (stream type) | Payload fields |
|---|---|
| `ItemMaster.Defined` / `.Revised` / `.Retired` (`materials.ItemMaster`) | code, category, base_uom, size_text, rating_text, material_code, consumable; Revised: the same, all optional; Retired: reason |
| `ProjectItem.Defined` | item_master_id, code, category, uom, consumable |
| `InventoryLocation.Defined` / `.Revised` / `.Retired` | code, kind, parent_id, depth; Revised: title?, kind?; Retired: reason |
| `POLineRef.Defined` / `.Updated` | po_number, line_no, project_item_id, qty_ordered, uom, promised_date, supplier_text; Updated: promised_date?, qty_ordered? |
| `Receipt.Defined` / `.Revised` | po_line_id, supplier_text, delivery_ref, received_on, location_id, lines[line_no, project_item_id, qty, uom, heat_no, condition, serials_text]; Revised: all optional |
| `Receipt.Inspected` / `.Accepted` / `.Rejected` | inspected_by, inspected_on, notes?; decided_by, decided_on, lots[line, lot_id]; decided_by, decided_on, reason |
| `StockLot.Defined` / `.Moved` | project_item_id, heat_no, receipt_id, receipt_line, uom; Moved: kind, qty, uom, direction?, from_location_id?, to_location_id?, cost_code_id?, mto_line_id?, iwp_id?, requisition_id?, person?, reason? |
| `MTO.Defined`; `MTOLine.Defined` / `.Assigned` | derived_document_id, revision_id, line_count; mto_id, line_no, project_item_id, qty, uom, tag_id?, work_package_id?; Assigned: work_package_id |

## Interfaces (what S2 and later pieces import; keep these names)
- Record types `materials.ItemMaster`, `ProjectItem`, `InventoryLocation`, `POLineRef`, `Receipt`, `StockLot`, `MTO`,
  `MTOLine`; tables `cur_materials_{item_master,project_item,location,po_line,receipt,receipt_line,lot,mto,mto_line}`
  and the non-record `cur_materials_{movement,stock,reservation}` with the columns of §2 (`available` a view column of
  `cur_materials_stock`; rows at zero are deleted by the projector, not by schema).
- Generated: `tl_schema.generated.offline_classes.OFFLINE_CLASSES` holds the eight types; `OFFLINE_STREAMS` follows the OC-S1 rule for `StockLot`.
- Workflow `materials-receipt.yaml`: Received -> Inspected -> Accepted | Rejected; Received -> Rejected; Received,
  Inspected -> Void; no `roles` guard. File slots `mtr` (many; PDF and images; 50 MB), `certificate`, `packing_slip`,
  `photo` (`capture_hint: camera`); `expected_links` at Accepted: receiving inspection, `n_a` until Phase 3.
- Numbering: `materials.Receipt`, `{project}-{type}-{seq:4}`, `type_code: RCPT`, `gap_free: true`.

## Context (<= 10 files)
- `docs/build-spec/specs/m4-materials.md` §2, §3; `docs/build-spec/specs/offline-classes.md` §2-§5 (annotation and generator rules)
- `schema/modules/cost/{module,cost_code,events}.yaml`; `schema/modules/documents/revision.yaml`
- `schema/fixtures/{workflows/documents-revision.yaml,files/documents-revision.yaml,standards/co.acme.documents@1.0.0.yaml,numbering/patterns.yaml}`
- `dev/accept/P2-W0/OC-S1.py` (the form of an acceptance script; `EXPECTED_RECORDS` is the pin you extend)
may explore: `packages/tl-schema/tests/{test_ddl.py,test_generate.py,test_offline_classes.py,test_registry_pins.py}`

## Allowed paths
- `schema/modules/materials/{module,item,location,po_line,receipt,lot,mto,movement,events}.yaml` (create)
- `schema/fixtures/workflows/materials-receipt.yaml`, `schema/fixtures/files/materials-receipt.yaml` (create)
- `schema/fixtures/numbering/patterns.yaml` (the RCPT entry only), `schema/fixtures/standards/co.acme.materials@1.0.0.yaml` (create)
- `packages/tl-schema/src/tl_schema/generated/**` (only by `just gen`; commit the output)
- Pinned lists, consequential pins only, listed in the report: `packages/tl-schema/tests/{test_ddl.py,test_generate.py,test_offline_classes.py,test_registry_pins.py}`
- `dev/accept/P2-I3/S1.py` (create), `docs/reports/P2-I3/S1.md` (create)

## Acceptance (run these once; no pytest, tests are deferred to T11)
```
just gen
just check
uv run python dev/accept/P2-I3/S1.py
```
`S1.py` (SQLite, temp ledger, exit 0, one `PASS <check>` per check, written from §2 not from the generated files)
proves: the eight types are in `OFFLINE_CLASSES` with the classes of decision 5, `StockLot` `draft_only`; the nine
record tables, the three projection tables and `available` exist in the generated DDL; every payload class of the event
table exists with its stream type; the edition loads twice with no change on the second load and the five lists hold the
values of decisions 1-2; `materials.Receipt` allocates `P123-RCPT-0001` then `-0002` through the numbering config; the
workflow fixture loads and refuses Accepted -> Inspected; the file-slot fixture lists the four slots.

## Tests to add
None (owner: tests deferred). T11 writes `packages/tl-schema/tests/test_materials_schema.py`. Update only the pinned lists.

## Mutation guards (run by T11, named so the schema is killable)
A type missing from `OFFLINE_CLASSES`; `StockLot` not `draft_only`; `StockUom` accepting a value outside the list; a
movement `kind` outside the eight; the RCPT pattern not gap-free. Report in 3 lines which guard sits where (file:line).

## Report requirements
Piece report (<= 60 lines): deviations first; pinned-list changes; acceptance output (<= 5 lines per command); candidate
learnings. Do not discuss the commit attribution lines. No model names in any committed file.

## Escalation triggers
Stop and write *Blocked* if: a core `schema/core/**` change is needed; the generator cannot express a column of §2; the
edition cannot load twice unchanged; ADR-0022 contradicts decision 4; more than the four named tests need new pins.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
