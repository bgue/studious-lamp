# Build spec 08 — Phase 2 plan: Execution planning and materials

Brief: §16 Phase 2. M3 field work packaging (COAA WFP), M4 materials, M9 requisitions and work orders; lake gold
marts; simulator scenarios. Six increments. Ticket IDs `P2-I<n>-T<nn>`.

**Phase exit (§16):** issue an IWP with a readiness check covering documents, materials, and scaffold.
**Human gates:** module schema merges; rules-of-credit company package (Q16); sign-off role settings (`awp.release.signoff_roles`).

---

## Increment 1 — GC WBS, cost-code mapping, path of construction, CWA, CWP

**Demo:** load a WBS with 12 nodes mapped to cost codes with allocation %; a path of construction of 4 CWAs; 6 CWPs
linked to CWAs, WBS nodes, referenced EWPs, and XER activities; CWP workflow Planned → In development.
**Fanout:** no. **Supervisor builds:** T02, T05 (allocation rollup).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Fixtures: WBS, cost codes, CWAs, CWP discipline code list | H | — |
| T02 | LinkML `awp.yaml` part 1: `WBSNode`, `PathOfConstruction`, `CWA`, `CWP`, `EWPRef`, `PWPRef`; CWP workflow | S | T01 |
| T03 | Projectors + commands for WBS/POC/CWA/CWP; many-to-many WBS↔CWP with allocation % | H | T02 |
| T04 | EWP/PWP reference records mirroring external packages with forecast/actual dates; constraint-source flag | H | T03 |
| T05 | Allocation rollup: CWP budget hours/qty/$ → WBS → cost code (projection) | S | T03 |
| T06 | TUI: WBS tree, POC sequence editor, CWA/CWP registers and records | H | T05 |
| T07 | API/MCP resources; reports: CWP status, WBS vs cost code | H | T06 |
| T08 | Simulator: planner builds CWPs from template; demo; report | H | T07 |

## Increment 2 — IWP, constraints, readiness, release sign-off

**Demo:** build an IWP from 24 welds (generic commodity records until Phase 3), 8 joints, 3 tags; constraints derived
from need-by dates; readiness screen (sketch 5) shows 5/7; clear constraints; sign-off by two roles; Issue.
**Fanout (orchestrator):** WS-A IWP + constraints; WS-B readiness engine + screens. Contract: `ReadinessCheck`
Protocol (name, evaluate(record) → state, detail, resolve_via).

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `awp.yaml` part 2: `IWP`, `Constraint`, `IWPCloseout`; IWP lifecycle with side states; expected links (permit-to-work @Issued) | S | — |
| A | T02 | IWP commands: create, add scope (links `contains`), split, hold/release, sign-off (roles from settings), issue | H | T01 |
| A | T03 | Constraint commands: need-by = IWP start − `awp.iwp.ready_lead_weeks`; owner; aging; sources manual/rule/`#hold`/`/hold` | H | T01 |
| A | T04 | `cur_constraints` projector; constraint review screen grouped by owner/type | H | T03 |
| B | T05 | Readiness engine: registry of checks (documents current, RFIs answered, materials reserved, scaffold, permits, inspections, labour, predecessors, model slice); `cur_readiness` | S | contract |
| B | T06 | Checks for documents (stale pins) and RFIs (answered); stubs returning `n/a` for materials/scaffold until I3–I4 | H | T05 |
| B | T07 | Readiness screen (sketch 5) + IWP record view tabs | H | T06 |
| B | T08 | Sizing warnings (`awp.iwp.size_hours`), backlog weeks per foreman dashboard tile | H | T05 |
| A | T09 | Webhook `IWP.Ready`; MCP tools; reports: IWP status, readiness & constraint log, constraints by type/owner/age | H | T04, T07 |
| A | T10 | Simulator workface-planner actor; demo; report | H | T09 |

Merge order: A T01–T04 → B → A T09–T10.

## Increment 3 — M4 item library, inventory, receipts

**Demo:** company item library with 50 items; receive 2 flanges with heat number and MTR; issue to a crew against a
cost code; stock on hand by location is a projection of transactions; reserve against an IWP and the readiness check
turns green.
**Fanout:** no. **Supervisor builds:** T02, T04 (inventory projection), T07 (reservation ↔ readiness).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Fixtures: item masters, catalog items, locations hierarchy (company → warehouse → project → laydown → toolcrib → gang box) | H | — |
| T02 | LinkML `materials.yaml`: `ItemMaster`, `CatalogItem`, `ProjectItem`, `MTO/MTOLine`, `POLineRef`, `Receipt` (file slot `mtr`), `StockLot`, `SerializedItem`, `InventoryTransaction`, `Equipment`, `InventoryLocation` | S | T01 |
| T03 | Commands: receive, issue, transfer, return, adjust, scrap, reserve, unreserve (quantities as deltas, §22.4) | H | T02 |
| T04 | Inventory projection: stock = sum of transactions per lot/location; heat traceability columns | S | T03 |
| T05 | MTO import from derived documents (Phase 1 pipeline) → `MTOLine` linked to CWP/IWP | H | T03 |
| T06 | Receiving inspection hook (links to Phase 3 inspection later); MTR slot required before Accepted | H | T03 |
| T07 | Reservation ↔ IWP readiness check (materials reserved) | S | T04 |
| T08 | TUI: item library, stock by location, receipt entry, transaction log | H | T04 |
| T09 | Company-level aggregation views (equipment utilisation, surplus) | H | T04 |
| T10 | Reports: stock on hand, MTO vs received vs issued, shortages against IWPs, heat traceability; demo; report | H | T08 |

## Increment 4 — M9 requisitions and work orders, scaffold, toolcrib

**Demo:** thread `/dispatch material-request` creates an MR linked `requires` to the IWP; a scaffold request → scaffold
asset Requested → Erecting → Inspected/Tagged Green; the IWP scaffold readiness check turns green; toolcrib screen
issues a tool to a person in one line.
**Fanout (orchestrator):** WS-A engine + specialisations; WS-B screens (toolcrib, scaffold register). Contract: `Requisition`/`WorkOrder` base classes.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `requisitions.yaml`: `Requisition`, `WorkOrder` + `ScaffoldRequest`, `Scaffold`, `LaborRequisition`, `MaterialRequisition`, `GeneralRequisition`; workflows | S | — |
| A | T02 | Generic engine: numbering, approval chain, scheduling, assignment, closeout | S | T01 |
| A | T03 | Scaffold lifecycle incl. tag colour, inspection intervals → due list; dismantle check against open IWPs | H | T02 |
| A | T04 | Labour requisition forecast by craft/week; material requisition → inventory transactions | H | T02 |
| A | T05 | Readiness checks: scaffold erected and tagged; labour requested | H | T03 |
| B | T06 | Toolcrib issue/return fast-entry screen (§10.5) | H | — |
| B | T07 | Scaffold register, requisition and WO screens; dispatch wiring from threads | H | A T03 |
| A | T08 | Reports: open requisitions, scaffold register, quantities on hire, labour forecast, WO backlog; demo; report | H | T07 |

## Increment 5 — Weekly workface planning cycle, rules of credit, progress, IWP pack, closeout

**Demo:** run one weekly cycle: load XER snapshot → look-ahead with unready IWPs → constraint review → release →
foreman commitments → progress and PPC → closeout with feedback; print an IWP pack PDF.
**Fanout:** no. **Supervisor builds:** T02 (rules-of-credit engine), T03 (progress rollup).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | `RulesOfCredit` company package (schema registry) with weld/joint/generic commodity examples (human gate) | S | — |
| T02 | Rules-of-credit engine: earned % from linked record states | S | T01 |
| T03 | Progress rollup IWP → CWP → WBS/cost code; export quantities (CSV) to cost system | S | T02 |
| T04 | `LookAhead` from current XER snapshot joined to readiness | H | — |
| T05 | `WeeklyPlan`: commitments, PPC, miss reasons | H | — |
| T06 | Weekly cycle screens (6 steps) | H | T04, T05 |
| T07 | IWP pack template (Jinja2 → PDF): cover, scope, drawings with QR, MTO, safety, ITP, permits, scaffold tags, sign-off | H | — |
| T08 | Closeout: actual hours import (CSV), redlines slot, remaining punch, feedback | H | — |
| T09 | KPIs: backlog weeks, % constraint-free, constraint aging, schedule compliance, PPC, earned vs burned, stale-pin issues | H | T03 |
| T10 | Subcontracted scope: CWP/IWP party assignment, interface constraints, progress via inbound webhook; demo; report | H | T09 |

## Increment 6 — Simulation, lake marts, reports, Phase 2 exit

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Simulator scenario `refinery-piping-medium` v2: materials coordinator, scaffold supervisor actors; `material_late` injection | H | — |
| T02 | Lake gold marts: IWP readiness history, materials, schedule trend vs readiness | H | — |
| T03 | Base reports audit against §12 for M3/M4/M9 | H | — |
| T04 | Phase-exit demo: issue an IWP with documents, materials, scaffold readiness green on a simulated project | H | T01 |
| T05 | Phase report, risk register, ADRs (orchestrator) | O | T04 |
