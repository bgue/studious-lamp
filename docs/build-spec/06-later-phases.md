# Build spec 06 — Fanout seeds for Phases 1–5

Each phase starts with an orchestrator fanout. These seeds say what the orchestrator decomposes, which parts are
supervisor engines, and where implementer volume lies. Module work follows the brief's pattern: schema → generated
surfaces → handlers → screens → reports → simulator actors (§29.8).

## Phase 1 — Information backbone

| Workstream | Supervisor engines | Implementer volume | Human gates |
|---|---|---|---|
| M1 Document Control | Revision scheme engine; derivation pipeline job orchestration; pin/stale resolution | Record types from §9 M1 tables (schema tickets with approver), transmittal workflow, renditions + file slots, extractor plugin interface + CSV/XLSX extractor, validation reports, TUI register and revision screens, base reports | Schema merges |
| M2 Engineering Data + Standards | Numbering-pattern registry integration; tag rename/split/merge with `supersedes` | Tag/TagClass schema, Standards registry records and code lists, bulk import diff preview, pattern-violation report | Schema merges |
| M10 Correspondence core + Technical, Document control, Commercial, General | Response clock engine (calendars, stop rules; §R11); domain definition compiler; confidentiality filters | Domain subtypes and workflows as YAML, numbering patterns, registers, clocks screen (sketch 7), email-in parser, templates | Commercial/legal lead on clocks and workflows; security on confidentiality |
| M11 Cost + XER | XER parser and snapshot compare | XER table loaders to bronze, `ScheduleActivity` typed tables, look-ahead query, cost snapshot import, orphaned-link health check | — |
| Schema workbench + registry workflow | Package lifecycle state machine, `linkml diff` classification, impact report | Workbench screens (sketch 8), `tl schema` subcommands, conformance dashboard, waiver record | Schema owners |
| Integration | Actions registry executor, rules engine evaluation with loop protection, inbound mapping (JSONata) runtime | Action/rule/enricher records, inbound endpoint routes, dry-run, error queue, first AI extraction enricher in `propose` mode | Security on inbound signing |
| Threads | Dispatch command parser and permission checks | Thread stream, events, TUI thread tab (sketch 13), slash commands → existing commands | — |
| Legacy loaders | Profiling + mapping framework | XLSX/CSV extractor, DMS export loader, reconciliation report | — |
| Lake | Marts for documents and XER history | SQL models, tests | — |

Merge order: Standards/M2 → M1 → M11 → Integration → M10 → Threads → Workbench → Loaders → Lake.

## Phase 2 — Execution planning and materials

| Workstream | Supervisor engines | Implementer volume |
|---|---|---|
| M3 field work packaging | Readiness computation over links (`cur_readiness`), constraint need-by derivation, rules-of-credit progress rollup, IWP split | WBS/CWA/CWP/IWP/Constraint schema, lifecycle workflows, weekly cycle screens, readiness screen (sketch 5), constraint review, IWP pack template, KPIs, subcontractor party access |
| M4 Materials | Inventory projection from transactions, reservation logic | Item library schema, locations, receipts with MTR slots, toolcrib fast-entry screen, company-level aggregation, reports |
| M9 Requisitions/WO | Generic request → WO engine | Scaffold/labour/material/general specialisations, scaffold inspection due lists, dismantle dependency check |
| Simulator | Scenario rates for AWP/materials/scaffold | Actors: planner, materials coordinator, scaffold supervisor; fault injection `material_late` |
| Lake | Gold marts: readiness history, materials, schedule trend | SQL models |

## Phase 3 — Quality and piping

| Workstream | Supervisor engines | Implementer volume | Human gates |
|---|---|---|---|
| M5 Quality | Issue engine shared by NCR/CAR/QSR; calibration impact query | ITP/checklist/inspection schema, deficiency raise-from-anywhere, checklist runner screen, instrument block rules, Quality correspondence domain | — |
| M6 Piping | NDE selection rules with lots and penalty selection; welder qualification checks | Line/iso/spool/weld/joint schema, weld daily log screen, boltup entry, progress quantities rollup | — |
| M7 Pressure testing | Package readiness computation | Test package schema, pre-test checklist, certificate template, reinstatement | — |
| Offline replicas | Replica protocol, command replay, merge policies, conflict resolution (§22) | Replica registration, mirror/local segments, sync CLI, conflict screen, property tests (convergence, idempotency, no-lost-writes) | Security on replica revocation |
| M12 Models | Object mapping engine, spatial context resolver (§23.5), slice generator | IFC ingest pipeline jobs, XKT conversion job, `ModelObject` projector, web workspace page (TypeScript), viewpoints, overlays, TUI context panel and pairing | Licence decision Q9 |
| External parties | ABAC party scoping, guest-link signing | Party accounts, guest-link flows, portal page | Security |
| Simulator | Partition injection, NDE contractor via inbound webhook | Actors: QC inspector, NDE contractor, welding crew, client representative |

## Phase 4 — Completions and turnover

| Workstream | Supervisor engines | Implementer volume |
|---|---|---|
| M8 Systems completion | Certificate snapshot hashing; ITR auto-generation per tag class × phase | System/subsystem/ITR/certificate/dossier schema, completion dashboards, burn-down, dossier builder, exports |
| Simulator | — | Completions engineer actor |

## Phase 5 — Expansion

Cost and schedule display modules, P6 XML and EPPM connectors, cross-project lake catalogs, PWAs on the replica protocol, full web client, connector hardening, broadened MCP write tools. Each is its own fanout; the orchestrator writes the seed when the phase starts.

## Standing rules for later phases

- Every module fanout starts with the schema workstream merged (types, psets, file slots, expected links, spatial paths, merge policies, settings keys) before handlers and screens are ticketed.
- Every module adds simulator actors and a legacy mapping template before its increment closes (§29.8).
- Any new correspondence domain, clock, or contractual workflow carries a commercial/legal human gate.
- Budget heuristic per module: 1 supervisor per 2–3 record types, 10–25 implementer tickets per supervisor, one orchestrator fanout per phase plus one per cross-module escalation.
