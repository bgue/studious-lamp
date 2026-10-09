# Build spec 09 — Phase 3 plan: Quality and piping

Brief: §16 Phase 3. M5 quality, M6 piping, M7 pressure testing, offline replicas (§22), M12 models (§23), external
parties (§18.11), fast-entry screens (§10.5), remaining correspondence domains. Eight increments. IDs `P3-I<n>-T<nn>`.

**Phase exit (§16):** weld → NDE → test package → certificate end to end; progress colour-overlaid in the model; NDE
contractor results arrive by inbound webhook.
**Human gates:** module schema merges; replica revocation and encryption (security); external-party ABAC (security);
xeokit licence (Q9) before any customer distribution; Legal domain confidentiality (legal lead).

---

## Increment 1 — M5 Issue engine, NCR/CAR/QSR, Quality correspondence domain

**Demo:** raise an NCR against three welds (generic records until I3) with disposition `repair`; a CAR addresses it;
a Quality-domain NCR notification to the client is issued and linked; closure requires the CAR effectiveness check.
**Fanout:** no. **Supervisor builds:** T02, T03 (Issue engine).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Fixtures: dispositions, root-cause methods, punch categories, priority codes | H | — |
| T02 | LinkML `quality.yaml` part 1: `NCR`, `CAR`, `QSR`, `Audit` (optional) sharing `Issue` base; workflows | S | T01 |
| T03 | Issue engine: numbering, assignment, due dates, response cycles, escalation, closure guards | S | T02 |
| T04 | NCR/CAR/QSR commands, projectors, registers; bulk link from selection | H | T03 |
| T05 | Quality correspondence domain (NCR notification, CAR request, quality notice, audit letter) linked to internal records | H | T03 |
| T06 | TUI: issue registers and records; `d`-style raise-from-anywhere for NCR | H | T04 |
| T07 | Reports: NCR/CAR/QSR registers and trends; simulator QC-inspector actor v1; demo; report | H | T06 |

## Increment 2 — ITPs, checklists, inspections, deficiencies, calibration

**Demo:** an ITP with H/W/R/S points; run a checklist inspection with a calibrated instrument; raise a deficiency in two
keystrokes; fail the instrument's calibration → impact analysis lists the inspection → one-click NCR.
**Fanout (orchestrator):** WS-A records and engine; WS-B checklist runner + punch walkdown screens. Contract: checklist pset → form metadata.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML part 2: `ITP/ITPLine`, `ChecklistTemplate` (pset-defined), `Inspection`, `Deficiency/Punch`, `Instrument`, `CalibrationRecord` | S | — |
| A | T02 | Inspection commands: schedule, record result + checklist responses, witness parties, instruments used | H | T01 |
| A | T03 | Deficiency raise-from-any-record (`d`), responsible party, due, clearing inspection; shared with Punch | H | T01 |
| A | T04 | Calibration: records, due lists, hard/soft block on past-due instruments (setting), impact analysis query → bulk NCR link | S | T02 |
| A | T05 | ITP compliance projection (planned vs done per line) | H | T02 |
| B | T06 | Checklist runner screen (question-by-question, keyboard answers) | H | contract |
| B | T07 | Punch walkdown fast-entry screen with location/system prefill | H | contract |
| B | T08 | Inspection log and deficiency aging screens | H | A T03 |
| A | T09 | Reports: inspection log, ITP compliance, deficiency aging, calibration due, calibration impact; demo; report | H | T08 |

## Increment 3 — M6 lines, isos, spools, welds, NDE, welder qualifications

**Demo:** import a weld map from a derived iso; weld daily log entry checks welder continuity and WPS; NDE selection by
piping class %; RT rejects via inbound webhook create repair welds and penalty selection.
**Fanout (orchestrator):** WS-A records + NDE rules; WS-B weld daily log + inbound NDE mapping. Contract: `NDESelectionRule` shape.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `piping.yaml` part 1: `Line`, `Isometric`, `Spool`, `Weld`, `WelderQualification`, `NDERequest/NDEResult`; spatial paths (`weld → spool, iso, line`); expected links (WPS @Welded) | S | — |
| A | T02 | Projectors with denormalised columns (`spool_key`, `iso_key`, `iso_rev`, `line_key`, `iwp_key`, `test_package_key`) | H | T01 |
| A | T03 | Weld commands: fit-up, weld, visual, PWHT, repair (links original), with welder qualification and continuity checks | H | T02 |
| A | T04 | NDE selection engine: % per class, lots, penalty selection on rejects | S | T03 |
| A | T05 | Weld map import from derived iso data; numbering validation | H | T02 |
| A | T06 | Progress quantities (count, inch-dia) → rules of credit → IWP/CWP/cost code | H | T03 |
| B | T07 | Weld daily log fast-entry grid by iso | H | A T03 |
| B | T08 | Inbound NDE results mapping (`acme-nde` endpoint) → `RecordNDEResult`; simulator NDE-contractor actor | H | A T04 |
| B | T09 | Piping grid/record screens (sketch 1 columns), NDE backlog tile | H | A T02 |
| A | T10 | Reports: weld log, progress by line/iso/area, welder performance, NDE status and reject rates, PWHT; demo; report | H | T09 |

## Increment 4 — Bolted joints, boltup, M7 pressure testing

**Demo:** torque a joint with a calibrated tool; build a test package over two lines; readiness shows welds accepted,
joints torqued, punch A closed, gauges calibrated; record the test; generate and sign the certificate; reinstatement.
**Fanout:** no. **Supervisor builds:** T02 (package readiness checks), T05 (certificate snapshot + signature).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML: `BoltedJoint`, `BoltupRecord`; `testing.yaml`: `TestPackage`, `PreTestChecklist`, `PressureTest`, `Reinstatement`; workflows | S | — |
| T02 | Test package readiness checks (welds + NDE, joints state, punch A, pinned docs current, gauges) via readiness engine | S | T01 |
| T03 | Boltup entry fast-entry screen with tool calibration check; break/remake cycles | H | T01 |
| T04 | Test commands: pre-test checklist, execute with instruments, result, witnesses, chart slot | H | T02 |
| T05 | Certificate generation from template + e-signature event with record hash and re-authentication stub | S | T04 |
| T06 | Reinstatement commands linking joints and boltup records | H | T04 |
| T07 | TUI: joint register, test package record with readiness, certificate view | H | T05 |
| T08 | Webhook `TestPackage.Ready`; reports: boltup log, joint status, test package status, certificates, reinstatement; demo; report | H | T07 |

## Increment 5 — Offline replicas: protocol, sync, merge, conflicts

**Demo:** two laptop replicas take the same IWP offline; both record welds, one edits the same visual result; sync →
weld records merge, the scalar edit becomes a conflict resolved in the conflict screen; a duplicate weld is merged with
a `same as` link; property tests prove convergence.
**Fanout (orchestrator):** WS-A protocol + merge engine; WS-B replica node packaging + UX. Contract: sync wire protocol (handshake, pull, push, ack) as LinkML.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `sync.yaml`: `Replica`, `PendingCommand`, `BaseContext`, `SyncConflict`, outcomes; protocol messages | S | — |
| A | T02 | Replica ledger: mirror and local segments, HLC timestamps, local hash chain, `Sync.Reconciled` | S | T01 |
| A | T03 | Sync client: handshake, pull (scope-filtered), rebase preview, push files (dedupe), push commands | H | T02 |
| A | T04 | Server merge: re-execute commands against canonical state → Accepted / Auto-merged / Conflict / Rejected | S | T02 |
| A | T05 | Merge policies from `tl:merge` annotations: append-only, deltas, add-wins sets, scalar rules, transitions, numbering provisional keys, natural-key duplicates | S | T04 |
| A | T06 | Property tests: convergence, idempotency, no-lost-writes, causal order; partition injection in simulator | H | T05 |
| B | T07 | Replica registration, scope subscription, `sync.max_offline_days`, revocation + quarantine (security gate) | H (S for revocation) | A T01 |
| B | T08 | Site node mode: embedded server on LAN serving TUIs; multi-level sync | H | A T03 |
| B | T09 | TUI: status bar, provisional ◌ rows, "take offline" picker, sync screen, conflict screen (base/mine/theirs, bulk) | H | A T04 |
| A | T10 | Demo; report | H | T06, T09 |

## Increment 6 — M12 models: ingest, objects, mapping, slices

**Demo:** upload an IFC; validation + property extraction; mapping rule `Pset_Tag.TagNumber → Tag` links 90% of
objects, ambiguous ones queued; slices generated per IWP and subsystem; one slice over 50 MB is split by storey.
**Fanout:** no. **Supervisor builds:** T04 (mapping engine), T06 (slice generator). See ADR-0002 for XKT fallback.

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML `models.yaml`: `ModelDocument` (is_a Document), `ModelRevision`, renditions, `ModelObject`, `ObjectMappingRule`, `FederatedView`, `Viewpoint`, `Overlay`, `ModelSlice`, `SliceRule` | S | — |
| T02 | IFC ingest job: schema check (IfcOpenShell), optional IDS validation (ifctester), property extraction → `props` rendition | H | T01 |
| T03 | `ModelObject` projector per revision with `ifc.*` psets and bounding boxes | H | T02 |
| T04 | Mapping engine: rules with class filters and regex transforms → links, proposals when ambiguous; review queue | S | T03 |
| T05 | Revision diff: added/removed/changed objects, tag coverage | H | T03 |
| T06 | Slice generator: by storey/area/system/IWP/test package/discipline/bbox/query; size gate; auto-split; floating regeneration | S | T03 |
| T07 | XKT conversion job (xeokit-convert via Node if available, else stub + `desktop_only`) and thumbnails | H | T02 |
| T08 | Publish model-derived data into Engineering Data via the import path with provenance | H | T04 |
| T09 | TUI: object tree, properties, mapping status, revision diff, slice list; reports; demo; report | H | T06 |

## Increment 7 — Model workspace, viewpoints, overlays, spatial context, TUI panel

**Demo:** web workspace search `weld nde:pending area:A12` highlights objects and lists records; select object → record;
raise an RFI from a viewpoint; an NCR with no explicit model ref shows context inherited via welds → spool → iso; the TUI
shows the text context and pairs with the open viewer.
**Fanout (orchestrator):** WS-A web workspace (TypeScript); WS-B spatial context resolver + TUI + snapshots. Contract: viewer component interface (load slice, highlight, fly-to, selection events, overlay colours).

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | Viewer component over xeokit SDK behind an interface (swap-able, Q9); page scaffold, build, Playwright test | S | — |
| A | T02 | Split workspace: search bar spanning both sides, result list, two-way selection sync, record panel from generated forms | H | T01 |
| A | T03 | Tools: section, X-ray, isolate, measure; viewpoints save/apply; BCF 3.0 import/export | H | T02 |
| A | T04 | Overlays from saved queries, live via change feed; federation of revisions | H | T02 |
| A | T05 | Bulk linking from object selection; raise RFI/punch/NCR from view with viewpoint attached | H | T03 |
| B | T06 | Spatial context resolver (§23.5 order) → `ctx_*` columns; recompute on revision publish | S | — |
| B | T07 | Envelope xref fields in forms; "Locate in model" command | H | T06 |
| B | T08 | TUI model context panel: text context everywhere; server-rendered snapshot (headless Chromium) in graphics terminals; `B` deep link/QR; `P` pairing channel | H | A T01, T06 |
| B | T09 | Guest-link page embedding the viewer (part of v1 web surface) | H | A T02 |
| — | T10 | Demo; report | H | all |

## Increment 8 — External parties, remaining domains, fast-entry hardening, Phase 3 exit

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | External-party accounts bound to `Party`, ABAC scoping (security gate) | S | — |
| T02 | Scoped guest links: expiring, OTP option, ledgered `guest:` actor; sign-off, RFI response, MTR upload, transmittal ack flows | H | T01 |
| T03 | Portal page: my items, uploads, sign-offs, correspondence addressed to me | H | T02 |
| T04 | HSE and Interface correspondence domains | H | — |
| T05 | Legal domain: restricted confidentiality, privilege markers, thin webhooks only, excluded from feeds/exports/AI (legal gate) | S | — |
| T06 | Fast-entry screens hardening on replicas (weld log, boltup, checklist, punch, toolcrib) | H | — |
| T07 | Simulator: QC inspector, welding crew, NDE contractor by inbound webhook, client rep via guest links; fault injections (calibration failed, design revision) | H | — |
| T08 | Phase-exit demo: weld → NDE → test package → certificate; overlay in model; inbound NDE | H | T07 |
| T09 | Phase report, risk register, ADRs (orchestrator) | O | T08 |
