# M3 — Field work packaging (GC WBS and AWP / workface planning)

Brief §9 M3, §10.6 sketch 5, §12, §16 Phase 2. Plan `08-phase2-plan.md` I1, I2, I5, I6. Status: design v0.1.

## Users and stories
Workface planner, superintendent, general foreman, foreman, area manager, cost controller, materials and scaffold
coordinators (read), subcontractor (Phase 3 party access).
- As a **workface planner** I build an IWP for one crew and a two-week window from a CWP's scope, pin its drawings,
  and see every constraint between it and the field, with an owner and a need-by date on each.
- As a **superintendent** I sign off the Ready IWPs each week knowing every check is green or named `n/a`, and who
  cleared what.
- As a **foreman** I receive an issued IWP pack, commit to the week's work, and record what was done and why not.
- As a **cost controller** I see hours and quantities earned per cost code from the linked field records without
  anyone typing progress.

## Records and states
| Record | States |
|---|---|
| `WBSNode`, `PathOfConstruction` (versioned), `CWA` | No workflow; admin edits, every change an event |
| `CWP` | Planned → In development → Released for IWP development → Executing → Complete → Closed |
| `EWPRef`, `PWPRef` | Mirror of the owner's package: dates and status only; `constraint_source` flag |
| `IWP` | Draft → In development → Constraint check → Ready → Issued → In progress → Field complete → Closed; side states On hold, Split, Cancelled |
| `ScopeItem` (P2-Q7) | Generic commodity line until welds and joints exist; Planned → Done, earns by rules of credit |
| `Constraint` | Open → Assigned → Cleared; Void. Source `manual`, `check`, `rule`, `feed_hold`, `thread_hold` |
| `WeeklyPlan` | Draft → Committed → Closed (PPC recorded) |
| `IWPCloseout` | Part of IWP Closed: actual hours file, redlines slot, remaining punch, feedback |
| `RulesOfCredit` | Company package in the schema registry (P2-Q1); `LookAhead` is a read, not a record |

## Logs and record screens (log standard)
**IWP log** (the module's home). Columns: Number, Subject, State, Discipline, Foreman, Planned start, Ready
(`5/7`), Constraints (open), Hours. Filters: `m` mine (foreman), `r` Ready only, `b` backlog by foreman, by CWA.
Panel: identity `P123-IWP-PIP-0042 · Rack 12 tie-ins`; state `Constraint check · since 2026-10-28`; summary
`Piping · crew J. Soto · 2026-11-03 to 11-14 · 420 h`. Sections: Readiness (table Check, State, Resolve via; `n/a`
counted apart), Constraints (table Type, Owner, Need by, Age, Source), Scope (counts by commodity, earned %),
Drawings (pinned revisions, stale in red with `!`), Timeline, Files (pack, redlines), Links.
Actions per state (planner unless said): Draft and In development: Add scope, Pin drawing, Raise constraint, Split,
Request check. Constraint check: Re-evaluate, Raise constraint, Clear constraint (constraint owner, with the
resolving record). Ready: Sign off (`awp.release.signoff_roles`, two distinct signers), Hold. Issued: Start, Hold.
In progress: Record progress, Commit week, Hold. Field complete: Close out. Any: Cancel (planner), Open thread.
Agents: propose constraint, propose scope.
**CWP register.** Number, Subject, State, Discipline, CWA, Planned start, IWPs (`3 ready / 8`), Earned %. Panel
sections: Scope (budget hours and quantities), Packages (table of IWPs), References (EWP and PWP mirrors with
forecast dates), Schedule (activities), Cost (WBS nodes with allocation %), Files, Links.
**Constraint review.** One log grouped by owner then type: Constraint, IWP, Type, Owner, Need by, Age, Source.
Actions: Assign, Clear, Escalate (notify), Open IWP. The weekly constraint meeting runs from this screen.
**WBS tree and path of construction** (admin, cost control): tree with cost-code allocation; sequence editor with
versions readable side by side.
**Weekly cycle** (six screens reached from one menu): 1 Look-ahead (next four weeks of activities with their IWPs
and readiness), 2 Constraint review, 3 Release (Ready IWPs with sign-off), 4 Commitments (foreman per IWP),
5 Progress and PPC, 6 Closeout. Each is a log or a form; none holds logic.
**Tiles:** backlog weeks per foreman, % released constraint-free, constraints by age, IWPs issued with stale pins.

## Workflows and approvals
- Readiness: plug-in checks `documents_current`, `rfis_answered`, `materials_reserved`, `scaffold_tagged`,
  `labour_requested`, `permits_planned`, `inspections_planned`, `predecessors_handed_over`, `model_slice_available`;
  each `ok / blocked / n_a / unknown`; the release refuses `unknown`, tolerates `n_a` only if the setting allows.
- Release sign-off: a module command with the record hash, two distinct signers (P2-Q2); never a `roles` guard.
- New constraint on an Issued IWP puts it On hold; a check clears only what a check raised; a person's clear of a
  check-raised constraint carries a reason and suppresses re-raise until the facts change (R-P2-11).
- Sizing warning from `awp.iwp.size_hours`; split by scope items or hours.
- Progress earned from linked record states through rules of credit; manual entry only for commodities without
  records; rollup IWP → CWP → WBS → cost code, exported as CSV per period.
- Closeout needs the actual-hours file, feedback and a remaining-punch count.

## Links to other modules
Documents (pins, stale pins → documents check); RFIs (open with impact → proposed constraint; answered → check);
materials (reservations, shortages → constraint); scaffold and labour requisitions (M9 checks); permits (expected
link, `n_a` until a type exists, P2-Q8); cost codes (WBS allocation, earned export); schedule (activity links,
look-ahead); tags (scope); quality (ITP lines and inspections planned, Phase 3); piping (welds supersede scope
items, Phase 3); models (slice per IWP, Phase 3); subcontractor party (Phase 3).

## Integrations
Webhooks `IWP.Ready`, `IWP.Issued`, `IWP.ReadinessEvaluated` (low importance). Rule: RFI impact flag → propose
constraint. Feed `#hold` → constraint proposal. Threads `/hold`, `/release`, `/dispatch scaffold-erect`,
`/dispatch material-request`, `/raise constraint`. MCP read tools and `propose_constraint`, `propose_iwp_scope`.
Inbound subcontractor progress (CSV first, endpoint mapping when a party has a system). Progress export to the cost
system is a file a person sends (R-P2-9).

## Reports (§12)
CWP/IWP status; readiness and constraint log; constraints by type, owner, age; backlog weeks; PPC; earned vs burned;
IWP schedule compliance; IWPs issued with stale pins. Lake: readiness history, schedule vs readiness.

## Confidentiality and roles
All M3 records `internal`; no restricted IWPs. A subcontractor sees the CWPs and IWPs assigned to its party and one
hop below (Phase 3 party scope). Roles: planner builds and issues (`user` today; a `workface_planner` role is
P2-Q2); sign-off per `awp.release.signoff_roles`; WBS and path are admin (P2-Q12); foreman is `user` with the mine
filter; agents propose only. **(proposed)** A foreman's TUI lands on the IWP log filtered to mine.

## First increment vs later
First (Phase 2): I1 WBS, path, CWA, CWP, EWP/PWP mirrors, allocation rollup; I2 IWP, scope items, constraints,
readiness engine and checks, sign-off, issue, `IWP.Ready`; I5 weekly cycle, rules of credit, progress, IWP pack
(HTML; PDF per P2-Q11), closeout, KPIs; I6 marts and the exit demo.
Later: permits as a record type; welds, joints and ITP lines replace scope items and `n_a` checks (Phase 3); model
slice in the pack (Phase 3); subcontractor portal (Phase 3); P6 progress write-back (Phase 5); mobile pack (Phase 5).

## Open questions for the owner
P2-Q1 rules of credit; P2-Q2 who signs off and whether that is a role; P2-Q7 generic scope items; P2-Q12 who owns
WBS; P2-Q13 subcontracted scope in Phase 2; P2-Q11 PDF packs. New: may a person waive a check-raised constraint, and
with what access? Should the foreman's landing screen be the mine-filtered IWP log **(proposed)**? Is a four-week
ready lead time the GC's norm (`awp.iwp.ready_lead_weeks`)?
