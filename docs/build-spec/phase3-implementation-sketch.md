# Phase 3 — implementation sketch

Status: 2026-10-20, written with `09-phase3-plan.md` v0.2. Per increment: what it touches, what it adds (records,
events, current-state tables), the surfaces, what it reuses, the fanout recommendation and the demo outline. Names
follow the code on the trunk and the Phase 2 sketch (`p2/prep`). "Core interface" marks anything that would change a
`03-repo-and-toolchain.md` §7 contract: that needs an orchestrator ADR before the increment starts.

Conventions used throughout, not repeated per increment:

- A module is `packages/tl-modules/<m>/src/tl_mod_<m>/` with `module.py` (`spec()`), `commands.py`, `guards.py`,
  `handlers/`, `projectors/`, `views.py`, `reports.py`, `names.py`, `limits.py`, `testing.py`, plus
  `schema/modules/<m>/` (`module.yaml`, one YAML per class, `events.yaml`), `schema/fixtures/workflows/<m>-<class>.yaml`,
  `schema/fixtures/standards/co.acme.<m>@1.0.0.yaml`, an entry point under `throughline.modules`, a `<MODULE>_COMMANDS`
  tuple splatted into `tl_api.commands.COMMANDS`, a CLI group `tl <m>` in `tl_cli/main.py`, `<m>_tools.py` in
  `tl_mcp`, client methods in `tl_tui/client.py` plus `embedded.py`, `remote.py` and the fake, and a screen under
  `tl_tui/widgets/`. `docs/modules/<m>/` holds the README and the legacy mapping template (06 cross-phase rule 2).
- Every record is on the ADR-0010 seam: one `cur_core_record` row, one typed row, a generated `v_<m>_<class>` view,
  closed generic commands, guards per state. Every read goes through the ADR-0016 viewer; every new route, tool,
  feed, export or replica pull gets the five-reader walking test.
- Reserved identifiers added by the phase go in `tl_core/services/reserved.py` at wave 0 (`phase3-contracts-draft.md` §7).

---

## I1 — Issue engine, NCR/CAR/QSR, Quality domain

**Touches:** new `quality` module and schema directory; `schema/fixtures/standards/co.acme.quality@1.0.0.yaml`;
`schema/fixtures/correspondence/domains/quality.yaml` (the domain file; the correspondence module loads it);
`tl_mod_correspondence/clocks.py` (import only, P3-Q2); `tl_core/threads` target registry (one `register(...,
module=True)` call from `quality`); registries of §0.3.

**Records:** `Issue` (abstract: `kind`, `raised_against` links, `owner`, `due_on`, `response_cycle`, `escalation_level`,
`closed_on`), `NCR` (`disposition`, `root_cause`, `approvals`), `CAR` (`root_cause_method`, `actions`,
`effectiveness_check`), `QSR` (`observations`, `rating`, `area`), `Audit` (optional, `scope`, `findings`).
**Events:** `Issue.Raised`, `Issue.Assigned`, `Issue.Responded`, `Issue.Escalated`, `Issue.Dispositioned`,
`Issue.Closed`, `Issue.Reopened`; a workflow transition per state. **Current state:** `cur_quality_ncr`,
`cur_quality_car`, `cur_quality_qsr`, `cur_quality_audit`, plus `cur_quality_issue_clock` (the due-date figures
replayed from the clock facts, as `cur_corr_clock` is).

**Commands:** `RaiseIssue(kind, title, against: list[record_id], ...)` (`user`; proposable as `propose_ncr`),
`AssignIssue`, `RespondToIssue`, `Disposition(ncr_id, disposition, reason)` (`controller`), `CloseIssue`
(guard: a CAR's effectiveness check recorded; no open deficiency `raised_against` the NCR), `BulkLinkAffected(issue_id,
record_ids)` (bounded, `MAX_AFFECTED = 200`). **API:** the command table rows, `GET /quality/ncr|car|qsr`, `/quality/issue/{id}`.
**MCP:** `list_issues`, `get_issue`, `propose_ncr`. **TUI:** issue registers, record view with tabs (affected, correspondence,
clock, history), `d`-style raise (the Phase 2 constraint key pattern) from any record.

**Reuse:** `allocate_key` with the `NCR`, `CAR`, `QSR` patterns; the workflow engine with `required_psets`
(disposition before Dispositioned) and `expected_links`; the correspondence clocks for due dates (a `Fact` sequence
replayed with the project calendar, `pause` while the Quality-domain item is with the client, `resume` on receipt);
threads (`/raise ncr`); the feed (one card per raise and close, `importance: low` for assignment).

**Fanout:** one supervisor. The domain file and the clock reuse are the only cross-module pieces and both are
data or pure functions.

**Demo (`just demo P3-I1`):** (1) load `co.acme.quality@1.0.0`, twice; (2) raise an NCR against three records,
numbered `P123-NCR-0001`; (3) disposition `repair` by a controller; a user's disposition is refused; (4) a CAR
`addresses` the NCR; (5) a Quality-domain NCR notification issued to the client, linked, the NCR clock paused; the
client's reply resumes it; (6) closure refused until the CAR effectiveness check exists; then closed; (7) `/raise ncr`
from a thread (or `deferred`); (8) the same over API, TUI and MCP, as five kinds of reader.

## I2 — ITPs, checklists, inspections, deficiencies, calibration

**Touches:** `quality` module part 2; `tl_core/readiness` (one check registered by `quality`); `tl_tui/widgets/`
two fast-entry screens; the `d` key binding in the record screen (shared with I1: `d` opens a chooser NCR /
deficiency / constraint).

**Records:** `ITP` (`activity`, `reference_spec`), `ITPLine` (`characteristic`, `acceptance`, `points` as a list of
`{party, kind: H|W|R|S}`), `ChecklistTemplate` (`questions` as a versioned pset definition, contract §1),
`Inspection` (`type`, `scheduled_on`, `actual_on`, `inspectors`, `result`, `responses` pset values, `witnesses`,
`instruments` links), `Deficiency` (`kind` deficiency or punch, `category` A/B/C, `priority`, `responsible_party`,
`due_on`, `photos` slot), `Instrument` (`instrument_id`, `type`, `range`, `accuracy`, `calibration_interval_days`),
`CalibrationRecord` (`calibrated_on`, `due_on`, `result`, `lab`, slot `certificate`).
**Events:** `Inspection.Scheduled`, `Inspection.Recorded`, `Deficiency.Raised`, `Deficiency.Assigned`,
`Deficiency.Cleared`, `Calibration.Recorded`, `Calibration.Failed`, `ITP.ComplianceUpdated`. **Current state:**
`cur_quality_itp`, `cur_quality_itp_line`, `cur_quality_checklist_template`, `cur_quality_inspection`,
`cur_quality_deficiency`, `cur_quality_instrument`, `cur_quality_calibration`, `cur_quality_itp_compliance`
(planned vs done per line; projected from `Inspection.Recorded`), `cur_quality_instrument_status` (due, past due).

**Commands:** `ScheduleInspection`, `RecordInspectionResult(inspection_id, result, responses, witnesses, instruments)`
(guard: every instrument has a current calibration unless `quality.calibration.block_mode = soft`, then a warning and a
constraint source `check`), `RaiseDeficiency(against, category, ...)` (`user`; the `d` key; proposable),
`AssignDeficiency`, `ClearDeficiency(clearing_inspection_id)`, `RecordCalibration`, `FailCalibration` (`controller`),
`ImpactOfCalibrationFailure(instrument_id) -> list[RecordRef]` (a read), then `BulkLinkAffected` (I1). **MCP:**
`inspection_log`, `deficiency_aging`, `calibration_due`, `propose_deficiency`. **TUI:** checklist runner (contract §1
form; one question per screen; keys `y n a` and digits), punch walkdown (location and system prefill from the last
entry; one row per `Enter`), inspection log, deficiency aging.

**Reuse:** psets for checklist responses (the effective-schema conformance guard validates them); the readiness
contract (`inspections_planned` becomes a real check reading `cur_quality_itp_compliance` for the IWP's scope);
Phase 2 constraints (`raise_from_check`) for soft calibration blocks; the file slots for photos and certificates.

**Fanout:** WS-A (records, engine) ∥ WS-B (two fast-entry screens, two log screens). Contract §1 lets WS-B build
the runner against a fixture form before `RecordInspectionResult` exists. The fanout is worth it: the screens are
four tickets with no schema dependency beyond the contract.

**Demo (`just demo P3-I2`):** (1) an ITP with four lines and H/W/R/S points; (2) a checklist template of 8 questions;
(3) an inspection recorded with instrument `INST-0007`, responses validated; (4) `d` on a weld (or generic record) raises
a deficiency with two keystrokes; (5) `FailCalibration` on `INST-0007`: the impact list names the inspection; one key
raises an NCR with the inspection `BulkLinkAffected`; (6) a past-due instrument refused (hard) then warned (soft) after
the setting changes; (7) ITP compliance 3/4; the IWP readiness check `inspections_planned` reads it; (8) surfaces and
readers.

## I3 — Lines, isos, spools, welds, NDE, welder qualifications

**Touches:** new `piping` module; `tl_extract` (`weld_map` extractor); `tl_mod_documents` `PublishMapping` kinds
(`weld_map`); `schema/core/annotations.yaml` (`tl:spatial_context_via` declared at wave 0, used here);
`schema/fixtures/integration/acme-nde.yaml` (`InboundEndpoint` and mapping); `AUTOMATION_COMMANDS`; the Phase 2
rules-of-credit package (`co.acme.awp-roc@1.1.0`, weld rows); `tl_lake` marts.

**Records:** `Line`, `Isometric` (pinned `documents.Revision` by `references`), `Spool`, `Weld` (`weld_no`, `type`,
`size`, `schedule`, `material_group`, `shop_field`, `wps` link, `welders`, `fit_up_on`, `welded_on`, `visual_result`,
`pwht_required`, `pwht_done`, `repair_of`, `repair_index`, `heat_numbers`, `inch_dia`), `WelderQualification`
(`welder`, `process`, `positions`, `range`, `expires_on`, `continuity` as dated facts), `NDESelectionRule`,
`NDERequest` (`method`, `lot`, `welds`, `status`), `NDEResult` (`result`, `report_no`, `reject_reason`, slot `report`).
**Events:** `Weld.FitUp`, `Weld.Welded`, `Weld.VisualRecorded`, `Weld.PwhtRecorded`, `Weld.Repaired`,
`NDE.Selected`, `NDE.Requested`, `NDE.ResultRecorded`, `NDE.Rejected` (webhook), `Weld.ProgressQuantity`.
**Current state:** `cur_piping_line`, `cur_piping_iso`, `cur_piping_spool`, `cur_piping_weld` (with the denormalised
keys), `cur_piping_welder_qual`, `cur_piping_nde_rule`, `cur_piping_nde_request`, `cur_piping_nde_result`,
`cur_piping_nde_lot` (selection bookkeeping per class and lot).

**Commands:** `RecordFitUp`, `RecordWeld(weld_id, welders, wps_revision, welded_on)` (guards: each welder's
qualification covers process, position and range and is not expired; continuity within `piping.welder.continuity_days`;
the WPS pin is current), `RecordVisual`, `RecordPwht`, `RepairWeld` (creates `W-012R1` linked `repair_of`),
`DefineNdeRule`(`controller`), `RecordNDEResult` (`user`; in `AUTOMATION_COMMANDS` so the endpoint's service actor may run
it), `PublishWeldMap` (`controller`, create-only, compensable). Job `piping.nde_select` runs after `Weld.Welded` and
`NDE.Rejected` (penalty: the next `piping.nde.penalty_count` welds of the same welder and class are selected). **MCP:**
`weld_log`, `nde_status`, `welder_performance`, `propose_nde_request`. **TUI:** weld daily log grid (rows per iso, columns
fit-up, weld, visual, welder, WPS; `Enter` posts one `RecordWeld`), piping grid and record screens, NDE backlog tile.

**Reuse:** the derivation pipeline (the iso's derived weld map is a `DerivedDocument`; `PublishMapping` kind
`weld_map`; compensation reverses the created welds); the integration layer (`acme-nde` endpoint, HMAC, JSONata to
`RecordNDEResult`; a failed mapping lands in the error queue); Phase 2 rules of credit (`earned_fraction` reads weld
states: fit-up 30, welded 60, NDE accepted 10) and `awp.rollup` for IWP and cost-code figures; the lake second pass for
`mart_weld_progress` and `mart_nde_rejects`.

**Fanout:** WS-A (records, commands, NDE engine, import, progress) ∥ WS-B (weld log screen, inbound mapping and
actor, piping screens). Contract §2 fixes `RecordNDEResult` and the inbound payload so WS-B can write the mapping and
the simulator actor against a stub command before T04 lands.

**Demo (`just demo P3-I3`):** (1) `co.acme.piping@1.0.0` loaded; (2) a line, an iso at rev B, two spools; (3) the
weld map derived from the iso and published: 24 welds, numbering validated, a duplicate number refused; (4) weld log:
`RecordWeld` with a qualified welder passes, an expired qualification is refused, continuity broken is refused;
(5) NDE selection 10% RT for class CS1: 3 requests; (6) an inbound POST to `acme-nde` with a reject: `NDE.Rejected`,
a repair weld, penalty selection of 2 more; a bad signature is refused; (7) weld progress earns 60% on the IWP and
appears in `tl awp export progress`; (8) surfaces, readers, and `mart_weld_progress` after `tl lake sync`.

## I4 — Bolted joints, boltup, pressure testing

**Touches:** `piping` part 2; new `testing` module; `tl_core/readiness/types.py` (the wave 0 `SubjectFacts`
generalisation, contract §5); the Phase 2 pack renderer (`tl_mod_awp.pack` or wherever Phase 2 put it: a template
loader and HTML writer reused for the certificate); `tl_core/auth` (the re-authentication check of `SignCertificate`).

**Records:** `BoltedJoint` (`joint_no`, flange and gasket slots, `target_torque`, `method`, `status`), `BoltupRecord`
(`technician`, `tool` link to `quality.Instrument`, `values`, `passes`), `TestPackage` (`number`, `medium`,
`pressure`, `hold_time`, `limits`, links to lines, isos pinned, welds, joints, tags, subsystem), `PreTestChecklist`,
`PressureTest` (`actual_pressure`, `duration`, temperatures, `gauges` links, slot `chart`, `result`, `witnesses`),
`Reinstatement`. **Events:** `Joint.Assembled`, `Joint.Torqued`, `Joint.Verified`, `Joint.Broken`, `Joint.Reinstated`,
`TestPackage.ReadinessEvaluated`, `TestPackage.Ready` (webhook), `Test.ChecklistCompleted`, `Test.Executed`,
`Test.ResultRecorded`, `Certificate.Generated`, `Certificate.Signed`, `Reinstatement.Recorded`. **Current state:**
`cur_piping_joint`, `cur_piping_boltup`, `cur_testing_package`, `cur_testing_readiness`, `cur_testing_pretest`,
`cur_testing_test`, `cur_testing_reinstatement`, `cur_testing_certificate`.

**Commands:** `RecordBoltup` (guard: the tool is a calibrated instrument), `BreakJoint`, `RemakeJoint`,
`CreateTestPackage`, `AddPackageScope`, `CompletePreTestChecklist`, `ExecuteTest` (guards: readiness all `ok`,
every gauge calibrated), `RecordTestResult`, `GenerateCertificate` (renders from `dev/templates/certificate.html.j2`
into slot `certificate`, records the sha256 of the canonical supporting record set), `SignCertificate(certificate_id,
record_set_hash)` (`controller` or the P3-Q5 role; refused when the hash differs from the live set; refused when the
caller's session is older than `auth.reauth_window_minutes`, the re-authentication stub), `RecordReinstatement`.
**TUI:** boltup fast-entry (joint, tool, values; one line), joint register, test package record with a readiness
tab (the Phase 2 readiness screen reused with the subject swapped), certificate view.

**Reuse:** the readiness contract (checks `welds_accepted`, `nde_complete`, `joints_in_state`, `punch_a_closed`,
`gauges_calibrated`; `documents_current` reused as is because it reads pinned links); the Phase 2 renderer; file slots;
the webhook catalog (`TestPackage.Ready` from the `tl:event_type` class); `Instrument` from I2 for tools and gauges.

**Fanout:** one supervisor; the readiness checks and the signature are the engine pieces, the rest are screens
and reads.

**Demo (`just demo P3-I4`):** (1) a joint torqued with a calibrated tool; an uncalibrated tool refused; (2) a package
over two lines: readiness 3/6 with the blocking welds, a punch A and a stale pinned iso as `resolve_via`; (3) the welds
accepted, the punch cleared, the pin refreshed, the gauge calibrated: 6/6 and `TestPackage.Ready` delivered;
(4) pre-test checklist, `ExecuteTest`, result pass; (5) certificate generated; a signature with a stale hash refused; a
fresh sign-in signs; a user's signature refused; (6) reinstatement linking the broken joint and its remake record;
(7) surfaces, readers.

## I5 — Offline replicas

**Touches (core interface):** `tl_core/ledger/types.py` (`Ledger` gains `import_canonical(events)` for the mirror
segment and `Event` is unchanged; `PendingCommand` is a new table, not an event), `tl_core/uow.py` (the replica unit of
work appends to the local segment instead of the canonical ledger), `tl_adapters/sqlite` (the segment tables and HLC),
`tl_adapters/sync` (HTTP client), `tl_api/routes/sync.py`, `tl_core/sync/` (merge engine, policies), `schema/core/sync.yaml`,
`schema/core/annotations.yaml` (`tl:merge`), `tl_core/numbering` (provisional keys or `reserve_range`, P3-Q8),
`tl_core/auth` (replica identity), `tl_tui` (status bar, three screens), `tl_sim` (partition injection), `tests/property/`.

**Records (core streams, as ADR-0017 §1: configuration and activity, no `cur_core_record` row):** `Replica` (identity,
owner account, certificate fingerprint, scope subscription, `max_offline_days`, status active / revoked),
`SyncConflict` (command id, kind: scalar / transition / duplicate / schema, base, mine, theirs, resolution),
`SyncSession` (handshake, cursors, outcomes). **Operational tables (never projections):** `sync_pending_command`
(the local segment: `command_id` ULID, `replica_id`, `hlc`, `captured_at`, `effective_at`, `base_seq`, `base_versions`
JSON, `command_name`, `body` JSON, `schema_hash`, `local_hash`, `prev_local_hash`, `status` pending / pushed /
reconciled), `sync_mirror_cursor`, `sync_file_push`. **Events:** `Replica.Registered`, `Replica.Revoked`,
`Sync.Started`, `Sync.Completed`, `Command.Accepted`, `Command.AutoMerged`, `Command.Rejected`, `Conflict.Opened`,
`Conflict.Resolved`, `Record.Merged` (the natural-key duplicate), `Sync.Reconciled` (local, on the replica only;
never pushed). **Current state:** `cur_replica`, `cur_sync_conflict`.

**Commands and surfaces:** `RegisterReplica` (`admin`), `RevokeReplica` (`admin`; pending commands quarantined, not
merged), `SubscribeScope`, `TakeOffline(iwp_ids | area_ids)` (pulls records, pinned revisions, slices into the local
cache), `tl sync now|status|conflicts`, `ResolveConflict(conflict_id, choice: keep_mine | keep_theirs | merge_fields |
merge_records, fields)`, bulk resolve. **API:** `/sync/handshake`, `/sync/pull`, `/sync/files`, `/sync/push`, `/sync/ack`
(contract §3). **TUI:** status bar, provisional ◌ rows (every grid reads a `provisional` column from the local
current state), take-offline picker, sync screen, conflict screen.

**Reuse:** the command runner (ADR-0017 §7) re-executes commands as the replica's owner with the owner's access
resolved at merge time (a revoked role rejects); the confidentiality filters on pull (`filter_events`,
`hidden_event_streams` with the owner's viewer; restricted and privileged never leave the server); `allocate_key` at
merge; the archive verifier for the local hash chain; the property-test style of the lake (rebuild equals incremental).

**Fanout:** WS-A (protocol, replica ledger, merge engine, policies, property harness) ∥ WS-B (replica identity and
revocation, site node, UX). Contract §3 is the wire protocol and `PendingCommand`; WS-B builds the screens over a
fake sync client. The ADR precedes everything.

**Demo (`just demo P3-I5`):** (1) two replicas registered and scoped to IWP-0042; both take it offline; (2) the
server goes away (the demo stops the API); replica A records welds W-001..W-005, replica B records W-006..W-008 and
W-003 (a duplicate), both edit W-002's visual result; (3) sync A: all accepted; sync B: W-006..W-008 accepted, W-003
a duplicate conflict, W-002 a scalar conflict; (4) the conflict screen merges W-003 (`Record.Merged`, `same as`) and
keeps theirs on W-002; (5) replica B is revoked; its next push is quarantined; (6) the property suite (convergence,
idempotency, no lost writes, causal order) over 200 generated histories on SQLite; (7) a restricted correspondence item
in the scope never appears in either replica.

## I6 — Models: ingest, objects, mapping, slices

**Touches:** new `models` module; `tl_extract` (`ifc` extractor: IfcOpenShell, ifctester; new dependencies, licence
gate: IfcOpenShell is LGPL — P3-Q9); `tl_mod_documents` (document type `model`, `PublishMapping` kind `model_props`);
`schema/modules/models/`; operational `model_object` table (`schema/modules/models/object_tables.yaml`, the ADR-0015
typed-rows pattern); jobs `models.ingest`, `models.convert`, `models.slice`; `dev/` Node detection for xeokit-convert.

**Records:** `ModelRevision` (`derived from` a `documents.Revision`; `ifc_schema`, `object_count`, `validation` summary,
`conversion_status`), `ObjectMappingRule` (`source_property`, `target_type`, `class_filter`, `regex`, `transform`),
`FederatedView`, `Viewpoint` (camera, sections, visibility sets, slot `snapshot`, markup), `Overlay` (saved query plus
colour rules), `ModelSlice` (rule, source revisions, sizes, `eligibility`, slots `ifc`, `xkt`, `thumb`), `SliceRule`.
**Operational:** `model_object` (`revision_id`, `global_id`, `ifc_class`, `name`, `storey`, `space`, `props` JSON,
bbox), bounded by `models.ingest.max_objects` (default 500 000; over it the revision is `desktop_only` and partial).
**Events:** `ModelRevision.Registered`, `ModelRevision.Validated`, `ModelRevision.Converted`,
`ModelRevision.ObjectsExtracted`, `ModelRevision.Published` (webhook), `Mapping.Applied`, `Mapping.Proposed`,
`Slice.Generated`, `Slice.Split`, `Slice.Regenerated`. **Current state:** `cur_models_revision`, `cur_models_rule`,
`cur_models_view`, `cur_models_viewpoint`, `cur_models_overlay`, `cur_models_slice`, `cur_models_mapping` (object ⇄
record, with `source` rule / proposal / manual).

**Commands:** `RegisterModelRevision` (from the ingest job after the `props` derived document validates),
`DefineMappingRule` (`controller`), `ApplyMappings` (job; links `references` from the mapped record to the model object
id; ambiguous → proposals with `tool: mapping`, accepted by a person), `DefineSliceRule`, `GenerateSlices` (job),
`PublishModelProps` (`controller`, `PublishMapping` kind `model_props` into `engineering.Tag` psets with provenance).
**MCP:** `model_objects`, `mapping_status`, `revision_diff`, `slice_list`. **TUI:** object tree (storey → class → object),
properties, mapping status, revision diff, slice list.

**Reuse:** M1 revision control as is (a model document is a document; transmittals, pins, the feed card and the
stale rule need nothing new); the derivation pipeline (ingest is an extractor; the `props` rendition is a
`DerivedDocument`; validation reports as P1-I3); the envelope (IfcOpenShell runs inside it, memory-capped: an IFC can be
gigabytes; the reader refuses past `models.ingest.max_ifc_mb`); proposals for ambiguous mappings; the job runner.

**Fanout:** one supervisor. The engines (ingest, mapping, slicing) are sequential and share the object table.

**Demo (`just demo P3-I6`):** (1) a model document with an IFC revision (the fixture IFC, small); (2) ingest: schema
check, IDS valid, 1 200 objects extracted; an IFC over the size bound refused with a fixed message; (3) mapping rule
`Pset_Tag.TagNumber → engineering.Tag`: 90% linked, 12 ambiguous proposals, one accepted; (4) slices per IWP and
subsystem; a slice over 50 MB (the setting lowered to 1 MB for the demo) split by storey; (5) XKT converted when Node
is present, else `desktop_only` with the stub note; (6) revision B: diff lists added, removed, changed; floating slices
regenerated; `ModelRevision.Published` delivered; (7) surfaces, readers.

## I7 — Model workspace, viewpoints, overlays, spatial context, TUI panel

**Touches:** new `web/` workspace (TypeScript, Vite, Playwright; `just test-web`; one owner); `tl_api/routes/models.py`
and `routes/pairing.py`; `tl_core/query` (filter `has:model_context`, a core change outside §7 but shared: the
query owner reviews); `tl_mod_models/context.py` (resolver), job `models.context`; `cur_models_context` side table
(`record_id`, `ctx_model_id`, `ctx_object_count`, `ctx_source`, `ctx_location_label`, `ctx_object_ids` bounded);
`schema/core/record.yaml` gains the four `xref_model_*` envelope slots (brief §6.2) — a `schema/core/**` gate, and the
generated DDL adds four nullable columns to every `cur_*` table (no §7 change; the migration of existing rows is a
no-op because the columns are nullable); `tl_tui/widgets/model_context_panel.py`; BCF reader in `tl_extract`.

**Records:** none new beyond I6's `Viewpoint` and `Overlay`; `PairingSession` is an operational row (`code`, account,
expires). **Events:** `Record.Located` (the xref fields set by `LocateInModel`), `Viewpoint.Saved`, `Overlay.Defined`,
`Context.Recomputed` (one per revision publish, not per record). **Current state:** `cur_models_context`.

**Commands and surfaces:** `LocateInModel(record_id, objects | location)`, `SaveViewpoint`, `DefineOverlay`,
`BulkLinkObjects(object_ids, record_id)`, `RaiseFromViewpoint(kind, viewpoint_id)` (calls I1, I2 or P1-I6 commands
with the viewpoint attached), `OpenPairing` / `DriveViewer(code, action)`; API: `/models/search` (the query language
plus object search), `/models/context/{record_id}`, `/models/slices/{id}/xkt`, `/pairing/*` (SSE on the change feed);
TUI: context panel on any record (location breadcrumb, nearby tagged objects, object counts by status), keys `B`
(deep link and QR) and `P` (pairing). **Web:** the split workspace over `ModelViewer` (contract §4).

**Reuse:** the query language and the change feed (overlays update live from `/changes`); generated forms (the
record panel renders the same JSON Schema the TUI forms use); links (`references` to object ids); the viewer only
loads slices the viewer's confidentiality filter allows (`cur_models_context` rows are filtered like every row).

**Fanout:** WS-A (web workspace) ∥ WS-B (resolver, forms, TUI panel, pairing, guest page). Contract §4 fixes the
viewer interface and the context view so WS-B's TUI panel and WS-A's page read one shape.

**Demo (`just demo P3-I7`):** (1) search `weld nde:pending area:A12` lists 7 welds and highlights 7 objects;
(2) selecting an object opens its weld; arrowing the list walks the model; (3) an RFI raised from a viewpoint carries it;
(4) an NCR with no xref shows context inherited weld → spool → iso with `ctx_source = inherited`; (5) overlay "weld
status" colours objects; a weld recorded in the TUI recolours live; (6) the TUI panel shows the text context and pairs
with the open page by code; `B` prints a deep link; (7) a restricted record shows no context to a user; (8) Playwright
proves (1), (2), (5).

## I8 — External parties, remaining domains, hardening, exit

**Touches:** `tl_core/auth` (role `external`, party binding, guest links in `schema/core/auth.yaml`),
`tl_core/confidentiality.py` (`Viewer.party`; `hidden_sql` gains the party predicate for external viewers),
`tl_api/routes/guest.py`, `web/portal`, `schema/fixtures/correspondence/domains/{hse,interface,legal}.yaml`,
`tl_sim` (actors, injections, `ROLE_NAMES`), `dev/demos/P3-I8.sh`.

**Records:** `GuestLink` (core stream: purpose, record, party, expires, OTP flag, uses), `Party` binding on `Account`.
**Events:** `Account.BoundToParty`, `GuestLink.Issued`, `GuestLink.Used`, `GuestLink.Expired`; the acts a guest performs are
the existing commands with actor `guest:<party>/<link>` and source `guest:`. **Current state:** `cur_guest_link`.

**ABAC predicate (ADR at wave 0):** an external viewer reads a record when the record, or a record it `belongs_to`
(one hop, bounded), carries the viewer's party in a typed `party_id` column or in a `references` link to the
`correspondence.Party` record, and the record's class is `internal`; `restricted` and `privileged` are never readable
by an external account; threads follow the record; the feed shows only cards of readable records; MCP agents of an
external account hold nothing (closed until listed).

**Surfaces:** `BindAccountToParty` (`admin`), `IssueGuestLink` (`controller`; purposes `sign_off_inspection`,
`respond_rfi`, `upload_mtr`, `acknowledge_transmittal`), guest routes that run exactly one command each; the portal
page; `tl guest issue|ls|revoke`. **Legal domain:** `privileged` default, feed policy `none`, `integration: thin`,
and tests that the replica pull, the lake sync, the exports, the semantic index and the MCP read tools never carry a
Legal item's text.

**Simulator:** actors `qc_inspector`, `welding_crew`, `nde_contractor` (posts to `acme-nde`), `client_rep` (uses guest
links); injections `calibration_failed`, `nde_reject`, `design_revision` (against a pinned iso: the weld map's
revision goes stale), `partition` (a replica offline for N days). Operators: certificate signer, NCR disposition.

**Fanout:** one supervisor; T01–T05 in wave 4 beside I7, the rest in wave 5.

**Phase-exit demo (`just demo P3-I8`):** on `refinery-piping-medium` v3, SQLite and Postgres: (1) the welding crew
records welds through the daily log, half of them on a replica that syncs later; (2) NDE selected; the contractor's
results arrive by inbound webhook; a reject makes a repair weld and penalty selection; (3) the test package over the
lines becomes ready when the welds, joints, punch and gauges are right; the test is recorded; the certificate is
signed by an operator; (4) weld progress is colour-overlaid in the model workspace (Playwright) and the TUI shows the
context; (5) the client rep signs off an inspection by guest link; (6) a Legal item exists and no feed, export, lake
row, replica or MCP answer carries its text; (7) every §12 M5, M6, M7 base report runs with a non-empty result.

---

## Core-interface touches (ADR needed before the increment)

| Increment | Interface (03 §7) | Change | Alternative without a change |
|---|---|---|---|
| I5 | `Ledger` | `import_canonical(events: Sequence[Event]) -> None` for the mirror segment (events carry upstream `seq`, `hash`, `prev_hash`; the replica stores them as given and never re-hashes) | A replica-only adapter method outside the Protocol; then `UnitOfWork` on a replica must still route appends to the local segment, which is a `UnitOfWork` change |
| I5 | `UnitOfWork` | A `ReplicaUnitOfWork` whose `append` writes a `PendingCommand` and provisional events to the local segment and runs projectors over them | None: the TUI and commands call `uow.append`, so the replica must satisfy the Protocol |
| I5 | `Event` | Unchanged: `captured_at` and `hlc` live on `PendingCommand`; after merge the canonical event has `effective_at` from the command and `recorded_at` from the server | — |
| I7 | `schema/core/record.yaml` envelope | Four `xref_model_*` slots (brief §6.2); generated DDL adds nullable columns everywhere | `cur_models_context` only, with `LocateInModel` writing there; loses the brief's envelope fields on forms |
| I4 | Phase 2 frozen contract `tl_core/readiness/types.py` | `SubjectFacts` base, `IwpFacts(SubjectFacts)`, `ReadinessCheck.subjects` | A second readiness engine in `testing` (rejected: two engines, two screens) |
| I8 | ADR-0016 `Viewer` | `party: str | None`; the party predicate in `hidden_sql` | A route-level filter per read path (rejected: ADR-0016 says one seam) |
