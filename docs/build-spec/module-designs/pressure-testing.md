# M7 — Pressure testing

Brief §9 M7, §12, §16 Phase 3 exit ("weld → NDE → test package → certificate"). Plan `09-phase3-plan.md` I4.
Status: design v0.1.

## Users and stories
Test coordinator or test engineer, QC, piping superintendent, bolting crew (reinstatement), client witness,
document control (certificate register).
- As a **test coordinator** I assemble a test package over lines and isos, and its readiness tells me which welds
  still lack NDE, which joints are not torqued, which punch A items are open and which gauges are out of
  calibration, with a jump to each.
- As a **QC inspector** I record the test with the gauges used, the chart and the witnesses, and the certificate is
  generated from the template and signed.
- As a **bolting foreman** I see the joints broken for the test and record their remake so the package can close.
- As a **client witness** I sign the test from a link on my phone.

## Records and states
| Record | States |
|---|---|
| `TestPackage` | Draft → Assembled (limits defined) → Readiness check → Ready → Pre-test checked → Tested (pass or fail) → Certified → Reinstated → Closed; side On hold, Void |
| `PreTestChecklist` | A checklist inspection (M5 runner): walkdown, documentation, NDE, PWHT, punch A |
| `PressureTest` | Scheduled → Executed → Accepted / Failed (a failed test leaves the package Ready for a retest) |
| `Reinstatement` | Open → Complete (joints remade, blinds removed, items reinstalled) |
| Certificate | A file in slot `certificate` with a signature event; **(proposed)** also registered as an M1 Document of type `test certificate` so it has a number and transmits |

## Logs and record screens (log standard)
**Test package log** (home). Columns: Number, Subject, State, Medium, Pressure, Lines, Ready (`4/6`), Punch A, Test
date, Subsystem. Filters: `r` ready, `t` tested this week, by subsystem. Panel: identity `P123-TP-0031 · Rack 12
cooling water supply`; state `Readiness check · 4 of 6 checks ok`; summary `Hydro · 150 barg · 4 lines · subsystem
47-01 · witness Meridian`. Sections: Readiness (table Check, State, Resolve via: `welds_accepted`, `nde_complete`,
`joints_in_state`, `punch_a_closed`, `documents_current`, `gauges_calibrated`), Limits (lines and isos with pinned
revisions, isolation and blind list, instruments to remove), Tests (table Date, Pressure, Hold, Result, Witness),
Punch (open by category), Certificate, Reinstatement (joints table Joint, State, Remade), Timeline, Files (chart,
certificate, limit drawing), Links.
Actions: Draft: Add lines and isos, Define limits, Add isolation item. Assembled: Evaluate readiness. Readiness
check: Re-evaluate, Hold. Ready: Run pre-test checklist, Schedule test. Pre-test checked: Execute test (guards:
gauges in calibration, witnesses named). Tested pass: Generate certificate, Sign (P3-Q5 role, re-authentication).
Certified: Start reinstatement. Reinstated: Close. Any: Hold, Void (controller), Open thread.
**Readiness screen** is the same component as the IWP's (readiness subject `testing.TestPackage`).
**Test execution form**: date, pressure, hold time, temperatures, gauges and recorders (lookup limited to
calibrated instruments), chart upload, witnesses, result.
**Reinstatement screen**: joints broken for the test with Remake (opens the M6 boltup entry) and blinds removed.
**Certificate view**: the rendered certificate with its signature line, snapshot hash in technical mode.
**Tiles:** packages ready to test, tests this week, certificates awaiting signature, reinstatement outstanding.

## Workflows and approvals
Readiness computed by the Phase 2 engine with the six checks above; `TestPackage.Ready` on the first all-green
evaluation; pre-test checklist is an M5 checklist inspection; test execution refuses an instrument past due (hard
or soft per `quality.calibration.block_mode`); certificate rendered from a repository template (the Phase 2 pack
renderer; HTML, PDF per P2-Q11) with the hash of the supporting record set; `SignCertificate` needs the
re-authentication check and refuses when the set has moved; reinstatement links joints and boltup records; closing
needs reinstatement complete. A failed test keeps the history and allows a retest after the fix.

## Links to other modules
Piping (lines, isos, welds, joints; break and remake); quality (punch A, pre-test checklist, instruments); documents
(limit drawings pinned, chart, certificate); subsystems (M8 certificate prerequisite "test packages passed"); IWP
(a test IWP may contain the package); models (slice per test package, overlay by package state); correspondence
(witness notice to the client as a Document-control or General item); external party (witness).

## Integrations
Webhooks `TestPackage.Ready`, `PressureTest.Recorded`, `Certificate.Signed`. Guest link: client witness sign-off
(Phase 3 I8). Threads `/hold`, `/release`, `/raise punch`. MCP read tools (package readiness, certificates). Feed cards
on ready, tested, certified.

## Reports (§12)
Test package status and readiness; test certificates; reinstatement status. Lake: packages tested per week, time from
ready to tested.

## Confidentiality and roles
All records `internal`; a client's witness link sees one package. Assemble and execute: `user`; void and sign:
`controller` or the role P3-Q5 names; witness: external party. Agents read only.

## First increment vs later
First (Phase 3 I4): packages, limits, readiness checks, pre-test checklist, test execution, certificate generation
and signature, reinstatement, register and record screens, reports, `TestPackage.Ready`.
Later: pneumatic test exclusion-zone and permit psets; service and leak tests as further test types; certificate
PDF; retest statistics; client co-signature on the certificate (Phase 3 I8); package slices on mobile (Phase 5).

## Open questions for the owner
P3-Q5 who signs and what re-authentication means (a session-age window is the stub); P3-Q4 witness by guest link.
New: is the certificate also a registered document with a number **(proposed)**? Which test types beyond hydro and
pneumatic are needed in v1? Does the client require its own certificate form per contract (a template per project)?
