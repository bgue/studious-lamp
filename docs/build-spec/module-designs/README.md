# Module designs — the remaining user-facing modules

Status: v0.1, 2026-10-30, planner tier. One file per module below; `deployment-and-merge.md` covers the owner's
requirement that the product runs centrally, on-premises or on-device and merges. These are **designs**, not specs:
they say who uses a module, which records and states it has, which logs and record screens it needs (in the log
standard), its workflows, links, integrations, reports, roles and confidentiality, what the first increment holds,
and what the owner must decide. Spec writers add field-level detail; builders implement from the specs. Everything
stays within the brief (`§n`) and the phase plans (`08-` to `11-`); a line that goes beyond them is marked
**(proposed)**.

## 1. The remaining user-facing modules

Built on the trunk today (Phase 0 and 1): M1 documents, transmittals, reviews; M2 standards and tags; M10
correspondence with the General, Document-control, Technical/RFI and Commercial domains; M11 cost and schedule
snapshots; threads, integration layer, schema registry, legacy loads, lake marts. Not built:

| File | Module | Brief | Phase (plan) | Purpose in one line |
|---|---|---|---|---|
| `field-work-packaging.md` | M3 Field work packaging (WBS, AWP) | §9 M3, §16 | 2 (I1, I2, I5, I6) | Break the GC's scope into CWPs and IWPs, clear constraints, release constraint-free IWPs to foremen, earn progress |
| `materials.md` | M4 Materials | §9 M4 | 2 (I3; toolcrib in I4-B) | Item library, receipts with heat numbers, ledgered stock, reservations that feed IWP readiness, toolcrib |
| `requisitions-and-scaffold.md` | M9 Requisitions and work orders (scaffold, labour, material, general) | §9 M9 | 2 (I4-A, I4-B) | One request-to-work-order engine; scaffold assets with tags and inspections |
| `quality.md` | M5 Quality (Issue engine, ITPs, inspections, deficiencies, calibration) | §9 M5 | 3 (I1, I2) | NCR/CAR/QSR, checklists, inspections with calibrated instruments, punch from any record |
| `piping.md` | M6 Piping (welds, NDE, bolted joints) | §9 M6 | 3 (I3, I4) | Weld log, NDE selection and results, welder continuity, boltup with calibrated tools |
| `pressure-testing.md` | M7 Pressure testing | §9 M7 | 3 (I4) | Test packages with live readiness, test execution, signed certificate, reinstatement |
| `models.md` | M12 Models (3D) | §23 | 3 (I6, I7) | IFC as versioned documents, object mapping, slices, web model workspace, model context on any record |
| `external-parties.md` | External parties and portal | §18.11 | 3 (I8) | Subcontractor, client and inspector access by scoped accounts and guest links; the portal page |
| `systems-completion.md` | M8 Systems completion and turnover | §9 M8 | 4 (I1, I2) | Subsystems, ITRs, punch, certificates with snapshot, handover dossiers |
| `cost-display.md` | Cost display and commenting | §13, §2.2 | 5 (I1) | Cost code tree and measure matrix over the M11 mirror, drill-through, comments |
| `schedule-display.md` | Schedule display and commenting | §13, §2.2 | 5 (I2) | Activity list and text Gantt over XER snapshot history, readiness overlay, comments, statusing export |

Not separate modules, but user-facing work the plans still owe: the Quality, HSE, Interface and Legal correspondence
domains (domain files on the built M10, Phase 3 I1 and I8; see `quality.md` and `external-parties.md`); offline
replicas and the sync and conflict screens (Phase 3 I5; `deployment-and-merge.md`); the fast-entry screens of §10.5
(each sits in its module file); mobile PWAs and the full web client (Phase 5, out of these designs).

## 2. Recommended build order and why

The phase order is fixed (`06-later-phases.md` rule 5); within it the order below follows dependencies and user value.

| # | Build | Why now |
|---|---|---|
| 1 | M3 part 1: WBS, path of construction, CWA, CWP (P2-I1) in parallel with M4 (P2-I3) | Different modules, no shared file; the IWP needs both the CWP scope and the materials check |
| 2 | M3 part 2: IWP, constraints, readiness, sign-off (P2-I2) | The hub record of the product: every later module hangs a check, a link or a quantity on the IWP |
| 3 | M9 requisitions and work orders, then scaffold and toolcrib (P2-I4) | Scaffold and labour checks complete the readiness picture; the material requisition closes the loop to M4 |
| 4 | M3 part 3: weekly cycle, rules of credit, progress, IWP pack, closeout (P2-I5) | The visible weekly routine for planners and foremen; the Phase 2 exit |
| 5 | M5 inspections, deficiencies and calibration (P3-I2) **before** the Issue engine (P3-I1) **(proposed re-sequence, orchestrator ADR)** | Deficiency, Inspection and Instrument are consumed by scaffold inspections (M9), receiving (M4), test packages (M7), ITRs (M8) and the weld log; the NCR engine is consumed by fewer screens and can land one wave later |
| 6 | M6 welds and NDE (P3-I3), then joints and M7 (P3-I4) | The Phase 3 exit chain; welds supersede the generic scope items of M3 |
| 7 | M12 ingest and mapping (P3-I6), then the workspace (P3-I7) | Independent of 5 and 6 until the spatial paths need welds; licence gates first |
| 8 | Offline replicas (P3-I5) once welds, inspections and toolcrib exist | Merge policies are tested over real field-capture commands |
| 9 | External parties and portal (P3-I8) | Needs the party scope on the viewer and `api.public_base_url`; every module above gains a party column |
| 10 | M8 (Phase 4) | Reuses ITR runner (M5 checklist runner), punch (M5), readiness (M3), certificates (M7), dossiers (archive bundle) |
| 11 | Cost and schedule display (Phase 5) | Both read only data that exists today (M11). **(proposed)** They can be pulled earlier if the owner wants planners to see a Gantt beside the weekly cycle; they need no new module seam |

## 3. Shared building blocks every design reuses

| Block | State | Where | What every design assumes |
|---|---|---|---|
| Log standard | built (P1-UX2, UX3) | `tl_tui/widgets/log_screen.py`, README "Log screens", `tui-layout` skill | Breadcrumb `P123 › <Log> › <Number>: <title>`, filter, list (Number, Subject, State first; constant columns hidden), panel with identity line, state line, dim summary line, named sections, actions bar, keys row, status line; panel right of the list from 160 columns |
| Record screen | built (P1-UX) | `record_screen.py`, `details/` | Enter opens Details, Properties, Links, History, Thread, Files; Details rows are built once per type and shared with the panel; technical details only under Ctrl+D |
| Actions from the server | built (P1-UX2) | `ModuleSpec.actions`, `allowed_actions(record)` | A log shows only what the viewer may do to that row in its state; an action that needs words opens `ActionFormScreen`; refusals land in the status line. Each design lists its actions per state and role |
| Property sets | built | layered psets, `bound_psets`, forms from the effective schema | Extended properties live on the Properties tab grouped by set; mandatory sets per class and state are guards, never screen logic |
| Workflows | built | `schema/fixtures/workflows/<module>-<class>.yaml`; guards `required_psets`, `conformance`, `required_links`, `expected_links`; roles from the account | A controlling act (approve, sign off, issue, close, disposition) is a module command with an access word, never a `roles` guard (R-P2-3) |
| Access and roles | built | `admin`, `document_controller`, `user`; access words; agents propose | Three roles exist. A design that needs another role (workface planner, cost controller, quality, inspector, external) says so under *Roles*; new roles are a human gate (ADR-0013) |
| Numbering | built; offline keys designed | `allocate_key`, patterns in a standards edition; `reserve_range` is a stub | One pattern per record kind in the module's `co.acme.<m>@1.0.0.yaml`; gap-free where the owner says (Q7) |
| Links | built | 13 relations, pins, class-aware stale pins, trace, reference tray, `tl:expects_link` | No module adds a relation; the target type carries the meaning; expected links without a type report `n_a` (P2-Q8) |
| Threads and dispatch | built (ADR-0018) | `threads.enabled_types`; targets by entry point | A module registers its `/raise`, `/dispatch`, `/hold`, `/status` targets; messages never mutate records |
| Files and preview | built (slots, PDF page 1, open externally); bulk upload by filename pattern designed §20.2 | `cur_files`, `file_panel.py` | Slots with `required_in_states`; **(proposed)** the bulk uploader lands with piping (NDE reports) and is shared |
| Feed | built (cards, posts, hashtags, `#hold` proposal) | `tl_core/feed` | Burst aggregation and `importance: low` for engine events (R-P2-16); a post converts into a record with `derived from` |
| Confidentiality | built (ADR-0016: `internal`, `restricted`, `privileged`; viewer; walking tests); party scope designed (Phase 3 I8) | `tl_core/confidentiality.py` | Every new route, tool, feed, replica pull, export carries the viewer; hidden = missing. Module records are `internal` unless a design says otherwise |
| Derivation and publication | built (ADR-0014) | `DocumentSchema`, `PublishMapping` kinds, compensation | Every import (MTO, weld map, model props, checklists) is a mapping kind and a create-only command; no second import path |
| Readiness engine | designed (Phase 2 contract §1; subjects in Phase 3 §5) | `tl_core/readiness/` | Plug-in checks by entry point, one evaluation event per subject, `ok / blocked / n_a / unknown`, `resolve_via` jump; subjects IWP, test package, certificate |
| Job queue | built; shared worker designed (R-P2-13) | `tl_core/jobs` | Bounded, state-derived runs; one worker per module until `tl worker` exists |
| Integration layer | built (ADR-0017) | actions, rules, inbound endpoints, enrichers, signed webhooks | Every module names its webhook events (from `tl:event_type` classes), its inbound mappings and its proposable commands |
| Reports | built pattern (`tl <m> report`, API, lake marts); ledgered report runs (§12) not built | `packages/tl-lake` | Each design lists its §12 reports; the "saved query + template + parameters, ledgered run" model is a **(proposed)** shared piece for Phase 4 dashboards |
| Dashboards and inbox | designed (§10.2); none built beyond the correspondence triage inbox and the review queue | — | **(proposed)** one tile widget (count, mini-bar, drill to a filtered log) built with P2-I2 T08 and one "My work" log (assignments, approvals, due, mentions) built with M9 approvals; every design lists its tiles |
| Fast-entry screens | designed (§10.5); none built | — | Keyboard-only, one line per fact, guards shown before Enter, provisional rows `◌` on replicas |
| Simulator, legacy loader, lake marts | built pattern | `tl_sim/actors`, `tl load`, `tl lake mart` | Each module ships an actor desk, a loader template and its marts before its increment closes (rule 2) |

## 4. Cross-cutting questions for the owner

1. **Roles.** Three roles cannot express planner sign-off, cost authority, quality disposition, scaffold tagging or an
   external party (P2-Q2, P2-Q3, P3-Q4, P3-Q5). Decide one project-role model before Phase 2 wave 0 rather than one
   role per module.
2. **Re-sequence Phase 3** so inspections and deficiencies (P3-I2) precede the Issue engine (P3-I1) (§2 row 5).
3. **Browser surface.** The P1-UX follow-up asked whether the full web client should move earlier; M12's workspace
   and the portal are the first browser pages either way. A yes changes where the cost and schedule display modules
   are built first.
4. **Deployment shapes.** `deployment-and-merge.md` §5 asks which record types may be written offline, and whether a
   site server can be the authority for a project with no central node.
