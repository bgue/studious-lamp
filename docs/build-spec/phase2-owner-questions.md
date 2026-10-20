# Phase 2 — questions only the owner can answer

Status: open, 2026-10-17. Written in the style of the Phase 1 questions that became ADR-0008; the answers become
ADR-0016 and are recorded before wave 0 of `08-phase2-plan.md` starts. Each question gives the options, a
recommended default, and what is blocked until it is answered. "Blocked" names increments of the Phase 2 plan.

| # | Question | Blocks |
|---|---|---|
| P2-Q1 | Rules-of-credit company package (brief Q16) | I5 T01, T02, T03; the I6 exit KPIs |
| P2-Q2 | Who signs off an IWP release (`awp.release.signoff_roles`), and does that need a new role | I2 S4, T02; I5 release step; the I6 exit |
| P2-Q3 | Materials and requisition authority; a cost role | I1 T03, I3 T03, I4 T02; P1-I4 cost import |
| P2-Q4 | ERP and procurement integration: stubs or real | I3 `POLineRef`, I4 material fulfilment |
| P2-Q5 | Inventory movements: records or events | I3 T02, T03, T04 (schema) |
| P2-Q6 | Simulator scenarios and how simulated people get roles | I6 T01; every increment's actor ticket |
| P2-Q7 | A generic commodity record for IWP scope until Phase 3 | I2 T01; I5 T02 |
| P2-Q8 | Expected links that have no record type yet (permit, ITP, model slice) | I2 T01, T06b |
| P2-Q9 | Where the `awp.*` and `materials.*` settings keys live | wave 0 |
| P2-Q10 | Delegation of the Phase 2 human gates | wave 0; every schema merge |
| P2-Q11 | PDF and QR dependencies for the IWP pack | I5 T07 |
| P2-Q12 | WBS and path of construction ownership (who edits cost control data) | I1 T03 |
| P2-Q13 | Subcontracted scope in Phase 2 (brief Q17) | I5 T10 |

---

## P2-Q1 — Rules-of-credit company package (brief Q16)

Brief §9 M3: `RulesOfCredit` is a company standard per commodity held in the schema registry (example weld: fit-up
30% / weld 60% / NDE accepted 10%). The GC's own standards and IWP sizing norms are unknown (Q16).

| Option | What it means | Cost |
|---|---|---|
| A. Sample package only | `co.acme.awp-roc@1.0.0.yaml` with scope item (I2's generic record), weld and bolted joint examples, loaded like a standards edition (`tl standards load` pattern), validated (weights sum to 100, states exist in the target workflow) | Nothing real is seeded; the GC's package is a second edition later |
| B. The GC's standard now | The owner supplies the GC's rules and sizing norms before I5; they become the first edition | Blocks I5 on an external input |
| C. Sample now, GC later, and `awp.rules_of_credit.set` picks the edition | A as the default; the setting (brief §30.5) names the edition in force per project; loading a second edition is the P1-I1 loader path | A plus one setting key |

**Recommended default: C.** The package is a human-gated fixture under `schema/fixtures/standards/`, approved
under P2-Q10. Sizing: `awp.iwp.size_hours` default `[60, 850]` (COAA) and `awp.iwp.ready_lead_weeks` 4 stay as the
brief says unless the owner changes them here.

## P2-Q2 — Who signs off an IWP release; a new role?

Brief: "IWPs are signed off before release to the field; sign-off roles are a setting (default: workface planner +
superintendent)". Phase 1 has `admin`, `document_controller`, `user` (ADR-0013). The workflow engine's `roles`
guard reads `TransitionWorkflow.actor_roles`, which a client sets in the request body (`request_model` strips
`actor` only), so it cannot carry a permission. Sign-off must be a module command with an access word, as every
controlling act is today.

| Option | What it means | Cost |
|---|---|---|
| A. Reuse `document_controller` | `SignOffIwp` and `IssueIwp` are `controller` commands; two distinct controllers (or an admin) sign; the setting holds the number of signatures, not roles | No auth change; a document controller releases field work, which misreads the role |
| B. One new role `workface_planner` | `ROLES` gains it (ADR-0013 mechanism: typed access word `planner`, action prefix `release.command.<Name>`, explicit action set from the command table, accounts screen key); sign-off needs two distinct holders of `workface_planner` or `admin`; `awp.release.signoff_roles` lists roles that exist and is validated against `ROLES` | One supervisor-built auth change with a human gate; the superintendent is a second planner account |
| C. Two new roles `workface_planner` and `superintendent` | As B with one signature from each, by distinct persons; the brief's default verbatim | Two roles; the accounts screen and the role rules grow; `superintendent` has no other act in Phase 2 |
| D. Per-project role assignment | A project-level role table (brief §8 RBAC per project) | A permission-model change the owner deferred to SSO (ADR-0013 known limits) |

**Recommended default: B.** It keeps one word per command (the ADR-0013 shape), names the person the COAA model
names, and leaves the superintendent as a second signer who holds the same role. The sign-off event carries the
record hash (brief §8 electronic signatures); re-authentication on sign is not built in Phase 2 (no password
re-entry over the API exists) and is noted as a limit. Whatever the choice, `actor_roles` over HTTP is reviewed as a
security item (`phase2-risks.md` R-P2-3): the recommended fix is that the API derives `actor_roles` from the
principal and refuses a body that carries it.

## P2-Q3 — Materials and requisition authority; a cost role

P1-I4 left `ImportCostSnapshot` admin-only ("the figures are money and Phase 1 has no cost role; a follow-up if the
owner wants one"). Phase 2 adds acts that move quantities and money: inventory adjust and scrap, requisition
approval, WBS allocation to cost codes, the progress export.

| Act | Option A: two tiers | Option B: a `cost_controller` role | Option C: a `materials_coordinator` role too |
|---|---|---|---|
| Receive, issue, transfer, return, reserve | `user` | `user` | `user` |
| Adjust, scrap, accept a receipt without MTR override | `admin` | `cost_controller` or admin | `materials_coordinator` or admin |
| Item library (company registry) | `admin` | `admin` | `materials_coordinator` or admin |
| Requisition approval | `admin` (material, labour), requester's `user` for general | `cost_controller` for material and labour | as B |
| WBS nodes, allocation %, path of construction | `admin` | `cost_controller` | `cost_controller` |
| Cost snapshot import (P1-I4) | `admin` (unchanged) | `cost_controller` | `cost_controller` |
| Progress export to the cost system | `admin` | `cost_controller` | `cost_controller` |

**Recommended default: A for Phase 2, with every act one word per command so B or C is a one-line change each.**
Reason: each new role is a gated auth change (ADR-0013 cost), and the Phase 2 demo team is small. If the owner
wants B, it is built in wave 0 together with P2-Q2's role in one auth increment (one review, one gate).

## P2-Q4 — ERP and procurement: stubs or real

`POLineRef` mirrors an external PO line; receipts reference it; the material requisition could raise a purchase
request. Brief Q1 (which cost system, API or file drop) is still open.

| Option | What it means |
|---|---|
| A. Stubs: `POLineRef` by hand and by CSV through the derivation pipeline (`target_kind: po_lines`); no outbound call | Nothing external; the P1-I3 path does the import |
| B. A plus inbound: the P1-I7 inbound endpoints map an ERP webhook (PO line created, promised date changed) to `RecordPoLine` | Real when the ERP can post; a staging test against a sandbox is the gate (brief §25.5) |
| C. A real connector (poll the ERP API) | Needs Q1 answered, credentials, a vault (X10 open) |

**Recommended default: A in I3, B in I6 if P1-I7 WS-A is on the trunk.** Nothing in Phase 2 calls out.

## P2-Q5 — Inventory movements: records or events

Brief §9 M4 lists `InventoryTransaction` as a record type with cross-references (lot, requisition, IWP, cost code,
person). On the ADR-0010 seam every record is a `cur_core_record` row (17 statements on Postgres, L-P0-I8D-1), a
feed card (R7) and a linkable node; a site posts thousands of movements a week.

| Option | What it means | Cost |
|---|---|---|
| A. Records, as the brief says | One record and one feed card per movement; links to IWP and requisition | Postgres write cost; feed noise; `cur_core_record` growth; the toolcrib "one line" screen writes a record and two links per keystroke |
| B. Events on the stock-lot stream with typed references (`iwp_id`, `requisition_id`, `cost_code_id`, `person`), projected into `cur_materials_movement`; a lot is the record | Cheap writes (one event, one projection row); the brief's cross-references become typed columns readable in the movement log and the query language; a movement is not a link target and has no thread | A deviation from brief §9 M4 recorded in an ADR; `linked:` filters do not see movements (they see lots and receipts) |

**Recommended default: B.** Receipts, lots, serialized items and requisitions stay records; a movement is what
happened to a lot. Brief §22.4 already treats quantities as deltas.

## P2-Q6 — Simulator scenarios and roles for simulated people

Simulated people sign in with dev tokens that carry `user` only (ADR-0009 §9); P1-I4 excuses controlling acts by
naming `operators` in the scenario (L-P1-I4-18). Phase 2 needs sign-off, issue, approval and adjust in the exit demo.

| Option | What it means |
|---|---|
| A. Operators only | The scenario names an operator for sign-off, issue, approval; actors do the `user` acts; `sim_assert` excuses the operators (at most 8) |
| B. Dev tokens carry the account's roles | A change to ADR-0009 §9 (a privilege path from the token file); then a simulated planner signs off |
| C. Session sign-in for one simulated identity | The connector signs one actor in with a password; the rest stay on tokens |

**Recommended default: A.** It is what P1-I4 built and tested, and it keeps the token rule. Scenario content for
the owner to confirm: `refinery-piping-medium` v2 with planner, materials coordinator, scaffold supervisor and
foreman actors; injections `material_late` (a receipt delayed N days), `scaffold_failed` (a red tag), and the
existing `design_revision` against pinned IWP drawings; rates seeded; `llm_share` 0 (ADR-0008 decision 8: no spend).

## P2-Q7 — A generic commodity record for IWP scope until Phase 3

Welds, joints and steel members are Phase 3 record types. An IWP needs scope items now (the I2 demo: 24 welds,
8 joints, 3 tags), and rules of credit need states to earn from.

| Option | What it means |
|---|---|
| A. `awp.ScopeItem`: commodity code, quantity and UOM, a three-state workflow (Planned → Installed → Verified), `belongs_to` the IWP; Phase 3 welds supersede them by link | One generic type; the rules-of-credit engine has states to read; Phase 3 adds types without changing the IWP |
| B. Tags only (`engineering.Tag`) | No quantities, no installation states; progress is manual |
| C. Extension types (§31) for welds and joints now | Bodies outside the ledger, no typed columns, no workflow guards |

**Recommended default: A.**

## P2-Q8 — Expected links without a record type yet

`tl:expects_link` on `IWP` at Issued names a permit-to-work; permits, ITP lines and model slices are Phase 3.

| Option | What it means |
|---|---|
| A. Declare the expectation now against a generic record type and report it as missing, not blocking | Data health shows the gap; issue is allowed |
| B. Declare it and make it a `required_links` guard on Issued | No IWP can be issued in Phase 2 without a stand-in permit record |
| C. Do not declare it until the type exists | Nothing shows |

**Recommended default: A** (and the readiness checks `permits_planned`, `inspections_planned`,
`model_slice_available` return `n_a` with a note, as I2 T06b says).

## P2-Q9 — Where the settings keys live

`register_definitions` serves extension types only; platform keys come from `schema/settings/platform.yaml`.
Phase 2 needs `awp.iwp.ready_lead_weeks`, `awp.backlog.target_weeks`, `awp.iwp.size_hours`,
`awp.release.signoff_roles`, `awp.rules_of_credit.set`, `awp.constraint.aging_days`,
`materials.receipt.mtr_required_categories`, `scaffold.inspection.interval_days`.

| Option | What it means |
|---|---|
| A. Add them to `platform.yaml` in wave 0 | One gated change; `lockable` and `scopes` per key as brief §30.1; no core change |
| B. A `ModuleSpec.settings` hook (keys namespaced by module name) | A core contract change (ADR); modules own their keys; the registry's reserved-namespace rule changes |

**Recommended default: A for Phase 2, B filed as a follow-up contract.**

## P2-Q10 — Delegation of the Phase 2 human gates

ADR-0008 decision 6 let the orchestrator approve every Phase 1 human gate (schema merges, clocks, filters, auth
details) and log each in `APPROVALS.md`; spend was not delegated.

| Option | What it means |
|---|---|
| A. Same delegation for Phase 2, same exclusions (spend, data migrations of existing data, copyleft licences) | The run goes to the Phase 2 exit without stopping |
| B. Delegate schema merges; the owner approves the roles (P2-Q2, P2-Q3) and the rules-of-credit package in person | Two stops: wave 0 and I5 T01 |
| C. Stop at each increment | Six stops |

**Recommended default: B.** The role change and the rules-of-credit package are the two decisions that reach outside
the system (who may release field work; how progress is earned and paid).

## P2-Q11 — PDF and QR for the IWP pack

The pack is "printable/PDF from a template". The licence gate (ADR-0006) refuses GPL, LGPL and AGPL.

| Option | Dependency | Licence |
|---|---|---|
| A. HTML pack only in Phase 2; print from the browser; PDF later | none | — |
| B. `reportlab` for PDF, `segno` for QR | reportlab (BSD-3), segno (BSD-3) | passes the gate as far as known; confirmed at `just check` |
| C. WeasyPrint | WeasyPrint (BSD-3) but it pulls Pyphen (GPL/LGPL/MPL tri-licence) | MPL only by the owner's allow-list (ADR-0006); a licence gate decision |

**Recommended default: A with B behind a flag** (the renderer emits HTML always; PDF when `reportlab` is installed
and allowed). QR codes as deep links (brief §19.1) use `segno` or an inline SVG writer.

## P2-Q12 — WBS and path of construction ownership

The GC's WBS and schedule of values are cost control data mapped to cost codes with allocation percentages.

| Option | Who edits |
|---|---|
| A. `admin` (as the engineering registry and the cost import today) | Cost control is an admin in the demo team |
| B. `cost_controller` (with P2-Q3 option B) | A role |
| C. Any `user`, with the rollup as the check | Open; allocation errors reach the cost export |

**Recommended default: A** (B if P2-Q3 chooses a cost role). CWPs, CWAs and IWPs stay `user` acts.

## P2-Q13 — Subcontracted scope in Phase 2 (brief Q17)

External-party access and guest links are Phase 3. I5 T10 assigns a CWP or IWP to a subcontractor party and
records progress.

| Option | What it means |
|---|---|
| A. Party assignment, interface constraints, progress by CSV import (envelope) and by an inbound webhook mapping when P1-I7 is on the trunk; no accounts | What the plan says |
| B. Subcontractor accounts with the `user` role now | No ABAC exists: a subcontractor would see every project (brief Q6, ADR-0008 decision 3) |

**Recommended default: A.**
