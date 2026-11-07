# ADR-0022 — Inventory movements are events on the stock-lot stream

Status: accepted (2026-11-01, orchestrator under P2-Q10; owner accepted the recommendation P2-Q5 B on 2026-10-30)
Date: 2026-11-01
Deciders: repository owner (P2-Q5, `module-designs/OWNER-DECISIONS-2026-10-30.md`); orchestrator (acceptance)
Brief sections: §9 M4 (deviation recorded here), §22.4 (quantities as deltas)
Amends: nothing. Applies the ADR-0010 module seam to M4.

## Context
Brief §9 M4 lists `InventoryTransaction` as a record type with cross-references to the lot, requisition, IWP, cost
code and person. On the ADR-0010 seam every record is a `cur_core_record` row, a feed card and a linkable node; a
Postgres record write is about 17 statements, and a site posts thousands of movements a week (toolcrib, issue to
foremen, returns, transfers). One record and two links per movement would cost write time, feed noise and core-table
growth for something nobody threads, links to or opens on its own.

## Decision
1. **Lots, receipts, requisitions and locations are records** (`materials.*` types, `cur_core_record`, links,
   threads, feed cards per their feed policy).
2. **A movement is an event on the stock lot's stream**: received, issued, transferred, returned, adjusted, disposed.
   Each carries a signed quantity delta, the unit, the from and to locations and typed references (`iwp_id`,
   `requisition_id`, `cost_code_id`, `person`, `receipt_id`, reason code).
3. **Movements are projected** into `cur_materials_movement` (one row per event) and the lot's on-hand balance per
   location. The movement log and the query language read those columns; `linked:` filters see lots and receipts,
   not movements.
4. **Stock never goes negative** (owner answer 16): the handler checks the lot's balance at the location inside the
   command's transaction, with the stream's expected version.
5. **Offline**: issue, transfer and return are `draft_only` (owner answer 17), posted on sync as commands, never as
   accepted events; receipts follow the offline table of the materials spec.

## Consequences
- Cheap writes: one event and one or two projection rows per movement; no feed card.
- A movement has no thread and is not a link target. A question about a movement is asked on the lot, the receipt or
  the requisition.
- The lake and reports read movements from the projection; the brief's cross-references are typed columns, so
  they are queryable without links.
- Replay rebuilds balances from the lot streams; the Phase 3 merge policy for movements is `delta` (quantities add),
  which this shape makes natural.
