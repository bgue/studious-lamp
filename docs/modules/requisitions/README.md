# Module spec: requisitions

Status: as built for P2-I4A (raise to close). Written by: P2-I4A-T12. Brief sections: §9 (M9), §18.3, §24.
Contract: [phase2-contracts-draft.md](../../build-spec/phase2-contracts-draft.md) §3. Decisions: ADR-0016 (confidentiality),
ADR-0014 section 8 and ADR-0027 (what an agent may propose). Package: `packages/tl-modules/requisitions/README.md`.

## Purpose
A requisition is a request for labour, material, a general service or a scaffold, made for a work package or an IWP
of the project. A person approves it, and the approval opens a work order that is scheduled, assigned, started,
completed and closed. The module numbers each request and each work order, keeps the history of every change and
names who did what.

## Record types
| Type | Table | Purpose | Workflow |
|---|---|---|---|
| `requisitions.LaborRequisition` | `cur_requisitions_labor_requisition` | Crew needed: craft, headcount, dates, shift | `requisitions-requisition-labor.yaml` |
| `requisitions.MaterialRequisition` | `cur_requisitions_material_requisition` | Items needed: lines of item, quantity, unit | `requisitions-requisition-material.yaml` |
| `requisitions.GeneralRequisition` | `cur_requisitions_general_requisition` | A service of a code-listed type (for example `crane_lift`) | `requisitions-requisition-general.yaml` |
| `requisitions.ScaffoldRequest` | `cur_requisitions_scaffold_request` | Scaffold: purpose, days it stands | `requisitions-requisition-scaffold.yaml` |
| `requisitions.WorkOrder` | `cur_requisitions_work_order` | The work that an approved requisition opens | `requisitions-work-order.yaml` |

The four requisition workflows are the same states and moves; they differ only in `id` and `record_type`, because the
loader finds a workflow by its exact record type. Numbers: `<project>-REQ-LAB-0001`, `-REQ-MAT-`, `-REQ-GEN-`,
`-REQ-SCF-` (one counter per kind, gap-free) and `<project>-WO-0001` (gap-free).

## States
| Record | States | Final |
|---|---|---|
| Requisition | Requested, Approved, Scheduled, In progress, Done, Closed, Rejected, Cancelled | Closed, Rejected, Cancelled |
| Work order | Open, Scheduled, In progress, Done, Closed, Cancelled | Closed, Cancelled |

A requisition moves Requested to Approved, Rejected or Cancelled. After Approved it follows its work order: the engine
moves the requisition when the work order moves. Requested or Approved can be cancelled; cancelling an Approved
requisition also cancels its Open work order.

## Commands and who may run them
`REQUISITIONS_COMMANDS` in `packages/tl-modules/requisitions/src/tl_mod_requisitions/module.py` lists ten commands,
each with one access word from [`docs/reference/access-words.md`](../../reference/access-words.md).

| Access word | Commands |
|---|---|
| `requisitions.raise` (user) | `RaiseRequisition` |
| `requisitions.edit` (user) | `EditRequisition` (a Requested requisition only) |
| `requisitions.cancel` (user) | `CancelRequisition` (reason required) |
| `requisitions.start` (user) | `StartWorkOrder` |
| `requisitions.complete` (user) | `CompleteWorkOrder` |
| `requisitions.approve` (controller) | `ApproveRequisition`: opens the work order |
| `requisitions.reject` (controller) | `RejectRequisition` (reason required) |
| `requisitions.schedule` (controller) | `ScheduleWorkOrder` |
| `requisitions.assign` (controller) | `AssignWorkOrder` |
| `requisitions.close` (controller) | `CloseWorkOrder` |

`requisitions.fulfil` (user) is in the access words yaml. No command carries it yet. The word `requisitions.view`
(read) gates the API routes and the CLI reads (`ls`, `show`). The MCP reads do not check it yet (see the reference page).

Who holds a word: a module role grants words (`viewer` holds `read`; `user` holds `read` and `user`; `superuser` holds
`read`, `user` and `controller`). An active admin holds every word. An admin grants a module role per project:
`tl admin roles grant <name> --project P123 --module requisitions --role superuser --reason "..."`. Every account
holds the `user` role in every module, so a person is `user` unless a grant says otherwise.

## Confidentiality
A requisition inherits the class of its subject: `for_record_id`, the IWP or CWP it serves (ADR-0016). A hidden
requisition is absent from every list, its work order is hidden with it, and its detail reads as a missing record.
The MCP tests read as five kinds of reader (`packages/tl-mcp/tests/test_requisition_tools.py`); the confidentiality
tests are in `tests/confidentiality/test_core.py`.

## Agents
An agent never runs a requisition command. It proposes a new requisition with `propose_requisition` (MCP), and a person
with `requisitions.raise` accepts it as themselves. Approve, reject, schedule, assign, start, complete, close, edit and
cancel are not proposable; `tests/tools/proposable_exclusions.toml` records each one and its reason.

## Events
| Event | Stream | Meaning |
|---|---|---|
| `Requisition.Raised` | the requisition's | Created; the payload is flat: base fields and the fields of its kind |
| `Requisition.Revised` | the requisition's | Fields changed while Requested; `changes` maps each field to `[old, new]` |
| `Requisition.Approved`, `.Rejected`, `.Cancelled` | the requisition's | The decision; the reason is in the payload for reject and cancel |
| `Requisition.Fulfilled` | the requisition's | Declared; not emitted by any command yet |
| `WorkOrder.Opened`, `.Scheduled`, `.Assigned`, `.Started`, `.Completed`, `.Closed` | the work order's | The work order's life; each carries `requisition_id` |

`Requisition.Approved`, `Requisition.Rejected` and `WorkOrder.Completed` carry feed text. Every payload has an
optional `at` (valid time); the payloads of `WorkOrder.Started` and `.Completed` mark it required. The catalogue is `schema/modules/requisitions/events.yaml`
and the generated catalog.

## Read paths
| Surface | Reads | Doc |
|---|---|---|
| API | four routes under `/projects/{project}/requisitions` and `/projects/{project}/work-orders` | [reference](../../reference/requisitions.md) |
| CLI | `tl req ls`, `tl req show`, `tl wo ls`, `tl wo show` | [runbook](../../runbooks/requisitions.md) |
| TUI | the requisition log (palette: `requisitions`), the work order backlog (palette: `work-orders`) and one-item screens | [runbook](../../runbooks/requisitions.md) |
| MCP | `list_requisitions`, `get_requisition`, `list_work_orders`, `get_work_order`, `propose_requisition` | [reference](../../reference/requisitions.md) |

## Not built yet
Stock fulfilment, first-in first-out lots, the shortage constraint, the labour forecast, reports, the TUI write actions
for requisitions, and the first module-to-module import (the scaffold module reading `api.py`). See
[`docs/build-spec/DEFERRED.md`](../../build-spec/DEFERRED.md).

## Demo
`just demo P2-I4` runs `dev/demos/P2-I4.sh` on SQLite and Postgres: raise, approve, a work order to close, the
refusal of an unauthorised approve, numbering under two writers, and one state across API, TUI and MCP.
