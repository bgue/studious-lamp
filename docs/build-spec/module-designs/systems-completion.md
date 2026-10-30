# M8 — Systems completion and turnover

Brief §9 M8, §12, §16 Phase 4 exit ("subsystem MC certificate with snapshot and dossier export"), §24.4 (bundles).
Plan `10-phase4-plan.md` I1 (systems, ITRs, punch), I2 (certificates, dossiers, dashboards), I3 (exit).
Status: design v0.1.

## Users and stories
Completions engineer or manager, commissioning lead, QC (ITRs), punch coordinator, client or owner's commissioning
team (co-signature), document control (dossiers), discipline leads.
- As a **completions engineer** I assign tags to subsystems and the A, B and C check sheets generate themselves per
  tag class, so I know exactly how many ITRs stand between 47-01 and mechanical completion.
- As a **QC technician** I complete an ITR on the tag with the instruments I used and someone else verifies it.
- As a **commissioning lead** I issue the MC certificate only when every ITR is complete, punch A is closed and the
  test packages passed, and the certificate records a snapshot of what it was signed over.
- As a **document controller** I build the handover dossier and export it as a package the client can open.

## Records and states
| Record | States |
|---|---|
| `System` / `Subsystem` | Defined → Mechanically complete → Ready for commissioning → Ready for start-up → Handed over (each step by a certificate); priority and planned dates |
| `ITRTemplate` (A, B, C as versioned question sets) | Draft → Published → Retired |
| `ITR` | Generated → In progress → Completed → Verified; Void (template version change or tag removed) |
| `Punch` | The M5 `Deficiency` with kind `punch`, category A, B, C (shared record) |
| `Certificate` (MC, RFC, RFSU, handover) | Draft → Prerequisites met → Issued (signed, snapshot hash) → Superseded |
| `HandoverDossier` | Building → Complete → Exported |

## Logs and record screens (log standard)
**System tree** (home): System › Subsystem with counts (ITRs done/total, punch A/B open, certificates). Enter opens
the subsystem log row.
**Subsystem log.** Columns: Number, Description, State, Priority, RFC planned, ITRs (`118/140`), Punch A, Punch B,
Test packages (`5/6`), Certificates. Filters by system, priority, `b` behind plan. Panel: identity `47-01 · Cooling
water supply`; state `Mechanically complete · since 2026-12-02`; summary `Priority 1 · RFC planned 2027-02-14 · 47
tags · 6 test packages`. Sections: Progress (table Phase, ITRs done, total, %), Punch (by category), Test packages
(table), Certificates (table Type, State, Issued, Signed by), Boundary drawings (pinned), Timeline, Links.
Actions: Assign tags, lines, test packages (completions engineer); Generate ITRs; Evaluate prerequisites; Open
thread.
**ITR log.** Number, Tag, Template, Phase, State, Discipline, Completed by, Verified by. Filters by subsystem, phase,
discipline, mine. Actions: Generated: Start. In progress: Complete (instruments). Completed: Verify (a different
person), Reopen. Any: Raise punch, Void (controller).
**ITR runner** = the M5 checklist runner over the template's questions, with the tag and subsystem prefilled.
**Punch by subsystem** = the M5 deficiency log filtered by subsystem and kind punch; the walkdown screen prefills the
subsystem.
**Certificate log.** Number, Subsystem, Type, State, Issued, Signed by, Snapshot (technical). Panel sections:
Prerequisites (readiness table Check, State, Resolve via: `itrs_complete`, `punch_a_closed`, `test_packages_passed`,
`documents_current`), Signatories, Snapshot (what was signed over, counts), Files (certificate), Timeline. Actions:
Draft: Evaluate prerequisites. Prerequisites met: Issue and sign (role per Q4; re-authentication), Request client
signature (guest link). Issued: Supersede.
**Dossier log.** Subsystem, State, Completeness %, Missing (n). Panel: Index (sections and counts), Missing items
(table), Export (file). Actions: Build, Rebuild, Export (admin or controller).
**Completion dashboards** (tiles): ITRs by status and discipline, punch by category, test packages, certificates,
burn-down by subsystem (planned vs actual ITR completion per week).

## Workflows and approvals
ITR auto-generation per tag class × phase on tag assignment and on template version change (old ITRs voided and
regenerated with a link); completion and verification by different people **(proposed)**; certificate
prerequisites by the Phase 2 readiness engine with subject `completions.Certificate`; snapshot at signing: a hash of
the supporting record set (ITRs, punch, test packages, documents) stored on the certificate and refused on drift;
e-signature with re-authentication (Q4); dossier builder job compiles documents, ITR reports, test certificates and
certificates into an indexed package in the object store and an export zip; the handover bundle excludes
confidentiality classes (§24.4).

## Links to other modules
Tags and tag classes (M2; ITR templates per class); lines and test packages (M6, M7); punch (M5); documents (boundary
drawings, certificates, dossier contents); P6 activities (RFC and RFSU dates vs plan); models (overlay ITR status by
subsystem; slice per subsystem); correspondence (handover letters, client notices); external party (client
co-signature); cost codes (none directly).

## Integrations
Webhooks `Certificate.Issued`, `ITR.Verified`, `Subsystem.StateChanged`. Guest link or portal: client co-signature
and dossier download. MCP read tools (subsystem progress, certificates). Legacy loader: completions database export
(Phase 4 I3). Lake: completions burn-down mart. Feed cards on certificate issue and subsystem state.

## Reports (§12)
ITR status by system, subsystem and discipline; punch by category; MC and RFC certificates; completion burn-down;
handover dossier completeness.

## Confidentiality and roles
All records `internal`; the dossier export leaves out `restricted` and `privileged` content and says so in its index.
Complete an ITR: `user`; verify: a different `user`; assign and generate: completions engineer (`user` today; a role
if the owner wants); void an ITR, issue a certificate: `controller` or the Q4 role; dossier export: admin or
controller; client signatory: external party. Agents read only.

## First increment vs later
First (Phase 4): I1 systems and subsystems, templates, ITR generation, ITR runner over the checklist runner, punch by
subsystem, projections and reports; I2 certificate workflow with prerequisites and snapshot, e-signature, dossier
builder and export, dashboards, lake mart.
Later: preservation routines; vendor ITRs by party; client certificate forms per contract; dossier index as PDF;
RFSU procedures; PWA ITR completion (Phase 5).

## Open questions for the owner
Q4 e-signature requirements per jurisdiction and client; who signs each certificate type and whether the client
co-signs. New: must the verifier differ from the completer **(proposed yes)**? Is a certificate also a registered
document? Does the client's completions system (if any) need an export format beyond the dossier zip?
