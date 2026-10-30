# M4 — Materials management

Brief §9 M4, §10.5 (toolcrib), §12. Plan `08-phase2-plan.md` I3 (module), I4-B (toolcrib screen). Status: design v0.1.

## Users and stories
Materials coordinator, warehouse and toolcrib attendants, foreman (requests, crew issues), QC (receiving inspection,
MTRs), cost controller, company equipment manager, vendor (MTR upload by guest link, Phase 3).
- As a **materials coordinator** I receive a delivery against a PO line, record the heat number and attach the MTR,
  and the stock is on hand at the laydown the moment I accept it.
- As a **workface planner** I reserve the MTO lines of an IWP and see the shortages that block its release.
- As a **toolcrib attendant** I issue a tool to a person and take it back in one keyboard line each.
- As an **equipment manager** I see where every company asset is across projects and what is surplus.

## Records and states
| Record | States |
|---|---|
| `ItemMaster` (company), `CatalogItem` | Active → Retired (admin) |
| `ProjectItem`, `MTO` / `MTOLine` | Published from a derived document; compensable; no workflow |
| `POLineRef` | Mirror: qty, promised date (P2-Q4) |
| `Receipt` | Received → Inspected → Accepted / Rejected; Accept needs the `mtr` slot for permanent materials |
| `StockLot`, `SerializedItem` | No workflow; quantities are the sum of movements on the lot stream (P2-Q5) |
| Movements (events) | Receive, Issue, Transfer, Return, Adjust (admin, reason), Scrap (admin), Reserve, Unreserve |
| `InventoryLocation` | Tree company → warehouse → project → laydown → toolcrib → gang box |
| `Equipment` (asset) | Available → Issued → Out for calibration → Retired **(proposed, small)**; calibration link to M5 |

## Logs and record screens (log standard)
**Stock by location** (home). Columns: Location, Item, Lot or heat, On hand, Reserved, Available, UOM. Filters by
location subtree, item, heat. Panel: identity `H-7781 · Flange WN 6" 150# A105`; summary `Laydown L2 · 12 on hand ·
4 reserved · receipt RCPT-0031`; sections Quantities, Movements (table Date, Kind, Qty, From, To, By, For),
Traceability (receipt, PO line, MTR), Links. Actions: Issue, Transfer, Return, Reserve, Unreserve (`user`);
Adjust, Scrap (admin).
**Receipt log.** Number, Supplier or PO line, State, Received, Location, Lines, MTR (`✓` or `—`). Panel summary
`PO 4471-3 · 2 lines · laydown L2 · heat H-7781`; sections Lines (table Item, Qty, UOM, Heat, Condition),
Inspection (expected link to an M5 receiving inspection, `n/a` until Phase 3), Files (MTR, certificates), Timeline.
Actions: Received: Inspect, Reject; Inspected: Accept (refused without MTR), Reject; any: Open thread.
**Receipt entry form**: PO line lookup, lines with heat numbers, MTR upload in the same form.
**Item library** (company): Code, Description, Class, Category, UOM, Stock (all projects). Actions: Retire (admin);
import from CSV with preview (admin).
**Movement log**: Date, Kind, Item, Qty, From, To, By, For (IWP, cost code, requisition). Read only.
**Reservations and shortages**: IWP, Item, Required, Reserved, Short, Need by; action Reserve from a lot.
**Equipment register** (company view): Asset, Description, State, Project or location, Calibration due.
**Toolcrib fast entry** (§10.5): one line `asset or item · person · qty`, Enter issues, `r` switches to return,
the last ten lines stay visible; keyboard only, scanner input is typed text.
**Tiles:** shortages against IWPs due this week, receipts awaiting MTR, equipment calibration due.

## Workflows and approvals
Receipt acceptance guarded by the MTR slot and, from Phase 3, a receiving inspection; stock is a projection of
movements and rebuilds equal on both databases (R-P2-7); a negative balance is refused except by an admin Adjust with
a reason; one UOM per lot; consumable issues post to a cost code; reservations against the MTO lines of an IWP feed
the `materials_reserved` check; a shortage raises a constraint with the receipt as `resolve_via`; a late receipt
(simulator `material_late`) puts the IWP On hold until it lands.

## Links to other modules
Documents (MTR, certificates); derived documents (MTO publication, `target_kind: mto`); IWP (reservations); cost
codes (consumables); requisitions (material requisition fulfilment issues from stock, M9); quality (receiving
inspection, NCR on a rejected receipt, instrument ↔ equipment, Phase 3); piping (heat number → lot → spool and weld,
Phase 3); external party (vendor MTR upload, Phase 3); scaffold hire quantities stay in M9.

## Integrations
PO lines as a mirror (CSV or inbound endpoint when the ERP exists, P2-Q4). Webhooks `Receipt.Accepted`,
`Receipt.Rejected`, `Stock.Reserved`. **(proposed)** `Stock.Short` event when a reservation cannot be met. Thread
`/dispatch material-request` (M9). MCP read tools `stock_on_hand`, `get_lot`, `heat_trace`, `mto_status`;
proposable `propose_reservation`. Feed: receipt cards only; movements post no card unless tagged (R-P2-16).

## Reports (§12)
Stock on hand by location and item; transaction log; MTO vs received vs issued; shortages against IWPs; equipment
utilisation and location; consumable usage by cost code; heat number traceability. Lake: materials by period.

## Confidentiality and roles
All records `internal`; a vendor sees only the receipt slot its guest link names. Moves and reservations are
`user`; adjust, scrap, library and location tree are admin until a cost or materials role exists (P2-Q3); agents
propose reservations only. Quantities and money written by anyone else are refused (R-P2-9).

## First increment vs later
First (Phase 2 I3): library import, locations, project items, receipts with MTR, movements, stock projection, MTO
publication, reservations, the readiness check, reports, MCP reads, actor. Then I4-B: toolcrib fast entry.
Later: receiving inspection and NCR links (Phase 3); heat traceability to welds (Phase 3); equipment calibration
(Phase 3); vendor guest links (Phase 3); real PO integration (P2-Q4); surplus transfer between projects; barcode and
camera scanning (PWA, Phase 5).

## Open questions for the owner
P2-Q3 who may adjust, scrap and approve; P2-Q4 ERP stub or real; P2-Q5 movements as events (deviation from §9 M4,
needs an ADR). New: what a scanner types at the toolcrib (asset number, serial, item code) so the entry line parses
it; are rental equipment hire days tracked here or only scaffold quantities on hire in M9; does the company item
library need a steward role separate from admin.
