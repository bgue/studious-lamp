# Build spec 09 — Phase 3 plan: Quality and piping

Brief: §16 Phase 3. M5 quality, M6 piping, M7 pressure testing, offline replicas (§22), M12 models (§23), external
parties (§18.11), fast-entry screens (§10.5), remaining correspondence domains. Eight increments. IDs `P3-I<n>-T<nn>`.

Status: v0.2, revised 2026-10-20 against Phase 1 as built (P1-I0 to P1-I5 on the trunk; P1-I6, P1-I7 and P1-I8 in
flight, taken as their plan sections in `07-phase1-plan.md`) and the Phase 2 sketch on `p2/prep`. Companions:
`phase3-implementation-sketch.md`, `phase3-contracts-draft.md`, `phase3-risks.md`, `phase3-owner-questions.md`.
Changes from v0.1 are marked **(changed: reason)** in the text and listed per increment.

**Phase exit (§16):** weld → NDE → test package → certificate end to end; progress colour-overlaid in the model; NDE
contractor results arrive by inbound webhook.
**Human gates:** every `schema/modules/**`, `schema/core/**` and `schema/fixtures/**` merge; the replica ledger ADR
(a 03 §7 interface change); replica revocation and encryption (security); external-party ABAC (security); the
xeokit licence (Q9) and the Node toolchain (ADR-0006, ADR-0002) before any viewer code is merged; the Quality, HSE,
Interface and Legal domain files (contractual clocks: commercial lead; Legal: legal lead); the Phase 3 settings keys in
`platform.yaml`. Delegation as P2-Q10 decides, extended by P3-Q11.

---

## 0. What Phase 3 builds on

| Seam (as built, names from the code and the Phase 2 sketch) | Phase 3 use |
|---|---|
| ADR-0010 module seam: `ModuleSpec`, `create_module_record`, generated `v_<module>_<class>` views, closed generic-command allow-list, entry point `throughline.modules` | New modules `quality` (M5), `piping` (M6), `testing` (M7), `models` (M12). **(changed: v0.1 named files `quality.yaml`, `piping.yaml`, `testing.yaml`, `models.yaml`; each is now a module directory `schema/modules/<m>/` with `module.yaml`, as every Phase 1 module)** |
| Commands and access words (`CommandSpec`, `Access`, ADR-0013); automation access (ADR-0017 §5, `AUTOMATION_COMMANDS`) | Every controlling act (NCR disposition, closure, calibration failure, NDE selection, certificate signature, replica revocation) is a module command with an access word; the inbound NDE endpoint runs `RecordNDEResult` as `svc:inbound-acme-nde` with `access: user` |
| Workflow engine: fixtures `schema/fixtures/workflows/<module>-<class>.yaml`; guards `required_psets`, `conformance`, `required_links`, `expected_links`; roles from the account (P1-SEC1) | NCR, CAR, QSR, Inspection, Deficiency, Weld, NDERequest, BoltedJoint, TestPackage, ModelSlice workflows are fixtures |
| Clocks: `tl_mod_correspondence.clocks` (pure replay over facts and a project calendar) and `DomainDefinition` clock templates | The Issue engine's due dates, response cycles and escalation reuse the clock arithmetic (P3-Q2 decides the import path); the Quality, HSE, Interface and Legal domains are domain files, not code |
| Readiness checks (`phase2-contracts-draft.md` §1, `tl_core/readiness/types.py`, frozen at Phase 2 wave 0) | Test package readiness (I4) and the Phase 2 `n_a` checks `inspections_planned`, `model_slice_available` become real; the contract needs a `SubjectFacts` generalisation (orchestrator decision, `phase3-contracts-draft.md` §5) |
| Derivation pipeline (ADR-0014): `DocumentSchema`, extractors in `tl_extract` found by entry point, `DerivedDocument`, `PublishMapping` with a `target_kind` and a create-only module command per kind, compensation | Weld map import from a derived iso (I3) and IFC ingest (I6) are extractors; publication into `piping.Weld` and `models.ModelObject` is a `PublishMapping` kind. **(changed: no second import path)** |
| Envelope for untrusted files (`run_in_envelope`, `tl_core/text.py` bounds) | IFC, IDS, weld map CSV, NDE report files, checklist imports, BCF |
| Job queue (`JobRunner`, kinds per worker CLI) | Kinds `piping.nde_select`, `testing.readiness`, `models.ingest`, `models.convert`, `models.slice`, `models.context`, `sync.merge`; one worker CLI per module until a shared worker exists (P2 T-10) |
| Integration layer (ADR-0017, P1-I7 WS-A): `InboundEndpoint` with JSONata mapping, rules, actions, reserved sources | `acme-nde` endpoint fixture; `TestPackage.Ready`, `ModelRevision.Published`, `NDE.Rejected` webhooks from `tl:event_type` classes; the calibration-failed rule |
| Threads and dispatch (ADR-0018): `TargetRegistry.register(..., module=True)` | `/raise ncr`, `/raise punch` targets registered by `quality`; threads on test packages |
| Confidentiality (ADR-0016): `Viewer`, `hidden_sql`, `filter_events`, `hidden_event_streams`; the five-reader walking test | Every new route, tool, feed, replica pull and guest link is filtered; the replica pull uses the owner's viewer; the external-party scope extends the `Viewer` (ADR at wave 0) |
| Lake (`tl_lake`, P1-I8 T08 marts framework or the `xer` second pass) | Marts: weld progress by line and iso, NDE reject rates, inspection log, calibration due |
| Cost and progress (ADR-0015; Phase 2 rules of credit `earned_fraction`, `IWP.ProgressRecorded`, job `awp.rollup`) | Weld and joint states feed the Phase 2 engine; `co.acme.awp-roc` gains weld and joint rows; `awp.ScopeItem` rows are superseded by weld records through a link (P2-Q7) |
| TUI: `ClientInterface`, embedded and remote clients, F1–F12 all taken; no logic in screens | Fast-entry screens open from the navigation panel and the palette; the embedded client over SQLite is the replica |
| Simulator: `ROLE_NAMES`, `INJECT_EVENTS`, operators (at most 8), `llm_share` 0 | Actors QC inspector, welding crew, NDE contractor (inbound), client rep (guest link); injections `calibration_failed`, `nde_reject`, `partition` |

### 0.1 Phase 1 and Phase 2 pieces Phase 3 consumes and must verify at phase start

| Consumed | Provider | If missing at phase start |
|---|---|---|
| RFI record and Technical domain | P1-I6 T01, T02 | Quality screens omit the RFI tab; nothing else waits |
| Inbound endpoints, JSONata mapping, `AUTOMATION_COMMANDS` | P1-I7 WS-A T04 (ADR-0017) | I3 T08 ships the command and a CSV path; the inbound clause of the exit demo says `deferred` |
| Rules engine | P1-I7 WS-A T03 | The calibration-failed rule becomes a command the impact screen calls |
| Thread dispatch targets | P1-I7 WS-B T10 (ADR-0018) | `/raise ncr` waits; the `d` key carries the demo |
| Lake marts framework | P1-I8 T08 | The `tl_lake.xer` second-pass pattern |
| Readiness contract, `awp.IWP`, `ScopeItem`, rules of credit, `cur_awp_readiness` | Phase 2 I2, I5 | Phase 3 does not start before Phase 2 I2 and I5 are on the trunk; I1, I3 and I5 of this plan can start after Phase 2 I2 alone |
| Movements as events on the lot stream, `StockLot` heat columns (P2-Q5) | Phase 2 I3 | Weld heat numbers are text until lots exist (`heat_number` slots, link to the lot when it exists) |
| `api.public_base_url` (P2 T-11) | Phase 2 I5 T07 | Guest links and QR deep links are refused until set |

### 0.2 Parallelism plan **(changed: eight sequential increments become five waves; the cap of about three active agents holds)**

| Wave | Runs in parallel | Why it is safe | Registry owner | Needs before start |
|---|---|---|---|---|
| 0 | Orchestrator alone: freeze `phase3-contracts-draft.md`; ADRs for the replica ledger (03 §7), the external-party viewer scope, models as documents; `platform.yaml` keys; owner answers recorded as an ADR | — | — | P3-Q1 to P3-Q14 answered |
| 1 | **I1** (quality part 1) ∥ **I3** (piping, fanout) | Different modules and fixture files; I1 raises NCRs against generic records until I3 lands | I3 | Wave 0 |
| 2 | **I2** (quality part 2, fanout) ∥ **I6** (models ingest) | `quality` against `models`; I6 touches only `documents` extractors and its own module | I2 | I1 on trunk; I6 needs nothing from wave 1 |
| 3 | **I4** (boltup, testing) ∥ **I5** (replicas, fanout) | `piping` and `testing` against `tl_core/sync` and `tl_adapters`; I5 merges a 03 §7 change, so it merges last | I5 | I2, I3 on trunk |
| 4 | **I7** (workspace, context, fanout) ∥ **I8 T01–T05** (external parties, domains) | `models` and `web/` against `tl_core/auth`, `confidentiality.py` and domain fixtures | I8 | I4, I6 on trunk; I7 WS-B needs I3 for spatial paths |
| 5 | **I8 T06–T09** (hardening, simulator, exit) | Integrates everything | — | I5, I7 on trunk |

Critical path: I3 → I4 → I7 → I8 (waves 1, 3, 4, 5). I5 is the riskiest increment and starts in wave 3 so that its
property tests run over real module commands with `tl:merge` annotations.

### 0.3 Shared registries (one owner per wave; the later side regenerates, never hand-merges)

As `08-phase2-plan.md` §0.3, plus: `schema/core/annotations.yaml` (`tl:merge`, `tl:spatial_context_via`) is a
wave 0 change; `web/` (new workspace, I7) has one owner; `tl_core/readiness/types.py` changes only in wave 0;
`AUTOMATION_COMMANDS` and the dispatch `TargetRegistry` are appended by the module that ships the command.

### 0.4 Tier rule applied to every increment **(changed: the Phase 2 tier rule and the AGENTS.md "never" list)**

Supervisor-built: every LinkML schema and fixture; every `ModuleSpec`, projector, allow-list and guard; every
command with an access word other than `user` and every command that writes a quantity, a result, a signature or a
selection; every job kind; every parser of an uploaded file; every API table entry, route, client method and MCP tool
registration; **all sync, merge, numbering, auth, permission and replica code** (AGENTS.md: never from an implementer ticket);
the TypeScript viewer interface. Implementer tickets: read views and reports with a provided test, CLI read groups,
one TUI screen from a sketch, MCP read tools, simulator actors over an existing desk, fixture files from a table,
property tests over a provided harness. Rows below marked `H (reads), S (writes)` are split at dispatch time.
Security review in a fresh context before DONE, per increment, as Phase 2.

---

## Increment 1 — M5 Issue engine, NCR/CAR/QSR, Quality correspondence domain

**Demo:** raise an NCR against three generic records (welds from I3 when on the trunk) with disposition `repair`; a
CAR addresses it; a Quality-domain NCR notification to the client is issued and linked; closure requires the CAR
effectiveness check; the due-date clock pauses while the NCR waits on the client; `/raise ncr` from a thread.
**Fanout:** no. Runs in parallel with I3 (wave 1). **Supervisor builds:** T02, T03, the write side of T04 and T05,
API, client and MCP registration, the demo.
**Changes from v0.1:** T04 split into write (S) and read (H) **(tier rule)**; T05 is a domain file plus letter
templates, H **(domains are data, ADR-0016 and `DomainDefinition`)**; T03 reuses the correspondence clocks
**(no second clock engine; P3-Q2)**; a thread target row added **(ADR-0018)**.

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Fixtures: `co.acme.quality@1.0.0.yaml` (patterns `NCR`, `CAR`, `QSR`, `AUD`, `INS`, `DEF`, `INST`; code lists: dispositions, root-cause methods, punch categories, priorities, inspection point types) | H (data), S (patterns) | — |
| T02 | LinkML `schema/modules/quality/` part 1: `Issue` (abstract), `NCR`, `CAR`, `QSR`, `Audit`; workflows; `tl:expects_link` (NCR → affected records, CAR → the issue it addresses) | S | T01 |
| T03 | Issue engine: `allocate_key` per kind, assignment, due dates and response cycles over the clock arithmetic, escalation (`Issue.Escalated`), closure guards (CAR effectiveness check, open deficiencies) | S | T02 |
| T04a | Commands `RaiseIssue` (kind), `Disposition` (`controller`), `AssignIssue`, `RespondToIssue`, `CloseIssue` (guarded), `BulkLinkAffected`; projectors `cur_quality_ncr` etc. | S | T03 |
| T04b | Registers and read views (`tl quality ncr|car|qsr ls|show`); API read tests | H | T04a |
| T05 | Quality correspondence domain file (NCR notification, CAR request, quality notice, audit letter; clocks; letter templates) and the `related_issue` link to the internal record | H (domain file, commercial gate), S (link rule) | T03 |
| T06 | TUI: issue registers and record view; `d`-style raise-from-anywhere for NCR; thread target `/raise ncr` (ADR-0018, `module=True`) | H (screens), S (target) | T04b |
| T07 | Reports: NCR/CAR/QSR registers and trends; MCP read tools and proposable `propose_ncr`; simulator QC-inspector desk and actor v1; `dev/demos/P3-I1.sh`; report | H (reads, actor), S (demo) | T06 |

## Increment 2 — ITPs, checklists, inspections, deficiencies, calibration

**Demo:** an ITP with H/W/R/S points; run a checklist inspection with a calibrated instrument; raise a deficiency in two
keystrokes; fail the instrument's calibration → impact analysis lists the inspection → one-click NCR; a past-due
instrument is refused (hard) or warned (soft) by the setting.
**Fanout (orchestrator):** WS-A records and engine; WS-B checklist runner and punch walkdown screens. Contract:
`phase3-contracts-draft.md` §1 (checklist form metadata and the response shape), frozen before the fanout.
**Supervisor builds:** WS-A: T01, the write side of T02, T03, T04, T05's projection, API, client and MCP
registration; WS-B: the client methods for the two screens (the P1-I4 S9 pattern).
**Changes from v0.1:** T02 and T03 split into S writes and H reads **(tier rule)**; T04 impact analysis is a read plus
a bulk command, not a rules-engine dependency **(P1-I7 rules may be propose-only)**; the Phase 2 readiness check
`inspections_planned` becomes real here **(P2 contract table says "Phase 3")**; `Punch` is the same class as
`Deficiency` with a `category` so Phase 4 reuses it **(brief M8)**.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `quality` part 2: `ITP`, `ITPLine`, `ChecklistTemplate` (questions as a versioned pset definition), `Inspection`, `Deficiency` (`category` A/B/C, `kind` deficiency or punch), `Instrument`, `CalibrationRecord`; workflows; `tl:expects_link` (Inspection → ITP line, instruments) | S | — |
| A | T02a | Inspection commands: `ScheduleInspection`, `RecordInspectionResult` (checklist responses as pset values, witness parties, instruments used; past-due instrument guard by `quality.calibration.block_mode`) | S | T01 |
| A | T02b | Inspection read views, `tl quality insp ls|show`, API read tests | H | T02a |
| A | T03 | `RaiseDeficiency` from any record (origin link `raised_against`), `AssignDeficiency`, `ClearDeficiency` (clearing inspection link); the `d` key target and thread target `/raise punch` | S (commands), H (key wiring) | T01 |
| A | T04 | Calibration: `RecordCalibration`, `FailCalibration` (`controller`), due list view, impact analysis query (inspections and tests since the last good calibration) → `BulkLinkAffected` of an NCR (I1) | S | T02a |
| A | T05 | ITP compliance projection `cur_quality_itp_compliance` (planned vs done per line) and the readiness check `inspections_planned` (real) | S (projection, check), H (report) | T02a |
| B | T06 | Checklist runner screen (question by question, keyboard answers) over the contract form | H | contract |
| B | T07 | Punch walkdown fast-entry screen with location and system prefill | H | contract |
| B | T08 | Inspection log and deficiency aging screens | H | A T03 |
| A | T09 | Reports: inspection log, ITP compliance, deficiency aging, calibration due, calibration impact; MCP read tools; simulator QC-inspector actor v2 (checklists); `dev/demos/P3-I2.sh`; report | H (reads, actor), S (demo) | T08 |

Merge order: A T01–T05 → B → A T09. A owns conflicts.

## Increment 3 — M6 lines, isos, spools, welds, NDE, welder qualifications

**Demo:** import a weld map from a derived iso; a weld daily log entry checks welder continuity and WPS; NDE selection by
piping class %; RT rejects via inbound webhook create repair welds and penalty selection; weld counts and inch-dia
earn progress on the IWP through the Phase 2 rules of credit.
**Fanout (orchestrator):** WS-A records, commands and NDE rules; WS-B weld daily log and inbound NDE mapping.
Contract: `phase3-contracts-draft.md` §2 (`NDESelectionRule`, `RecordNDEResult`, the inbound payload).
**Supervisor builds:** WS-A: T01, T02, T03, T04, T05's reader and publication command, T06; WS-B: the client
methods for T07 and T09, the endpoint fixture and mapping of T08.
**Changes from v0.1:** T02 projectors are S **(tier rule)**; T03 and T06 are S **(qualification guards; quantities)**;
T05 is an extractor plus a `PublishMapping` kind `weld_map` **(ADR-0014: one import path)**; T08 is an
`InboundEndpoint` fixture with a JSONata mapping, not a bespoke endpoint **(ADR-0017)**; T06 feeds the Phase 2
`earned_fraction` instead of a new rollup **(Phase 2 I5)**.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `schema/modules/piping/`: `Line`, `Isometric`, `Spool`, `Weld`, `WelderQualification`, `NDESelectionRule`, `NDERequest`, `NDEResult`; `tl:spatial_context_via` (weld → spool, iso, line); `tl:expects_link` WPS document at Welded; `tl:merge` on weld slots; workflows; `co.acme.piping@1.0.0.yaml` (patterns, piping classes, weld types, NDE methods) | S | — |
| A | T02 | Projectors with denormalised columns (`spool_key`, `iso_key`, `iso_rev`, `line_key`, `iwp_key`, `test_package_key`, `heat_numbers`) | S | T01 |
| A | T03 | Weld commands: `RecordFitUp`, `RecordWeld` (welder qualification and continuity guards, WPS pin), `RecordVisual`, `RecordPwht`, `RepairWeld` (links the original, increments the repair index) | S | T02 |
| A | T04 | NDE selection engine: job `piping.nde_select` (% per class, lots), `NDE.Selected`, `NDERequest` creation, penalty selection on `NDE.Rejected`; `RecordNDEResult` (user; in `AUTOMATION_COMMANDS`) | S | T03 |
| A | T05 | Weld map import: `weld_map` extractor (derived iso data, CSV in the envelope), `PublishMapping` kind `weld_map`, `PublishWeldMap` (`controller`, create-only, compensable), numbering validation | S (reader, command), H (CLI and preview view) | T02 |
| A | T06 | Progress quantities (count, inch-dia) per weld state → the Phase 2 rules-of-credit rows for welds; `awp.ScopeItem` superseded-by-weld link; IWP and cost-code figures through `awp.rollup` | S | T03 |
| B | T07 | Weld daily log fast-entry grid by iso (keyboard only) | H | A T03 |
| B | T08 | Inbound NDE results: `acme-nde` `InboundEndpoint` fixture, HMAC, JSONata mapping → `RecordNDEResult`; simulator NDE-contractor actor posting to the endpoint | H (mapping, actor), S (fixture and secret handling) | A T04 |
| B | T09 | Piping grid and record screens (sketch 1 columns), NDE backlog tile | H | A T02 |
| A | T10 | Reports: weld log, progress by line, iso and area, welder performance, NDE status and reject rates, PWHT; MCP read tools; lake marts `mart_weld_progress`, `mart_nde_rejects`; `dev/demos/P3-I3.sh`; report | H (reads, marts), S (demo) | T09 |

Merge order: A T01–T04 → B T07–T09 → A T05, T06, T10. A owns conflicts.

## Increment 4 — Bolted joints, boltup, M7 pressure testing

**Demo:** torque a joint with a calibrated tool; build a test package over two lines; readiness shows welds accepted,
joints torqued, punch A closed, pinned documents current, gauges calibrated; record the test; generate and sign the
certificate; reinstatement; `TestPackage.Ready` reaches a loopback receiver.
**Fanout:** no. Runs in parallel with I5 (wave 3). **Supervisor builds:** T01, T02, the write side of T03, T04, T05,
T06, API, client and MCP registration, the demo.
**Changes from v0.1:** `BoltedJoint` and `BoltupRecord` stay in `piping` **(brief M6)**; `testing` is its own module;
T02 is a readiness subject over the Phase 2 contract, generalised at wave 0 **(no second readiness engine)**; T04 and
T06 are S **(results and instruments are guarded writes)**; T05 reuses the Phase 2 pack renderer and P2-Q11's PDF
decision **(one template engine)**.

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML `piping` part 2: `BoltedJoint`, `BoltupRecord`; `schema/modules/testing/`: `TestPackage`, `PreTestChecklist`, `PressureTest`, `Reinstatement`; workflows; `tl:spatial_context_via` (test package → slice, lines); `co.acme.testing@1.0.0.yaml` | S | — |
| T02 | Test package readiness: checks `welds_accepted`, `nde_complete`, `joints_in_state`, `punch_a_closed`, `documents_current` (reused), `gauges_calibrated` as `throughline.readiness_checks` plugins for subject `testing.TestPackage`; job `testing.readiness`; `TestPackage.ReadinessEvaluated`; `TestPackage.Ready` | S | T01, contract §5 |
| T03 | Boltup: `RecordBoltup` (tool calibration guard, measured values), `BreakJoint`, `RemakeJoint`; boltup fast-entry screen | S (commands), H (screen) | T01 |
| T04 | Test commands: `CompletePreTestChecklist`, `ExecuteTest` (instruments calibrated, witnesses), `RecordTestResult`, chart in file slot `chart` | S | T02 |
| T05 | Certificate: rendered from a repository template (Phase 2 renderer; HTML, PDF per P2-Q11) into slot `certificate`; `SignCertificate` (`controller` or the P3-Q5 role) with the record-set hash and a re-authentication check | S | T04 |
| T06 | Reinstatement commands linking joints, boltup records and blinds | S (write), H (view) | T04 |
| T07 | TUI: joint register, test package record with readiness tab, certificate view | H | T05 |
| T08 | Reports: boltup log, joint status, test package status, certificates, reinstatement; MCP read tools; `dev/demos/P3-I4.sh`; report | H (reads), S (demo) | T07 |

## Increment 5 — Offline replicas: protocol, sync, merge, conflicts

**Demo:** two laptop replicas take the same IWP offline; both record welds, one edits the same visual result; sync →
weld records merge, the scalar edit becomes a conflict resolved in the conflict screen; a duplicate weld is merged with
a `same as` link; a revoked replica's commands are quarantined; property tests prove convergence.
**Fanout (orchestrator):** WS-A protocol, replica ledger and merge engine; WS-B replica node, scope, revocation and
UX. Contract: `phase3-contracts-draft.md` §3 (wire protocol as LinkML, `PendingCommand`, outcomes, `tl:merge`).
**Supervisor builds:** everything except T06 (property tests over a provided harness), the two read screens of
T09 and the status bar **(AGENTS.md: sync, merge, numbering and auth code are never implementer tickets)**.
**Changes from v0.1:** the replica ledger is an ADR at wave 0 because it touches `Ledger`, `Event` and
`UnitOfWork` in 03 §7 **(core interface)**; T03 and T08 become S **(never list)**; T07 is S throughout **(auth)**;
T05 adds `reserve_range` or provisional keys per P3-Q8 **(`reserve_range` was never built)**; site node mode is the
existing embedded server plus multi-level sync, scheduled last and droppable **(P3-Q1)**.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | LinkML `schema/core/sync.yaml`: `Replica`, `PendingCommand`, `BaseContext`, `SyncConflict`, outcomes; protocol messages; `tl:merge` annotation in `annotations.yaml` | S | — |
| A | T02 | Replica ledger: mirror segment (canonical events imported with their `seq` and hash) and local segment (`PendingCommand` rows, HLC, `captured_at`, local hash chain); `Sync.Reconciled`; the ADR's `Ledger` addition | S | T01, ADR |
| A | T03 | Sync client: handshake (schema hash, skew), pull (scope- and viewer-filtered), rebase preview, push files (dedupe by hash, resumable), push commands | S | T02 |
| A | T04 | Server merge: job `sync.merge` re-executes commands through the command runner (ADR-0017 §7) against canonical state → Accepted / Auto-merged / Conflict / Rejected; `Command.Rejected` | S | T02 |
| A | T05 | Merge policies from `tl:merge`: append-only, deltas, add-wins sets, scalar rules, transitions, numbering (provisional keys with alias, P3-Q8), natural-key duplicates → `Record.Merged` + `same as` | S | T04 |
| A | T06 | Property tests over the harness: convergence, idempotency, no lost writes, causal order; simulator `partition` injection | H | T05 |
| B | T07 | Replica registration (certificate, owner, scope subscription), `sync.max_offline_days`, revocation and quarantine, encryption posture (P3-Q14) — security gate | S | A T01 |
| B | T08 | Site node mode: embedded server on the LAN serving remote TUIs; multi-level sync | S | A T03 |
| B | T09 | TUI: status bar (`● online` / `◌ offline · n pending`), provisional ◌ rows, "take offline" picker, sync screen, conflict screen (base, mine, theirs; bulk) | H (status, sync screen), S (conflict resolution commands) | A T04 |
| A | T10 | `dev/demos/P3-I5.sh`; report | S | T06, T09 |

Merge order: A T01–T02 (with the ADR) → B T07 → A T03–T05 → B T08–T09 → A T06, T10. A owns conflicts.

## Increment 6 — M12 models: ingest, objects, mapping, slices

**Demo:** upload an IFC as a revision of a model document; validation and property extraction; mapping rule
`Pset_Tag.TagNumber → Tag` links 90% of objects, ambiguous ones queued; slices generated per IWP and subsystem; one
slice over 50 MB is split by storey; `ModelRevision.Published` reaches a loopback receiver.
**Fanout:** no. Runs in parallel with I2 (wave 2). **Supervisor builds:** T01, T02, T03, T04, T06, T08, the
conversion job of T07, API, client and MCP registration, the demo. See ADR-0002 for the XKT fallback.
**Changes from v0.1:** `ModelDocument` is a `documents.Document` of document type `model` and the IFC is its
revision file; `models.ModelRevision` is a module record `derived from` that revision, created by the ingest job
**(no cross-module `is_a` on the ADR-0010 seam; P3-Q3)**; `ModelObject` is a typed operational table per revision,
not a `cur_core_record` row **(tens of thousands of rows per revision; L-P0-I8D-1)**; T02 is an extractor in the
envelope **(ADR-0014)**; T08 is a `PublishMapping` kind **(one import path)**.

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML `schema/modules/models/`: `ModelRevision` (record, `derived from` a `documents.Revision`), `ObjectMappingRule`, `FederatedView`, `Viewpoint`, `Overlay`, `ModelSlice`, `SliceRule`; operational `model_object` (per revision, `ifc.*` psets, bounding box); renditions as file slots `ifc`, `xkt`, `props`, `thumb`; `ModelSlice` workflow; document type `model` in the documents fixtures | S | — |
| T02 | IFC ingest: extractor `ifc` (IfcOpenShell in the envelope; schema check; optional IDS with ifctester) → `props` derived document; job `models.ingest` registers the `ModelRevision` | S | T01 |
| T03 | `model_object` loader from the `props` rendition (bounded rows per revision) and read views | S (loader), H (views, `tl models obj ls`) | T02 |
| T04 | Mapping engine: rules with class filters and regex transforms → `references` links `ModelObject` ⇄ Tag, Line, Spool, Equipment; proposals when ambiguous; review queue | S | T03 |
| T05 | Revision diff: added, removed, changed objects; tag coverage | H | T03 |
| T06 | Slice generator: job `models.slice` by storey, area, system, IWP, test package, discipline, bbox or query; size gate `models.slice.max_ifc_mb`; auto-split; floating regeneration on publish | S | T03 |
| T07 | XKT conversion job `models.convert` (xeokit-convert via Node when present, else stub and `desktop_only`) and thumbnails | S (job), H (stub detection test) | T02 |
| T08 | Publish model-derived data into Engineering Data: `PublishMapping` kind `model_props` with provenance to the revision | S | T04 |
| T09 | TUI: object tree, properties, mapping status, revision diff, slice list; reports; MCP read tools; `dev/demos/P3-I6.sh`; report | H (screens, reads), S (demo) | T06 |

## Increment 7 — Model workspace, viewpoints, overlays, spatial context, TUI panel

**Demo:** web workspace search `weld nde:pending area:A12` highlights objects and lists records; select object → record;
raise an RFI from a viewpoint; an NCR with no explicit model ref shows context inherited via welds → spool → iso; the TUI
shows the text context and pairs with the open viewer; weld progress is colour-overlaid (the §16 exit clause).
**Fanout (orchestrator):** WS-A web workspace (TypeScript, `web/`); WS-B spatial context resolver, TUI panel,
pairing. Contract: `phase3-contracts-draft.md` §4 (viewer component interface, the context view, the pairing channel).
**Supervisor builds:** WS-A: T01 (the interface and the first implementation), the API routes the page calls;
WS-B: T06, the pairing channel of T08, client methods.
**Changes from v0.1:** `ctx_*` lives in a side table `cur_models_context` joined by the query language, not in every
`cur_*` envelope **(generated DDL; no envelope change)**; T08's headless-Chromium snapshot is deferred per
P3-Q13 **(ADR-0002 environment; browser download)**; T09 waits for I8 T02 guest links **(dependency)**; the
`web/` toolchain and the xeokit licence are wave 0 gates **(ADR-0006, Q9)**.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | Viewer component behind `ModelViewer` (contract §4) over the xeokit SDK; `web/` workspace scaffold, build, one Playwright test; licence posture per P3-Q9 | S | wave 0 gates |
| A | T02 | Split workspace: search bar over the query language API, result list, two-way selection sync, record panel from generated forms | H | T01 |
| A | T03 | Tools: section, X-ray, isolate, measure; viewpoints save and apply; BCF 3.0 import (envelope) and export | H (tools), S (BCF reader) | T02 |
| A | T04 | Overlays from saved queries, live via the change feed; federation of revisions | H | T02 |
| A | T05 | Bulk linking from object selection; raise RFI, punch, NCR from the view with the viewpoint attached | H | T03 |
| B | T06 | Spatial context resolver (§23.5 order) → `cur_models_context`; job `models.context` recompute on revision and slice publish; query filter `has:model_context` | S | — |
| B | T07 | Envelope xref fields in forms; `LocateInModel` command | H (forms), S (command) | T06 |
| B | T08 | TUI model context panel: text context everywhere; `B` deep link and QR; `P` pairing channel (same user, code) | H (panel), S (pairing) | A T01, T06 |
| B | T09 | Guest-link page embedding the viewer (part of the v1 web surface) | H | A T02, I8 T02 |
| — | T10 | `dev/demos/P3-I7.sh`; report | S | all |

Merge order: B T06–T07 → A T01–T05 → B T08–T09 → T10. B owns conflicts (it touches `tl_core/query`).

## Increment 8 — External parties, remaining domains, fast-entry hardening, Phase 3 exit

**Fanout:** no. T01–T05 run in wave 4 in parallel with I7; T06–T09 in wave 5. **Supervisor builds:** T01, T02, T05,
T07's injection semantics, T08.
**Changes from v0.1:** T01 extends the ADR-0016 `Viewer` with a party scope (ADR at wave 0) rather than a new ABAC
engine **(one seam for every read path)**; T03 is a web page in `web/` **(the v1 web surface; depends on I7 T01's
toolchain)**; T04 and T05 are domain files **(data, not code; the Legal tests stay S)**.

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | External-party accounts: role `external` bound to a `Party`; `Viewer.party` and the party scope in `hidden_sql` (records assigned to or shared with the party, and their threads); the five-reader walking tests gain a sixth reader — security gate | S | ADR |
| T02 | Scoped guest links: expiring, OTP option, ledgered `guest:<party>/<link>` actor (reserved source); flows: inspection sign-off, RFI response, MTR upload to a receipt slot, transmittal acknowledgement; needs `api.public_base_url` | S | T01 |
| T03 | Portal page (`web/portal`): my items, uploads, sign-offs, correspondence addressed to my party | H | T02, I7 T01 |
| T04 | HSE and Interface correspondence domain files (commercial gate) | H | — |
| T05 | Legal domain file: `privileged` default, privilege markers, feed policy `none`, thin webhooks, excluded from replica pull, feeds, exports, lake and AI — tests prove each exclusion (legal gate) | S | — |
| T06 | Fast-entry screens hardening on replicas (weld log, boltup, checklist, punch, toolcrib): provisional rows, conflict hints | H | I5 |
| T07 | Simulator: QC inspector, welding crew, NDE contractor by inbound webhook, client rep by guest link; injections `calibration_failed`, `nde_reject`, `design_revision`, `partition`; `ROLE_NAMES` and operators | H (actors), S (injection semantics) | T02, I5 |
| T08 | Phase-exit demo `dev/demos/P3-I8.sh`: weld → NDE (inbound) → test package → certificate; weld progress overlay in the model; on SQLite and Postgres | S | T07 |
| T09 | Phase report, risk register, `LEARNINGS.md` curation, ADRs (orchestrator) | O | T08 |
