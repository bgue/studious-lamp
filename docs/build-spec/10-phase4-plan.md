# Build spec 10 — Phase 4 plan: Completions and turnover

Brief: §16 Phase 4. M8 systems completion, ITRs, certificates, handover dossiers; completion dashboards.
Three increments. IDs `P4-I<n>-T<nn>`.

**Phase exit (§16):** a subsystem MC certificate with snapshot and dossier export.
**Human gates:** module schema merges; certificate signature rules (Q4).

## Increment 1 — Systems, subsystems, ITR templates, ITR generation, punch

**Demo:** define system 47 with subsystems 47-01, 47-02; assign tags; ITRs auto-generate per tag class × phase A/B/C;
complete and verify ITRs; punch items by category roll up per subsystem.
**Fanout:** no. **Supervisor builds:** T02, T04 (auto-generation rules).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Fixtures: ITR template forms as psets (A/B/C), system/subsystem numbering pattern | H | — |
| T02 | LinkML `completions.yaml`: `System`, `Subsystem`, `ITRTemplate`, `ITR`, `Certificate`, `HandoverDossier`; `Punch` shared with Deficiency | S | T01 |
| T03 | Commands: assign tags/lines/test packages to subsystems; ITR complete/verify with instruments | H | T02 |
| T04 | ITR auto-generation per tag class × phase on assignment and on template version change | S | T03 |
| T05 | Projectors: ITR status by subsystem/discipline, punch by category, test packages per subsystem | H | T03 |
| T06 | TUI: system tree, subsystem record, ITR runner (reuse checklist runner), punch list by subsystem | H | T05 |
| T07 | Reports: ITR status, punch by category; demo; report | H | T06 |

## Increment 2 — Certificates, dossiers, dashboards

**Demo:** MC certificate for 47-01 blocked by open punch A; clear it; issue with a snapshot hash of the supporting set;
dossier builder compiles documents, ITRs, test packages, certificates into an indexed package in the object store.
**Fanout (orchestrator):** WS-A certificates + dossier; WS-B dashboards. Contract: certificate prerequisite check interface.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | Certificate workflow with prerequisite checks (ITRs complete, punch A closed, test packages passed) via readiness engine | S | — |
| A | T02 | Snapshot at signing: hash of supporting record set, stored on the certificate; e-signature | S | T01 |
| A | T03 | Dossier builder job: index, contents, completeness, package in object store, export zip | H | T02 |
| A | T04 | Handover bundle excludes confidentiality classes per §24.4 | H | T03 |
| B | T05 | Completion dashboards: ITRs by status, punch by category, test packages, certificates, burn-down by subsystem | H | — |
| B | T06 | Lake gold marts: completions burn-down | H | — |
| A | T07 | Reports: MC/RFC certificates, dossier completeness; demo; report | H | T05 |

## Increment 3 — Simulation, reports, Phase 4 exit

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Simulator completions-engineer actor; scenario assertions on burn-down | H | — |
| T02 | Legacy loader: completions database export | H | — |
| T03 | Phase-exit demo: subsystem MC certificate with snapshot and dossier export on a simulated project | H | T01 |
| T04 | Phase report, risk register, ADRs (orchestrator) | O | T03 |
