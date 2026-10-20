# Phase 2 — shared contracts (DRAFT)

Status: **DRAFT**, 2026-10-17. The orchestrator freezes these at phase start (wave 0 of `08-phase2-plan.md`),
commits the Python files named here, and from then on they change only by orchestrator decision, as
`tl_core/derivation/types.py` did for P1-I3 (`docs/tickets/P1-I3/FANOUT.md`, "Shared contracts"). Everything
below names interfaces that do not exist yet; everything it builds on is verified in the tree (`08-phase2-plan.md`
§0). Owner questions it depends on are marked `P2-Q<n>`.

Style: the P1-I3 contract. Pydantic models with bounds as module constants, a `Protocol` per plugin, an entry-point
group, and pipeline-side signatures listed as comments so the other workstream can test against them.

| § | Contract | Fanout that needs it frozen | File |
|---|---|---|---|
| 1 | Readiness checks (plugin registry, facts, results, event, job) | I2 WS-A ∥ WS-B; I3 T07; I4 T05 | `packages/tl-core/src/tl_core/readiness/types.py` |
| 2 | Constraint sources and the check-raised constraint | I2 WS-A ∥ WS-B | `packages/tl-modules/awp/src/tl_mod_awp/constraints/types.py` |
| 3 | Requisition and work order base; what the scaffold module consumes | I4 WS-A ∥ WS-B | `schema/modules/requisitions/requisition.yaml` (LinkML), `tl_mod_requisitions/api.py` |
| 4 | Inventory movements and reservations (what I4 and the readiness check call) | I1 ∥ I3; I4 WS-A | `tl_mod_materials/api.py` |
| 5 | Rules of credit package and the earned-progress result | I5 (and I2 `ScopeItem`) | `schema/modules/awp/rules_of_credit.yaml`, `tl_mod_awp/progress/types.py` |
| 6 | Simulator desks and actors for Phase 2 | every actor ticket; I6 | `tl_sim/desks/` (names only) |
| 7 | Reserved identifiers and job kinds added by Phase 2 | all | `tl_core/services/reserved.py` (additions) |

---

## 1. Readiness checks

```python
"""Readiness contracts for Phase 2 (brief §9 M3 "Readiness check"; 08-phase2-plan.md I2).

Frozen for the phase: change only by orchestrator decision.

A *readiness check* answers one question about one IWP from the live linked records ("documents
current", "materials reserved", "scaffold erected and tagged", ...). Checks are plugins found
through the entry-point group READINESS_ENTRY_POINT; each entry point names a zero-argument
callable that returns an object satisfying ReadinessCheck. The awp module runs them in a job
(kind JOB_KIND, one IWP per run) and appends one IWP.ReadinessEvaluated event with every result;
cur_awp_readiness is projected from that event, so a rebuild never calls a check.

A check is read-only: it gets a connection, never a unit of work, never writes, never raises for
a bad record (it answers "unknown" with a fixed detail), never opens the network, and keeps every
list it returns inside the bounds below. The module that ships a check owns the tables it reads;
the awp module never imports that module (the ADR-0010 and P1-I3 pattern).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from sqlalchemy import Connection

READINESS_ENTRY_POINT = "throughline.readiness_checks"
JOB_KIND = "awp.readiness"

#: Bounds on what one check may return (the parent refuses a result past any of them; the IWP's
#: evaluation is then "unknown" for that check, never truncated, as P1-I3 D10 did for results).
MAX_CHECKS = 32
MAX_RESOLVE_VIA = 50
MAX_DETAIL_CHARS = 500
MAX_NAME_CHARS = 64
#: Bounds on an evaluation run (the job claims one IWP; a check that takes longer fails the run
#: with a fixed code and the IWP keeps its previous evaluation).
CHECK_MAX_SECONDS = 10
EVALUATION_LEASE_S = 60.0

#: ok: nothing blocks this aspect. blocked: at least one resolve_via record must change.
#: pending: something was asked for and is not yet answered (a reservation requested, an RFI
#: open). n_a: the check's module or record type does not exist yet; detail names the decision.
#: unknown: the check could not answer (a bound was hit, a read failed); never blocks release
#: silently: the release command refuses an IWP with an unknown check unless the setting
#: awp.release.allow_unknown_checks is true.
CheckState = Literal["ok", "blocked", "pending", "n_a", "unknown"]


class IwpFacts(BaseModel):
    """What every check is told about the IWP. Read once per evaluation by the awp module
    (tl_mod_awp.facts.iwp_facts); checks read linked records themselves through the connection."""

    record_id: str
    scope: str  # the project scope
    key: str  # P123-IWP-PIP-0042
    status: str  # the workflow state, "Draft" when the record never moved (L-P1-I2-3)
    discipline: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    foreman: str | None = None  # an account actor string, user:<name>
    estimated_hours: float | None = None
    #: The ids of the records the IWP `contains`, by record type (scope items, tags; Phase 3 welds).
    scope_ids: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    #: Active links from the IWP that pin a document revision (relation references, pin set).
    pinned_document_links: list[str] = Field(default_factory=list[str])


class RecordRef(BaseModel):
    """A record a person can open to resolve a blocked check."""

    record_id: str
    record_type: str
    key: str


class CheckResult(BaseModel):
    name: str = Field(max_length=MAX_NAME_CHARS)
    version: str
    state: CheckState
    #: Fixed text plus the caller's keys and counts; no paths, no exception text.
    detail: str = Field(max_length=MAX_DETAIL_CHARS)
    #: Records whose change would move the state (a stale pin, an open constraint, a receipt).
    resolve_via: list[RecordRef] = Field(default_factory=list[RecordRef], max_length=MAX_RESOLVE_VIA)
    #: Counts for the screen ("5/7 drawings current"); None when the check has no denominator.
    count_ok: int | None = None
    count_total: int | None = None


@runtime_checkable
class ReadinessCheck(Protocol):
    """A plugin that answers one question about one IWP. Pure reads, no writes, no network."""

    #: Unique, snake case: "documents_current", "materials_reserved", "scaffold_tagged".
    name: str
    #: Bump when the answer for the same state changes.
    version: str
    #: Record types whose events ask for a re-evaluation of the IWPs that link them (the awp
    #: module subscribes to these; a check that reads tables no event names declares the type
    #: whose module writes those tables).
    watches: frozenset[str]

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP as of ``today`` (the job's clock; a simulation sets it)."""
        ...


# Event (schema/modules/awp/readiness_events.yaml, tl:event_type IWP.ReadinessEvaluated, stream
# of the IWP): {iwp_id, evaluated_at, today, ready: bool, checks: list[CheckResult] (bounded),
# facts_hash: sha256 of the canonical IwpFacts}. IWP.Ready (the brief's default webhook) is
# appended by the same job when `ready` turns true and the previous evaluation was not ready.
#
# Pipeline-side signatures, implemented in I2 WS-B and listed here so WS-A, I3 and I4 can test
# against them:
#   tl_core.readiness.registry.load_checks() -> dict[str, ReadinessCheck]
#       Loads READINESS_ENTRY_POINT. A plugin that fails to load is an error at first use, never a
#       silent gap (ADR-0010 decision 3). Two checks with one name is an error.
#   tl_mod_awp.readiness.request(uow, iwp_ids: Sequence[str], *, reason: str) -> int
#       Queues one JOB_KIND job per IWP not already queued (job id "ready:<iwp id>"); returns
#       how many were queued. Called by WS-A's commands (scope, pin, constraint changes) and by
#       the modules that ship checks when their state changes (a reservation, a tag colour).
#   tl_mod_awp.readiness.evaluate_now(uow, iwp_id, today) -> ReadinessView
#       The same evaluation inside a request, for the release command and the demo; bounded by
#       the same constants; it appends the same event.
#   tl_mod_awp.readiness.views.readiness(conn, scope, iwp_key) -> ReadinessView
#       From cur_awp_readiness (projected): the last evaluation, its checks, ready, evaluated_at.
# Every check ships with a test that calls
#   tests/contract/test_readiness_contract.py::check_readiness_contract(check, world)
# which proves: no write (a read-only connection; L-P1-I0B-4), bounds, fixed detail, n_a for a
# missing dependency, and that `watches` names existing record types.
```

Checks and owners:

| Name | Ships in | Reads | `n_a` until |
|---|---|---|---|
| `documents_current` | I2 WS-B | pinned links and `tl_mod_documents.resolver` (stale by the class-aware rule) | — |
| `rfis_answered` | I2 WS-B | `correspondence` RFI records linked to the IWP (P1-I6) | P1-I6 on the trunk |
| `constraints_clear` | I2 WS-A (the one check the awp module owns and WS-A writes) | `cur_awp_constraint` (`blocks` the IWP, open) | — |
| `materials_reserved` | I3 T07 | reservations against the MTO lines of the IWP | — |
| `scaffold_tagged` | I4 WS-B T05 | `scaffold.Scaffold` the IWP `requires`, tag colour | — |
| `labour_requested` | I4 WS-B T05 | approved `LaborRequisition` covering the window | — |
| `permits_planned`, `inspections_planned`, `predecessors_handed_over`, `model_slice_available` | I2 WS-B T06b | nothing | Phase 3 |

---

## 2. Constraint sources and the check-raised constraint

```python
"""Constraint contracts shared by I2 WS-A (commands) and WS-B (the engine raises constraints)."""

from typing import Literal

#: Where a constraint came from (brief §9 M3). The last two are server sources: a client that
#: names them is refused (the link-source rule of ADR-0010 addendum 2, item 3), and the readiness
#: job and the rules engine write them with by_module=True.
ConstraintSource = Literal["manual", "feed_hold", "thread_hold", "rule", "check"]
#: Constraint types are a code list of co.acme.awp@1.0.0 (documents, materials, scaffold, permit,
#: labour, access, engineering, other); the command validates against the registry.

# tl_mod_awp.constraints.raise_from_check(uow, iwp_id, check: CheckResult, *, today) -> str | None
#     Called by the readiness job for a check in state "blocked" when awp.constraint.auto_raise is
#     true: one open constraint per (IWP, check name), owner = the IWP's foreman or the type's
#     default owner from the setting awp.constraint.default_owners, need_by = planned_start minus
#     awp.iwp.ready_lead_weeks, source "check", resolve_via copied (bounded). Returns the id or None
#     when one is already open. Idempotent: a job run twice raises nothing twice.
# tl_mod_awp.constraints.clear_from_check(uow, iwp_id, check_name, *, resolved_by: str | None)
#     Clears the constraint the same check raised when the check turns "ok"; a person's constraint
#     of the same type is never cleared by the engine (source decides, as the module-flagged links
#     of ADR-0015 §5).
```

---

## 3. Requisition and work order base (I4)

LinkML, `schema/modules/requisitions/requisition.yaml` (abstract base; every specialisation `is_a: Requisition`
and adds its own slots; the generated tables are one per concrete class, as ADR-0010):

```yaml
classes:
  Requisition:
    abstract: true
    is_a: RecordEnvelope
    annotations:
      tl:current_state: true
    slots: [kind, requester, need_by, location_text, priority, approval_chain, approved_by, approved_at, work_order_id]
  WorkOrder:
    is_a: RecordEnvelope
    annotations: {tl:current_state: true, tl:record_types: [requisitions.WorkOrder]}
    slots: [requisition_id, assigned_to, planned_start, planned_finish, actual_start, actual_finish, hours_planned, hours_actual]
  LaborRequisition: {is_a: Requisition, slots: [craft, classification, headcount, start_date, end_date, shift, requirements]}
  MaterialRequisition: {is_a: Requisition, slots: [from_location_id, lines]}   # lines: JSON, bounded by MAX_LINES
  GeneralRequisition: {is_a: Requisition, slots: [general_type]}               # type-specific psets by class binding
  ScaffoldRequest: {is_a: Requisition, slots: [purpose, elevation, gridline, length_m, width_m, height_m, load_class, duration_days]}
slots:
  kind: {range: RequisitionKind}   # enum: labor, material, general, scaffold
  priority: {range: Priority}      # enum: low, normal, high, urgent
  approval_chain: {range: string, multivalued: true}   # access words or account actors, P2-Q3
```

Workflow fixtures `requisitions-requisition.yaml` (one definition, `record_type` per concrete class) and
`requisitions-work-order.yaml`. Links: a requisition `requires` from the IWP or CWP it serves; `references` a
`cost.CostCode` and an activity; a work order `belongs_to` its requisition.

```python
# tl_mod_requisitions/api.py (what the scaffold module and I3 call; never the handlers directly)
# open_requisitions_for(conn, record_id: str, *, kinds: Sequence[str] | None = None) -> list[RequisitionRow]
#     Requisitions that `requires` the record and are not Closed, Rejected or Cancelled.
# work_order_for(conn, requisition_id: str) -> WorkOrderRow | None
# Events the scaffold module watches (stream of the requisition): Requisition.Approved,
# Requisition.Rejected, WorkOrder.Scheduled, WorkOrder.Completed, WorkOrder.Closed.
# Access (P2-Q3 option A): RaiseRequisition user; ApproveRequisition admin for labor and material,
# user (the requester's superintendent, unchecked in Phase 2) for general and scaffold;
# ScheduleWorkOrder, AssignWorkOrder, CompleteWorkOrder user; CloseWorkOrder user.
MAX_LINES = 200
MAX_APPROVAL_CHAIN = 5
```

The `scaffold` module: `scaffold.Scaffold` (asset) and `scaffold.ScaffoldInspection`; `Scaffold` `belongs_to` its
`ScaffoldRequest`; `ErectScaffold`, `InspectScaffold` (tag colour `green`, `red`, `yellow`; next due from
`scaffold.inspection.interval_days`), `DismantleScaffold` (refused while `open_requisitions_for` of any IWP that
`requires` the scaffold is non-empty or the IWP is Issued or In progress). The module imports
`tl_mod_requisitions.api` (read) and never its handlers. This is the first module-to-module import; it is recorded
here so a later ADR can replace it with an entry point if a third consumer appears.

---

## 4. Inventory movements and reservations (I3; called by I4 WS-A and the readiness check)

```python
"""tl_mod_materials/api.py: the surface other modules call. Movements are events on the lot's
stream (P2-Q5); the brief's cross-references are typed fields of the event, projected as columns of
cur_materials_movement. Quantities are Decimal with a UOM from the registry; every write is a delta
(brief §22.4) and a negative stock is refused unless the movement is an admin Adjust with a reason."""

from decimal import Decimal
from typing import Literal

MovementKind = Literal["receive", "issue", "transfer", "return", "adjust", "scrap", "reserve", "unreserve"]
MAX_QTY = Decimal("1000000000")      # refused above (fixed message), never cut
MAX_REASON_CHARS = 500
MAX_LINES_PER_CALL = 200


class Movement(BaseModel):            # the command payload shared by Receive, Issue, ...
    kind: MovementKind
    lot_id: str                        # a materials.StockLot (or SerializedItem) record id
    qty: Decimal                       # > 0; the kind says the sign
    uom: str                           # must equal the lot's base UOM or convert through the registry
    from_location_id: str | None = None
    to_location_id: str | None = None
    cost_code_id: str | None = None    # cost.CostCode; required for issue of consumables
    iwp_id: str | None = None          # awp.IWP; required for reserve and unreserve
    requisition_id: str | None = None  # requisitions.MaterialRequisition
    person: str | None = None          # an account actor (user:<name>) for issue to a person
    reason: str | None = None          # required for adjust and scrap


# post_movements(uow, movements: Sequence[Movement], *, actor, source, by_module=False) -> list[str]
#     One unit of work, one event per movement, projection rows updated inline; refuses the whole
#     batch on the first problem (fixed message; L-P1-I2-17 text checks). Adjust and scrap need the
#     admin access of the calling command; a module caller (I4 fulfilment) passes by_module=True to
#     skip the allow-list of the lot's record type, never the access word.
# stock(conn, scope, *, lot_id=None, location_id=None, item_id=None) -> list[StockRow]
# reservations_for_iwp(conn, iwp_id) -> list[ReservationRow]   # what materials_reserved reads
# mto_lines_for(conn, record_id) -> list[MtoLineRow]            # CWP or IWP
```

---

## 5. Rules of credit and earned progress (I5)

LinkML `schema/modules/awp/rules_of_credit.yaml`: a `RulesOfCredit` package edition is a company registry record
(`awp.RulesOfCredit`, key `<set>@<semver>`, loaded like a standards edition, closed rather than rewritten), holding
`rules: list[CommodityRule]` with `commodity_type` (a record type: `awp.ScopeItem`, later `piping.Weld`),
`steps: list[{name, state, weight}]` where `state` is a workflow state of that type and the weights sum to 100.
`awp.rules_of_credit.set` (brief §30.5) names the edition in force per project.

```python
# tl_mod_awp/progress/types.py
class EarnedResult(BaseModel):
    iwp_id: str
    edition: str                      # the RulesOfCredit key used
    earned_fraction: Decimal          # 0..1, 4 decimals
    earned_hours: Decimal | None      # earned_fraction × estimated_hours
    by_type: dict[str, Decimal]       # commodity type -> earned fraction
    manual_items: int                 # scope items progressed by hand (no rule)
    as_of_seq: int                    # the ledger seq the figures are a function of

# earned_fraction(conn, iwp_id: str, *, edition: str | None = None) -> EarnedResult
#     Pure read; deterministic for a seq; a scope item whose type has no rule counts by its manual
#     percent_complete; an edition the registry lacks is a fixed refusal.
# Rollup (job awp.rollup, shared with I1): per CWP the sum over its IWPs; per WBS node the sum over
# its CWPs by allocation %; per cost code the sum over nodes. Written as CWP.ProgressRolledUp and
# WBSNode.ProgressRolledUp events (counts, totals, the seq range), projected to cur_awp_rollup;
# export_progress(conn, scope, period) -> CSV rows [cost_code, period, earned_qty, uom, earned_hours,
# as_of_seq] with the reserved source prefix "progress:" on the export event.
```

---

## 6. Simulator desks and actors

Follows `ScheduleDesk` (P1-I4 S15): a desk is the typed client surface an actor uses, with `FakeWorld` held to the
real suite call by call. Names reserved so the increments' actor tickets do not collide:

| Desk | Calls | Actor (ticket) |
|---|---|---|
| `AwpDesk` | create CWP from template, create IWP, add scope, pin, raise and clear constraint, request readiness | `workface_planner` (I1 T08, I2 T10) |
| `MaterialsDesk` | receive with MTR, issue, reserve, unreserve | `materials_coordinator` (I3 T11) |
| `ScaffoldDesk` | raise scaffold request, erect, inspect (colour), dismantle | `scaffold_supervisor` (I4 T08b) |
| `ForemanDesk` | commit for the week, progress scope items, closeout feedback | `foreman` (I5 T10, I6 T01) |

Operators (`Scenario.operators`, P2-Q6 option A): the sign-off and issue of IWPs, requisition approval, inventory
adjust. Injections added to `INJECT_EVENTS` in I6: `material_late {item, days}` (a receipt deferred), `scaffold_failed
{scaffold, days}` (a red tag). The `tl_sim` boundary test stays: the simulator imports nothing from `tl_adapters`
and reaches the suite through its public MCP and API only (L-P1-I0B-7).

---

## 7. Reserved identifiers and job kinds added by Phase 2

| Kind | Value | Added in |
|---|---|---|
| Correlation prefix | `ready:` (readiness evaluations), `rollup:` (allocation and progress rollups), `progress:` (exports) | `tl_core/services/reserved.py` `DERIVE_CORRELATION_PREFIX` becomes a tuple `RESERVED_CORRELATION_PREFIXES`; the body-model check and the API-walking test (L-P1-I3-10) stay |
| Event source prefixes | `job:awp.readiness`, `job:awp.rollup`, `job:scaffold.inspections_due` | the job kinds write them; `RESERVED_SOURCE_PREFIXES` gains `job:` |
| Job kinds | `awp.readiness`, `awp.rollup`, `scaffold.inspections_due`, `lake.phase2_marts` | each in the module that owns it; `tl awp worker`, `tl scaffold worker` list theirs; a shared worker is a follow-up |
| Link sources written by Phase 2 jobs | `rule` (constraints raised by a check), with `by_module=True` | ADR-0010 addendum 2 item 3 unchanged |
