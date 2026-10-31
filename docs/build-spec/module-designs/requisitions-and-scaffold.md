# M9 — Requisitions and work orders (scaffold, labour, material, general)

Brief §9 M9, §12, §21.5 (dispatch). Plan `08-phase2-plan.md` I4-A (engine, four kinds, work orders) and I4-B
(scaffold, checks, toolcrib). Status: design v0.1.

## Users and stories
Foreman and planner (raise), superintendent or approver, scaffold coordinator and scaffold crew, scaffold
inspector, labour coordinator, materials coordinator (fulfil), scaffold subcontractor (Phase 3 party).
- As a **foreman** I ask for a scaffold, six pipefitters or a crane lift from the IWP's thread in one line, and the
  request is linked to the IWP and visible to its readiness.
- As an **approver** I see every open request with its need-by date and approve or reject it with a reason.
- As a **scaffold coordinator** I turn approved requests into erect, modify and dismantle work orders, and no
  dismantle starts while an open IWP still uses the scaffold.
- As a **scaffold inspector** I tag a scaffold green or red after inspection and the due list tells me what is next.

## Records and states
| Record | States |
|---|---|
| `Requisition` (abstract; kinds Material, Labour, Scaffold, General with type psets, e.g. crane lift) | Requested → Approved → Scheduled → In progress → Done → Closed; Rejected, Cancelled |
| `WorkOrder` (from an approved requisition; erect, modify, dismantle, lift, general) | Scheduled → In progress → Done → Closed; Cancelled |
| `Scaffold` (asset) | Requested → Designed → Erecting → Inspected and tagged green → In use → Modify → Dismantle → Removed; tag colour green, red, yellow; inspection due |
| `ScaffoldInspection` | Scheduled → Done (pass or fail); **(proposed)** becomes a kind of M5 `Inspection` when Phase 3 I2 lands, kept by a link |
| `LaborRequisition` lines | Craft, classification, headcount, window, shift; forecast is a read |

## Logs and record screens (log standard)
**Requisition log** (home). Columns: Number, Subject, State, Kind (only when it varies), Requested by, Need by,
For (IWP), Approver. Filters: `o` open, `a` awaiting my approval, by kind. Panel: identity
`P123-REQ-SCF-0017 · Access to rack 12 north face`; state `Requested · since 2026-10-29`; summary `Scaffold · needed
by 2026-11-01 · for IWP-PIP-0042 · J. Soto`; sections Request (text and type properties: location, dimensions, load
class, duration), Key facts, Work orders (table Number, Kind, State, Crew, Planned), Timeline, Files, Links.
Actions: Requested: Approve, Reject (approver, P2-Q3), Edit, Cancel (requester). Approved: Schedule, Assign.
Scheduled: Start. In progress: Complete. Done: Close. Any: Open thread.
**Work order backlog.** Number, Subject, State, Kind, Crew or sub, Planned start, Hours. Actions: Assign, Start,
Complete, Close.
**Scaffold register.** Number, Location, State, Tag, Inspection due, Used by (IWPs), On hire since. Filters: `d` due
or overdue inspection, `r` red tags. Panel summary `Tube and fitting · elevation 12.4 m · gridline C-7 · 3 IWPs`;
sections Status (tag colour, last and next inspection), Requests (table), Work orders, Inspections (table Date,
Inspector, Result), Links (IWPs that require it, tags accessed), Files (tag photo).
Actions: Requested: Design, Start erecting. Erecting: Inspect. Inspected: Tag green, Tag red (inspector).
In use: Inspect, Request modification, Request dismantle (refused while an open IWP requires it). Dismantle: Mark
removed.
**Labour forecast.** A grid Craft × week with requested, approved and covered headcount; drill to requisitions.
**Tiles:** requests awaiting approval, scaffolds overdue for inspection, red tags in use, labour gap next two weeks.

## Workflows and approvals
Approval chain per kind from a setting (`requisitions.approval.<kind>`); numbering per kind, gap-free under
concurrent creators; material requisition fulfilment issues stock through M4 commands with partial fulfilment and a
shortage back to the constraint owner; scaffold inspection interval setting drives the due list job; a failed
inspection turns the tag red and the IWP's `scaffold_tagged` check `blocked`; an approved labour requisition
covering the window turns `labour_requested` `ok`; dismantle check against open IWPs.

## Links to other modules
IWP (`requires`; the two readiness checks), cost code and P6 activity on every requisition, materials (fulfilment
movements), tags and equipment accessed by a scaffold, permits (expected link, `n_a`), quality (scaffold inspection
→ M5 Inspection; deficiencies on a scaffold, Phase 3), documents (scaffold design drawing pinned), external party
(scaffold subcontractor, union hall, Phase 3), correspondence (labour requests to a subcontractor as General items).

## Integrations
Thread `/dispatch material-request | scaffold-erect | scaffold-modify | scaffold-inspect | labour | crane-lift |
general` creates the requisition pre-linked. Webhooks `Requisition.Approved`, `WorkOrder.Completed`,
`Scaffold.Tagged`. MCP read tools; proposable `propose_requisition`. Inbound: scaffold subcontractor status by
endpoint mapping when it has a system (Q10, Phase 3). Feed cards on approval, tag colour change and completion.

## Reports (§12)
Open requisitions; scaffold register (status, tag colour, inspection due); scaffold quantities on hire; labour
requisition forecast by craft and week; work order backlog.

## Confidentiality and roles
All records `internal`. Raise is `user`; approve per P2-Q3 (admin for material and labour, the requester for general
in option A; a cost or superintendent role in option B); tagging a scaffold needs a named inspector: **(proposed)**
an access word `inspector` is not a role today, so the first increment lets any `user` tag and records who did,
and the owner decides whether tagging needs a role; a subcontractor sees its own work orders and scaffolds (Phase 3).

## First increment vs later
First (Phase 2 I4-A): the engine, four requisition kinds, work orders, approval, fulfilment into M4, labour forecast,
thread dispatch wiring, reports. I4-B: scaffold asset lifecycle, inspections, tag colours, due list, the two
readiness checks, register screen, toolcrib (M4 screen).
Later: scaffold inspection as an M5 inspection; scaffold material quantities and hire billing; permits as a record
type; subcontractor portal and inbound status (Phase 3); scaffold tag scanning on mobile (Phase 5); crane lift plans
as documents.

## Open questions for the owner
P2-Q3 who approves which kind. New: who may tag a scaffold green, and must that be a role? Are scaffold quantities
on hire needed from day one (they need scaffold material lines)? Does the GC want labour requisitions to go to a
union hall or subcontractor as formal correspondence (a General domain item) or stay internal?
