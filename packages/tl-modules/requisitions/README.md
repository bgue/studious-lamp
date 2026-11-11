# tl-mod-requisitions (`tl_mod_requisitions`)

Requisitions and work orders (brief §9, M9). A requisition asks for labour, material, a general service or a
scaffold. Approving it opens a work order; the work order is scheduled, assigned, started, completed and closed.
Schema: `schema/modules/requisitions/`; contract: `docs/build-spec/phase2-contracts-draft.md` §3. The guide for
people is `docs/modules/requisitions/README.md`; the runbook is `docs/runbooks/requisitions.md`.

## Built
- Raise four kinds: `labor` (craft, headcount, start and end dates), `material` (lines of item, quantity and unit,
  from a location), `general` (a code-listed type such as `crane_lift`), `scaffold` (purpose and days).
- Edit a requisition while it is Requested; approve, reject (with a reason) or cancel it.
- Approve opens the work order in the same unit of work. Work orders: schedule, assign, start, complete (hours),
  close. Cancelling an Approved requisition cancels its Open work order with it.
- Start of a work order runs the `no_open_blocking_constraints` guard (phase `start`).
- Reads through the API, the CLI, the TUI log screens and MCP. An agent may propose a new requisition; it never
  approves, rejects, schedules or closes.

## States
Requisition: Requested, Approved, Scheduled, In progress, Done, Closed, Rejected, Cancelled. Closed, Rejected and
Cancelled are final. After Approved the requisition follows its work order. Work order: Open, Scheduled, In
progress, Done, Closed, Cancelled; Closed and Cancelled are final. Workflows:
`schema/fixtures/workflows/requisitions-requisition-<kind>.yaml` (one per kind) and
`schema/fixtures/workflows/requisitions-work-order.yaml`.

## Numbering
`<project>-REQ-LAB-nnnn`, `-REQ-MAT-`, `-REQ-GEN-` and `-REQ-SCF-` (one gap-free counter per kind), and
`<project>-WO-nnnn` for work orders. Patterns: `schema/fixtures/numbering/patterns.yaml`.

## Access words
Twelve words in `schema/settings/access-words.yaml`, listed in `docs/reference/access-words.md`:
`requisitions.view` (table word `read`); `raise`, `edit`, `cancel`, `start`, `complete` (`user`); `approve`,
`reject`, `schedule`, `assign`, `close` (`controller`). `requisitions.fulfil` (`user`) is in the yaml and has no
command yet.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_requisitions.module:spec` | entry point `throughline.modules` (`requisitions`) | The `ModuleSpec`: record types, projectors, `REQUISITIONS_COMMANDS` (ten commands with their access words), `PROPOSABLE` (`propose_requisition`). |
| `tl_mod_requisitions.commands` | module | Command models: `RaiseRequisition`, `EditRequisition`, `ApproveRequisition`, `RejectRequisition`, `CancelRequisition`, `ScheduleWorkOrder`, `AssignWorkOrder`, `StartWorkOrder`, `CompleteWorkOrder`, `CloseWorkOrder`. |
| `tl_mod_requisitions.handlers` | package | One handler per command: `requisitions.py`, `work_orders.py`. |
| `tl_mod_requisitions.views` | module | Read views for the entry points: requisition list and detail, work order list and detail. Each takes `viewer=`. |
| `tl_mod_requisitions.api` | module | Reads for other modules: `open_requisitions_for`, `work_order_for`, `RequisitionRow`, `WorkOrderRow`. |
| `tl_mod_requisitions.names` | module | Record types, tables, views, event types, states, access words. |
| `tl_mod_requisitions.projectors` | package | `RequisitionProjector` (dispatches by kind) and `WorkOrderProjector`. |
| `tl_mod_requisitions.guards`, `actions`, `errors` | modules | Workflow guards, rule actions, refusal texts. |

## Confidentiality
A requisition inherits the class of its subject, `for_record_id` (the IWP or CWP it serves). A requisition with no
subject is its own subject. A work order is hidden with its requisition. A hidden requisition is absent from the
lists and its detail reads as a missing one. The join is `SUBJECT_LINKS` in `tl_core.confidentiality`; every read
here takes the viewer's class filter.

## Events
`Requisition.Raised|Revised|Approved|Rejected|Cancelled|Fulfilled` are on the requisition's stream.
`WorkOrder.Opened|Scheduled|Assigned|Started|Completed|Closed` are on the work order's stream, with `requisition_id`
in every payload. Every payload has an optional `at`, tagged `tl:valid_time: at`. `Requisition.Fulfilled` is
declared; no command emits it yet.

## Not built yet
Stock fulfilment, first-in first-out lots, the shortage constraint, the labour forecast, reports, and the first
module-to-module import (the scaffold module reading `api.py`, deferred to S3). See `docs/build-spec/DEFERRED.md`.

## Depends on / used by
- Depends on: `tl-core`, `tl-schema`, `tl-mod-engineering` (the general requisition type code list).
- Used by: `tl-api` (routes), `tl-cli` (`tl req`, `tl wo`), `tl-mcp` (read and propose tools), `tl-tui` (log screens).
  No other module imports `api.py` yet.
