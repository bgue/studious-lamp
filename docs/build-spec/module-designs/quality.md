# M5 — Quality control and quality management

Brief §9 M5, §10.5 (checklist runner, punch walkdown), §12, §16 Phase 3. Plan `09-phase3-plan.md` I1 (Issue engine,
NCR/CAR/QSR, Quality domain) and I2 (ITPs, checklists, inspections, deficiencies, calibration). Status: design v0.1.
**(proposed)** Build I2 before I1 (README §2 row 5).

## Users and stories
QC inspector, QA manager, welding and piping QC supervisor, calibration coordinator, client inspector (witness),
subcontractor QC, every user (raise a deficiency).
- As a **QC inspector** I run a checklist inspection question by question with a calibrated instrument and raise a
  deficiency in two keystrokes from whatever I am looking at.
- As a **QA manager** I raise an NCR against the affected welds, record the disposition, and cannot close it until the
  corrective action's effectiveness is checked.
- As a **calibration coordinator** I fail an instrument's calibration and see every inspection and test it touched
  since its last good one, and link them to an NCR in one step.
- As a **client inspector** I witness a hold point and sign it off from a link without an account.

## Records and states
| Record | States |
|---|---|
| `NCR` | Raised → Under review → Dispositioned (use as is, repair, rework, reject) → Corrected → Verified → Closed; Rejected |
| `CAR` | Raised → Root cause → Actions agreed → Actions done → Effectiveness checked → Closed |
| `QSR` | Draft → Issued → Findings raised → Closed; `Audit` (v1.x) Planned → Done → Closed |
| `ITP` / `ITPLine` (points H, W, R, S per party) | Draft → Approved → Superseded |
| `ChecklistTemplate` (questions as a versioned pset definition) | Draft → Published → Retired |
| `Inspection` | Planned → Scheduled → Done (Accept, Reject, Conditional) → Verified; Cancelled |
| `Deficiency` (`kind` deficiency or punch; category A, B, C) | Open → Assigned → Fixed → Cleared (clearing inspection); Cancelled |
| `Instrument`, `CalibrationRecord` | In calibration → Due → Overdue → Failed; Retired |

## Logs and record screens (log standard)
**NCR register** (and one register per issue kind, Kind column when mixed). Columns: Number, Subject, State,
Severity, Raised, Due, Owner, Disposition, Against (count). Filters: `o` open, `v` overdue, mine. Panel: identity
`P123-NCR-0042 · Porosity on 6" BW welds, ISO-1234`; state `Under review · due 2026-11-07 · 3 days left`; summary
`Welding · Acme Fab · 4 welds · disposition pending`. Sections: Nonconformance (text), Disposition (text, method,
approvals), Affected records (table Record, Type, State), Corrective action (CAR), Correspondence (Quality-domain
items), Timeline, Files (photos, reports), Links.
Actions: Raised: Review, Bulk link affected. Under review: Disposition (controller). Dispositioned: Record
correction, Raise CAR, Issue notification (Quality domain). Corrected: Verify (a person other than the corrector,
**proposed** separation). Verified: Close (guards: CAR effectiveness checked, no open deficiencies). Any: Assign,
Escalate, Open thread.
**Inspection log.** Number, Subject (what is inspected), State, Type, Point (H/W/R/S), Scheduled, Inspector, Result.
Panel sections: Scope (record, ITP line, acceptance criteria), Responses (checklist as a table Question, Answer,
Note), Instruments (table with calibration state), Witnesses, Deficiencies raised, Files, Timeline. Actions:
Planned: Schedule. Scheduled: Run checklist, Record result (past-due instrument refused or warned by
`quality.calibration.block_mode`), Add witness. Done: Raise deficiency, Verify.
**Deficiency and punch aging.** Number, Subject, State, Cat, Against, Responsible, Due, Age, Subsystem. Filters by
category, subsystem, responsible, `w` walkdown mode. Actions: Assign, Mark fixed, Clear (with the clearing
inspection), Escalate to NCR.
**ITP compliance.** Per ITP: Line, Activity, Point, Planned, Done, Open deficiencies. **Calibration due.**
Instrument, Type, Due, State, Used in (inspections since last good). Action Fail calibration opens the **impact
screen**: a log of every inspection and test since the last good calibration with one action, Link all to an NCR.
**Fast entry:** checklist runner (one question per screen, keys for answers, note and photo slot); punch walkdown
(location and system prefilled from the last item, `d` raises the next one).
**Tiles:** open NCRs by age, punch A open by subsystem, inspections due this week, instruments overdue.

## Workflows and approvals
Issue engine shared by NCR, CAR, QSR, Audit: numbering per kind, assignment, due dates and response cycles on the
project calendar (the correspondence clock arithmetic, P3-Q2), escalation, closure guards. Formal exchanges with
clients and subcontractors are Quality-domain correspondence items linked by `related_issue`. Calibration impact
analysis with bulk link. Past-due instrument block hard or soft (P3-Q6). A deficiency from any record carries
`raised_against` and `derived from` a feed post or thread message when it started there.

## Links to other modules
Welds, joints, spools (inspected records, NCR on NDE reject); IWP (ITP lines → `inspections_planned` check);
receipts (receiving inspection); scaffold inspections (M9); test packages (punch A closed check); subsystems and ITRs
(M8 reuses the checklist runner and punch); documents (specs, procedures, certificates pinned); RFIs (visible from
quality, raised from an NCR); tags and tag classes (checklist templates per class); equipment ↔ instrument (M4);
cost codes (rework); models (viewpoint on an NCR or punch); external party (responsible, witness).

## Integrations
Threads `/raise ncr | punch | inspection`. Webhooks `NCR.Raised`, `NCR.Dispositioned`, `Inspection.Recorded`,
`Deficiency.Cleared`, `Calibration.Failed`. Rule: calibration failed → propose an NCR (or the impact screen's
command when rules are propose-only). MCP read tools; proposable `propose_ncr`, `propose_deficiency`. Guest links:
witness sign-off, NCR response by a subcontractor (Phase 3 I8). Feed cards on raise, disposition, clear.

## Reports (§12)
Inspection log; ITP compliance; deficiency and punch aging; NCR, CAR, QSR registers and trends; RFI log (M10);
calibration due and overdue; calibration impact. Lake: inspection log, NDE and NCR trends by subcontractor.

## Confidentiality and roles
Internal records are `internal`; client-facing NCR notifications take the Quality domain's class; a subcontractor
sees the issues and deficiencies where its party is responsible (Phase 3). Record an inspection or raise a
deficiency: `user`. Disposition, fail calibration, close an NCR: `controller` today; **(proposed)** a `quality`
role if the owner wants QA separate from document control. Witness: external party or guest link. Agents propose.

## First increment vs later
First (Phase 3): I2 ITPs, checklist templates, inspections, deficiencies and punch, instruments, calibration,
impact analysis, the `d` key, checklist runner and walkdown screens, `inspections_planned` check; I1 Issue engine,
NCR, CAR, QSR, Quality domain file and letter templates, `/raise ncr`.
Later: Audit; QSR trends by subcontractor; HSE domain (I8); ITRs (Phase 4); photo slots with a metadata pset
(before, after, direction); checklist and walkdown on mobile and offline (Phase 3 I5, Phase 5).

## Open questions for the owner
P3-Q2 clock reuse; P3-Q6 hard or soft blocks; P3-Q4 witness by guest link or account. New: is a `quality` role
wanted for disposition and closure, and must the verifier differ from the corrector? Are the GC's QC forms expressible
as versioned question sets (psets), or do some need free layouts? Should inspections and deficiencies be built before
the Issue engine (README §2)?
