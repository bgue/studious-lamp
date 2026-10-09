# Throughline — Construction Management Suite: Product & Technical Brief

**Working name:** *Throughline* (placeholder - configurable name)
**Document status:** Draft v0.4 for discussion
**Scope of this brief:** Product and technical brief for a general contractor's construction management suite: a Textual TUI on an append-only ledger with realtime access, open APIs/MCP, initial functional modules, base reporting, roadmap, tech stack, and implementation plan.
**Change log:** Appendix A.

---

## 0. Why Throughline: gaps and pain points in current approaches

General contractors today run projects with one of two approaches, and usually a mix of both: a **collection of systems** glued together by people and spreadsheets, or a **unified platform** that tries to do everything in one product. Each fails in predictable ways.

### 0.1 Collection of systems (best-of-breed tools + spreadsheets)

A typical stack: a document management system, P6, a cost system, a completions database, a QC/welding app, materials in an ERP, email and shared drives, plus many spreadsheets in between.

| Pain point | What it looks like on site |
|---|---|
| **Identity drift** | The same tag, line, or weld is keyed differently in each system. Tag lists diverge, and reconciling them becomes someone's full-time job |
| **References live in people's heads** | The link between an NCR and its welds, or an RFI and the drawing revision, exists as free text or a filename. It cannot be followed or queried, and breaks silently when a revision changes |
| **Re-keying and spreadsheet glue** | Data is copied by hand or by weekly export. Errors creep in, it arrives late, and nobody can say where a number came from |
| **No single readiness picture** | "Can this IWP go to the field?" needs answers from the DMS, materials, scaffold, permits, and the schedule, collected by hand in a meeting |
| **Stale documents at the workface** | Crews build from superseded isos because a revision issue is not connected to the work packages that use it |
| **Brittle integrations** | Point-to-point interfaces that nobody owns break on upgrades; CSV hand-offs lose units, code meanings, and context |
| **Fragmented history** | "What did we know, and when?" means forensic reconstruction from inboxes, which is painful in claims and disputes |
| **Handover crunch** | Turnover dossiers are assembled at the end from many systems |
| **Context switching** | Different UIs, logins, and licences per tool; external parties need several accounts or get emailed spreadsheets |
| **AI and analytics are blind** | Data sits in silos without shared semantics, so cross-cutting questions go unanswered |

### 0.2 Unified (monolithic) platforms

| Pain point | What it looks like on site |
|---|---|
| **Rigid data model** | Adding fields or changing workflows is expensive, and upgrades break customisations. Projects stop asking and go back to spreadsheets |
| **Breadth without depth** | Generic modules are weak at specialist work (welding/NDE, boltup, completions, workface planning), so shadow systems reappear |
| **One workflow fits none** | Commercial, legal, QC, and field are forced through the same approval patterns |
| **Mutable records** | History is an audit log added later; corrections overwrite. There is no reliable "as at" view |
| **Closed integration** | Few events, rate-limited APIs, export as an afterthought: data lock-in |
| **Company vs project tension** | Either central control (projects cannot adapt) or free-for-all (no comparability across projects) |
| **Vendor-paced change** | Needs wait on someone else's roadmap |
| **Heavy UI, weak offline** | Mouse-heavy screens slow down power users; sites with poor connectivity struggle |
| **Costly external access** | Per-seat pricing keeps subcontractors and clients out, so email takes over again |
| **No spatial context** | Models live in separate viewers, with no link between a punch item and where it is |

### 0.3 Gaps common to both

- **Field work packaging** (AWP / workface planning) runs in separate tools or spreadsheets, disconnected from QC, materials, scaffold, and completions; constraints are chased by hand.
- **Correspondence and contractual clocks** are divorced from the records they concern.
- **Discussion and dispatch** happen in email and chat; decisions and the work they trigger never reach the records.
- **Configuration is opaque**: nobody can see who changed which rule, or when.
- **Adopting a new system is risky**: there is no easy way to run it in parallel with the incumbent and compare.

### 0.4 How Throughline responds

| Pain point | Throughline response |
|---|---|
| Identity drift, re-keying | One system of record; Standards registry numbering patterns; external IDs kept on every record (§6.4, §18.5) |
| References in people's heads | Cross-referencing as a first-class operation: create, maintain, surface, follow (§7) |
| No readiness picture | Live IWP readiness from linked records; COAA-style workface planning for the GC's field scope (M3) |
| Stale documents at the workface | Revision-aware pinned links with stale-pin alerts and re-pin (§7.3, M1) |
| Brittle integrations, lost meaning | Open API/MCP/webhooks with LinkML semantics in every payload (§18, §19) |
| Fragmented history | Append-only ledger with time travel (§5, §24.5) |
| Rigid data model | Layered property sets, runtime schema packages, extension record types (§6.3, §27, §31) |
| Company vs project tension | Company standards with enforcement levels; project custom sections; about:config settings with locks (§6.3, §30) |
| One workflow fits none | Per-domain workflows (M10), per-type workflows, configurable per project |
| Discussion outside the records | Optional record threads with dispatch (§21.5) |
| Weak offline | Replica sync and merge on the append-only ledger (§22) |
| No spatial context | Model workspace and slide-out model context for any record (§23) |
| Risky adoption | Load or mirror the incumbent project suite and reconcile before cutover (§29.9) |

---

## 1. Purpose and guiding principles

Throughline gives a general contractor (GC) one integrated system of record for project execution data: documents, engineering data, work packaging, materials, quality, piping, testing, systems completion, requisitions, and correspondence. It links to external cost and schedule systems rather than replacing them (initially).

Design principles:

1. **Ledger first.** Every change is an immutable, attributable event. Current state is a projection. Nothing is overwritten or hard-deleted; corrections are new events.
2. **Everything links.** Any record can reference any other record through typed, bidirectional links. Creating, maintaining, surfacing, and following references are first-class user operations (§7).
3. **Schema is the product.** One semantic model is the source of truth. Database DDL, validation schemas, API contracts, TUI forms, and MCP tool definitions are generated from it, so meaning survives every boundary.
4. **Flexible without being formless.** Every record type carries typed, versioned **property sets** (psets) so projects and companies can extend records without code changes, while remaining validated and queryable.
5. **Project-scoped, company-aware.** Transactional data lives in a project. Master data (item library, standards, people, crews, equipment, templates, schemas) lives at company level and is referenced or adopted by projects.
6. **Same core, many faces.** The TUI is the first client. The web client, API consumers, and AI agents (via MCP) all use the same service layer and the same permissions.
7. **Dev small, prod big.** SQLite + MinIO on a laptop; PostgreSQL + S3-compatible object storage in production. Same code, swapped adapters.
8. **Keyboard-first, mouse-complete.** Every action is reachable from the keyboard and by mouse in the TUI. Touch arrives with the PWAs (deferred, §22.9).
9. **Open by default.** Every record, event, action, and feed is addressable, subscribable, and invokable by external people, systems, and AI agents. Access is governed by the same permissions as the native clients. Every payload links back to its originating record and ledger position (§18).
10. **Files are first-class.** Most record types need uploads. Upload slots, file requirements, and file processing are part of the schema, not an afterthought (§20).
11. **Offline tolerant.** Disconnected sites keep working on local replicas that sync and merge through the append-only ledger (§22).
12. **Configurable in the open.** Every tunable behaviour is a visible, typed, ledgered setting, with company locks (§30).
13. **Extensible without releases.** New record types can be added as packages in a directory or object store, with only metadata held in the system (§31).

---

## 2. Scope

### 2.1 Initial scope (v1 modules)

| # | Module | Summary |
|---|---|---|
| M1 | Document Control | Document register, revisions, renditions, transmittals, schema-validated derived documents, processing pipeline |
| M2 | Engineering Data | Project-unique identifiers (tags) with psets; company Standards registry (mnemonics, naming conventions, code lists) |
| M3 | Field work packaging (GC WBS / AWP) | GC WBS mapped to cost codes; COAA-style workface planning: path of construction, CWA/CWP/IWP, constraints, release, backlog, progress, closeout (EWPs/PWPs as references) |
| M4 | Materials | Item library (abstract item masters), inventory from toolcrib to company, consumables, permanent materials, equipment |
| M5 | Quality (QC/QM) | ITPs, inspections, checklists, deficiencies, calibration, RFI/NCR/CAR/QSR |
| M6 | Piping | Lines, isos, spools, welds (incl. NDE, PWHT, repairs), bolted joints (boltup/torque/tension) |
| M7 | Pressure Testing | Test packages, test limits, pre-test checks, test execution, reinstatement |
| M8 | Systems Completion & Turnover | Systems/subsystems, ITRs, punch, certificates, handover dossiers |
| M9 | Requisitions & Work Orders | Generic requisition/WO engine; specialisations for Scaffolding, Labor, Materials, General |
| M10 | Correspondence | Shared core (register, threading, issue/receipt, response clocks) with a domain layer: Technical/RFI, Quality, Commercial, Legal, HSE, Interface, Document control, General, each with its own workflow |
| M11 | Cost & Schedule Links | Mirror of external cost codes (hours/qty/UOM/$ × budget/actual/FTC) and P6 schedules; linking only |
| M12 | Models (3D) | IFC models as versioned documents; XKT conversion; object-to-tag mapping; xeokit viewer with status overlays and viewpoints (§23) |

Cross-cutting v1 platform capabilities:

| Capability | Summary |
|---|---|
| Open integration layer | Granular subscriptions, outbound and inbound webhooks, actions, rules, enrichment, external parties, AI hooks (§18) |
| Cross-referencing | Create, maintain, surface, and follow references as first-class operations (§7) |
| Activity stream | Broadcast feed over the ledger (no replies) with lightweight hashtag semantics (§21) |
| Record threads | Optional per-record message threads with dispatch, enabled per project and type (§21.5) |
| Offline tolerance | Replica sync and merge on the append-only ledger for site laptops and site servers (§22) |
| Settings | about:config-style layered settings for companies and projects (§30) |
| Extension record types | Directory/object-store backed record types, metadata in the system (§31) |

### 2.2 Out of scope for v1 (but designed for)

- Costing frontend (display, commenting, later editing/forecasting)
- Schedule frontend (Gantt/list display, commenting, later progress statusing)
- Mobile and desktop PWAs (deferred; they will reuse the offline replica protocol, §22.9)
- Full desktop web client (v1 web surface is only the model workspace, because 3D needs a browser (§23.3), plus guest-link/portal pages for external parties (§18.11))
- Native mobile apps
- Authoring engineering and procurement work packages (EWPs/PWPs are referenced, not authored; M3)
- Payroll/timesheets (link to external only)
- Procurement/expediting beyond PO-line references

---

## 3. Organisational and data scoping model

```
Company (tenant)
 ├── Company master data
 │    ├── People, roles, crews, trades/crafts, subcontractors
 │    ├── Item Library (item masters, commodity codes, catalogs)
 │    ├── Standards registry (mnemonics, naming rules, code lists, UOMs)
 │    ├── Templates (ITPs, checklists, ITR forms, report layouts)
 │    ├── Schemas & pset definitions (company-level)
 │    ├── Equipment & instruments (fleet, calibration)
 │    └── Company warehouses / inventory locations
 └── Project (n)
      ├── Project settings, numbering schemes, adopted standards
      ├── Project-level pset definitions (extend company ones)
      ├── Project transactional data (all modules)
      ├── Project inventory locations (laydown, toolcribs)
      └── External links (cost system project, P6 project)
```

**Rules:**

- Every record has a `scope` of either `company` or `project:{id}`.
- Projects **reference** company master data by default. A project may **adopt** (snapshot + pin a version) or **override** (project-local variant with a `derived_from` link) any master record.
- Cross-project links are allowed only to company-scope records, or by explicit cross-project link with permission on both sides (e.g. moving equipment between projects).
- Standards and pset definitions are versioned; records capture the definition version they were validated against.

---

## 4. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│ Clients: Textual TUI │ (future) Web │ Scripts/SDK │ AI agents (MCP) │
└────────────┬───────────────┬──────────────┬───────────────┬─────────┘
             │ in-process or │ HTTP/JSON    │ WebSocket/SSE │ MCP
┌────────────▼───────────────▼──────────────▼───────────────▼─────────┐
│ Service layer (commands, queries, workflows, permissions, validation)│
│  ├── Command handlers → emit events                                   │
│  ├── Query handlers   → read projections                              │
│  ├── Workflow engine (declarative state machines)                     │
│  ├── Link service, Numbering service, Pset service                    │
│  └── Job runner (document processing, imports, reports, connectors)   │
├───────────────────────────────────────────────────────────────────────┤
│ Ledger (append-only event store) ──► Projectors ──► Read models       │
│        │                                         (tables, FTS, views) │
│        └──► Change feed (realtime bus) ──► subscribers, webhooks, MCP │
├───────────────────────────────────────────────────────────────────────┤
│ Storage adapters                                                      │
│   Dev:  SQLite (WAL, JSON1, FTS5)   + MinIO                           │
│   Prod: PostgreSQL (JSONB, LISTEN/NOTIFY, partitioning) + S3-compatible│
├───────────────────────────────────────────────────────────────────────┤
│ Connectors (in & out): cost system, P6, email, CAD/3D/eng. DBs, ERP   │
└───────────────────────────────────────────────────────────────────────┘
```

**Deployment modes**

| Mode | Use | Topology |
|---|---|---|
| **Local/dev** | Developer, demo, single user | TUI runs service layer in-process; SQLite file; MinIO via docker compose |
| **Shared/team** | Pilot project | Server process (API + workers) on Postgres; TUI connects over HTTP/WebSocket |
| **Production** | Multi-project company | Horizontally scaled API + workers; Postgres (HA); S3-compatible store; TUI served over SSH or locally; web client later |

The TUI must work in both **embedded** (in-process) and **remote** (API client) modes through a single client interface, so the same screens run against a laptop SQLite file or a production server.

**Read paths:**
- Interactive clients read **materialized current-state tables** (§5.4).
- History and audit come from the ledger.
- Analytics run on a **DuckLake lakehouse** (§28), fed incrementally from both, with Parquet in the same object store (MinIO in dev, S3-compatible in prod).

---

## 5. Ledger (append-only data backbone)

### 5.1 Event model

Every write is a command validated by the service layer, which emits one or more events in a single transaction.

| Field | Notes |
|---|---|
| `seq` | Global monotonic sequence (bigint) — the ordering backbone |
| `event_id` | ULID |
| `stream_id` | The record (aggregate) ID the event belongs to |
| `stream_type` | Record type (e.g. `qc.Inspection`) |
| `stream_version` | Per-record version; optimistic concurrency check |
| `event_type` | e.g. `Inspection.Created`, `Inspection.ResultRecorded`, `Link.Added`, `Pset.ValuesSet` |
| `schema_version` | Version of the event schema (for upcasting) |
| `scope` | `company` or `project:{id}` |
| `payload` | JSON, validated against event schema |
| `actor` | User, service account, or agent (with on-behalf-of user) |
| `recorded_at` | System time (transaction time) |
| `effective_at` | Business time (valid time) — e.g. the date the weld was actually made |
| `correlation_id` / `causation_id` | Ties command chains, imports, and automated processing together |
| `source` | `tui`, `api`, `mcp:{agent}`, `import:{job}`, `connector:{name}` |
| `prev_hash` / `hash` | Hash chain per scope for tamper evidence |

### 5.2 Rules

- **No updates, no deletes** on the event table (enforced by DB triggers/permissions in Postgres; by convention + checks in SQLite).
- **Corrections** are explicit events (`*.Corrected`, `*.Voided`) with a mandatory reason. Voided records remain visible in audit views.
- **Bitemporal queries:** "what did we believe on date X about the state on date Y" is supported via `recorded_at` and `effective_at`.
- **Snapshots** per stream every N events to keep rebuilds fast.
- **Projections** are disposable and rebuildable from the ledger. Projection schema changes = replay.
- **Upcasters** migrate old event versions on read; events are never rewritten.
- **Personal data:** where erasure is legally required, sensitive fields are stored encrypted per data subject; key destruction ("crypto-shredding") renders them unreadable without breaking the chain.
- **Files are immutable too:** object keys are content-addressed (SHA-256). A file is never replaced; a new revision references a new object.

### 5.3 Realtime data access

| Concern | Dev (SQLite) | Prod (Postgres) |
|---|---|---|
| Change feed source | In-process bus fed on commit; polling by `seq` for out-of-process readers | `LISTEN/NOTIFY` for wake-ups + `seq` cursor reads; optional logical replication for heavy consumers |
| Client delivery | In-process callbacks to TUI | WebSocket and SSE endpoints; subscriptions by scope, record type, record ID, or saved query |
| Delivery semantics | At-least-once, cursor-based (`seq`) | Same; clients resume from last `seq` |
| Outbound | Webhooks (signed), MCP resource-change notifications, connector pushes | Same, plus optional message broker (e.g. NATS) when scale requires |

Every open TUI screen subscribes to the records it shows; rows update live with a subtle highlight, and edit conflicts are detected through `stream_version`.

### 5.4 Materialized current state

Every entity type in the effective schema (§27.3) has a **materialized current-state table**. The ledger is the truth for history; current-state tables are what every client, report, API query, and MCP tool reads by default. They are generated, never hand-written.

| Generated object | Contents |
|---|---|
| `cur_<module>_<class>` (one per entity type) | Envelope columns (§6.2); typed columns for every class slot; **promoted** typed columns for company-standard pset properties marked `materialize: true` (§6.3); a JSON column with all pset values (including project custom sections); denormalised display columns for primary references (e.g. on `cur_piping_weld`: `spool_key`, `iso_key`, `iso_rev`, `line_key`, `iwp_key`, `test_package_key`); link counts by relation; file-slot completeness flags; workflow state, `state_entered_at`, age; `version`, `last_seq`, `effective_schema_hash` |
| `cur_links` | One row per live link (both directions resolvable), with relation, pinned/floating revision, and target status/void flags |
| `cur_pset_values` | Long-form typed index (record, pset, property, typed value columns, unit, layer: standard/custom/enrichment/source) for filtering and sorting on any property, including project custom ones |
| `cur_files` | Current file per slot, with processing and scan status |
| `cur_clocks`, `cur_constraints`, `cur_readiness` | Cross-cutting computed states (response clocks, AWP constraints, IWP/test package readiness) |
| `v_<class>` and `v_<project>_<class>` (views) | Reporting-friendly views with LinkML labels as column names. Project views add that project's custom pset properties as columns, so projects get wide tables without DDL churn on base tables |

Rules:

- **Updated in the same transaction** as the events that change them (inline projector). Writers get read-your-writes, and the TUI never shows stale state after a save. Heavier derived state (rollups, readiness across hundreds of records, search indexes) is updated asynchronously with a visible lag indicator.
- **Deterministic and rebuildable** from the ledger, per type, per project, or entirely (shadow rebuild, §24.2).
- **Generated from LinkML.** When a schema package is published (§27), the generator diffs the old and new effective schema and produces the DDL change: new columns, new views, or a shadow rebuild for type changes.
- **History tables** (`hist_<class>`, one row per version with `valid_from_seq/valid_to_seq` and effective dates) are generated for types marked `history: true`, and for all types in the lakehouse (§28).
- The same generated DDL targets SQLite and Postgres; promoted columns get indexes per the LinkML `indexed` annotation.

---

## 6. Semantic model, schemas and property sets

### 6.1 Single source of truth

The model is authored in **LinkML** (YAML). From it the build generates:

- Pydantic models (service layer validation)
- JSON Schema (API contracts, document-derivative validation such as `x_schema.json`, pset validation)
- SQL DDL for projections (SQLite and Postgres dialects)
- JSON-LD context + OWL/SHACL (semantic model for integration and AI use)
- OpenAPI specification fragments
- MCP tool and resource schemas
- TUI form/grid metadata (labels, help, ordering, widgets, lookups)

Every class and slot carries a URI, definition, units, and mappings to external vocabularies where available (e.g. ISO 15926 / CFIHOS reference data, IFC, CSI MasterFormat, P6 fields). APIs return JSON with an `@context` link so semantic meaning travels with the data.

### 6.2 Common record envelope

Every record type, in every module, shares:

| Field | Notes |
|---|---|
| `id` | ULID (immutable, global) |
| `key` | Human-readable number from the Numbering service (e.g. `NCR-P123-0042`) |
| `type` | Fully qualified record type |
| `scope` | Company or project |
| `title`, `description` | |
| `status` | From the record type's workflow |
| `discipline`, `area`, `unit` | Standard classification (from Standards registry) |
| `wbs_ref`, `awp_ref` | Optional typed references |
| `cost_code_ref`, `schedule_activity_ref` | Optional typed references (activity by stable P6 Activity ID) |
| `xref_model_id`, `xref_model_objects`, `xref_model_location`, `xref_viewpoint` | Optional spatial context (shown as *x-ref-model-id*, *x-ref-model-location*): model document (pinned revision or floating), IFC GlobalIds, structured location (level, space, grid, area/CWA, coordinates, bounding box), saved viewpoint. Resolved or inherited automatically where not set (§23.5) |
| `tags[]` | Free tags (non-semantic) |
| `psets{}` | Property-set values keyed by pset definition |
| `links[]` | Projection of all typed links (both directions) |
| `attachments[]` | File references (object store) |
| `external_refs[]` | References into other systems (§7.1) |
| `thread_ref` | Optional message thread, when enabled (§21.5) |
| `created_*`, `updated_*`, `version` | Derived from ledger |

### 6.3 Property sets (psets): layered, standard + custom

A **pset definition** is a named, versioned group of typed properties, applicable to one or more record types or classes. Psets are how the model stays flexible: they change often, they change at runtime, and they change at different levels of the organisation. The full schema lifecycle is in §27. This section defines the layers.

#### Layers

| # | Layer | Owner | Namespace | What it can do |
|---|---|---|---|---|
| 1 | **Core slots** | Platform (code release) | `tl:` | Class slots defined in module LinkML. Not psets; listed for completeness |
| 2 | **Company standard psets** | Operating company (schema stewards) | `co:<company>/` | Define standard properties, value lists, units, meanings, and **enforcement** |
| 3 | **Project extensions of standard psets** | Project (data manager) | `co:…/x/<project>/` | Within limits set by the company: add values, add properties in the pset's **custom section**, tighten constraints, set defaults |
| 4 | **Project custom psets** | Project | `prj:<project>/` | Entirely project-defined psets for local needs |
| 5 | **Enrichment psets** | Enrichers (§18.9) | `enrich:<app>/` | Machine-written, with provenance and confidence; read-only for humans |
| 6 | **Source psets** | Connectors/imports | `src:<system>/` (e.g. `src:ifc/`, `src:p6/`, `src:legacy-acme/`) | External properties preserved verbatim, then mapped into standard properties over time |

A pset value on a record is addressed by layer-aware paths:

```
psets.valve_data.size_in                 ← company standard property
psets.valve_data.x.fat_witness_by        ← project custom section of the same pset
psets.prj.shutdown_tie_in.window         ← project custom pset
psets.enrich.ai_classifier.valve_type    ← enrichment
psets.src.ifc.Pset_ValveTypeCommon.Size  ← source (IFC)
```

#### Company enforcement

Each company standard pset, and each property within it, carries an **enforcement level**:

| Level | Effect |
|---|---|
| `advisory` | Shown and validated; violations are warnings only |
| `required` | Violations block the write or transition where the binding says so (e.g. required before `Accepted`) |
| `locked` | As `required`, and projects cannot extend or tighten it: no added values, no relabelling, no custom section |

Further controls per pset/property:

- `value_list_policy`: `closed` (company values only), `extensible` (projects may add values, which must crosswalk to a company value or `other`), or `project_defined` (projects own the list entirely; an optional crosswalk keeps cross-project reports working).
- `custom_section`: whether projects may add properties under `x.` in this pset, and an optional maximum.
- `materialize`: promote to typed columns in current-state tables (§5.4) and the lakehouse.
- `adoption`: `mandatory` (every project gets it), `default` (on unless declined), `optional`.

**Project conformance mode** decides how company enforcement applies on a project: `strict`, `lenient` (required acts as advisory; useful during onboarding and legacy loads, time-limited), or `strict with waivers`. A **waiver** relaxes one property on one project. It is a ledgered record with a reason, an approver, and an expiry, and it shows in conformance reports.

#### What projects can and cannot do

| Projects can | Projects cannot |
|---|---|
| Add values to `extensible` value lists (with crosswalk) | Remove or rename company properties |
| Own `project_defined` value lists outright | Change a company property's type, unit dimension, or meaning |
| Add custom-section properties (`x.`) to non-locked psets | Loosen company required/range/pattern constraints |
| Tighten constraints (make optional properties required, narrow ranges) | Touch `locked` psets beyond filling values |
| Set project defaults and display labels (if allowed) | Bypass enforcement without a waiver |
| Create project custom psets and bind them to any record type | Write into enrichment or source layers |

#### Example

```yaml
# Company standard pset (schema registry package co:acme/engineering@3.2.0)
psets:
  valve_data:
    applies_to: [ed.Tag]
    class_filter: "class in (ControlValve, ManualValve)"
    enforcement: required
    adoption: mandatory
    custom_section: {allowed: true, max_properties: 10}
    properties:
      size_in:
        range: decimal
        unit: {ucum: "[in_i]"}
        required_in_states: [Design, Installed]
        materialize: true
        exact_mappings: [cfihos:CFIHOS-40000123]     # illustrative
      body_material:
        range: MaterialCode                          # Standards registry code list
        value_list_policy: extensible
      fail_action:
        range: FailAction
        value_list_policy: closed
        enforcement: locked

# Project extension (prj P123, package co:acme/x/P123@1.4.0)
extends: co:acme/engineering@3.2.0#valve_data
tighten:
  body_material: {required_in_states: [Design]}
add_values:
  MaterialCode:
    - {code: "SS316L-NACE", label: "316L NACE MR0175", crosswalk: "SS316L"}
custom:
  fat_witness_by: {range: Party, description: "Client witness for FAT"}
  tie_in_window:  {range: string, description: "Shutdown window ref"}
```

#### General rules

- **Property attributes:** key, label, description (mandatory), data type (string, int, decimal, bool, date, datetime, enum, quantity-with-UOM, reference-to-record, reference-to-standard, file slot, list-of), required/required-in-states, default, validation (range, regex, enum source), unit, help text, semantic URI, external mappings, enforcement, materialize.
- **Values** are stored as events (`Pset.ValuesSet`) recording the effective schema hash they were validated against, and projected into current-state tables (§5.4).
- **Templates:** psets drive checklist/ITR forms, engineering data sheets, derived-document schemas, and IDS specs for models.
- **Querying:** every layer is first-class in filters, saved views, reports, API queries, MCP tools, and the lakehouse (e.g. `psets.valve_data.size_in >= 2 and psets.valve_data.x.fat_witness_by = @party:client`).
- **Promotion:** a project custom property that proves useful can be promoted to the company standard. The promotion tool records an alias from the old path to the new one, so no events are rewritten (§27.5).

### 6.4 Standards registry (company "holding zone")

Engineered standards used everywhere, versioned and governed:

- Mnemonics and abbreviations (e.g. tag prefixes `FV`, `PT`, `HS`) with meanings
- Tag/document/line numbering conventions as parseable patterns (regex + segment definitions), used for validation and auto-parsing
- Code lists: disciplines, areas, document types, status codes, NDE methods, weld types, gasket types, piping classes, test media, punch categories, crafts
- Units of measure and conversions
- Each entry has an owner, effective dates, supersession links, and project adoption status
- Code lists follow the same `value_list_policy` and crosswalk rules as pset value lists (§6.3), so a project's local values always map to company values for reporting

---

## 7. Cross-referencing: a first-class operation

References are the backbone of the product. Every user can **create**, **maintain**, **surface**, and **follow** them as everyday operations: one key or click each, in every screen, and with the same operations in the API and MCP.

### 7.1 Reference model

| Kind | What it is |
|---|---|
| **Typed reference fields** | Schema-defined slots with cardinality and target type (e.g. `Weld.spool_ref → Spool`) |
| **Links** | Generic, typed relations between any two records, from a governed relation vocabulary |
| **External references** | `ExternalRef` records pointing into other systems (client DMS document, ERP PO, archived email): system, external ID, URL, label, last checked |

Typed fields and links are unified in the read model (`cur_links`), so both appear together everywhere.

**Relation vocabulary** (extensible, each with an inverse label): `references / referenced by`, `derived from / source of`, `supersedes / superseded by`, `responds to / responded by`, `raised against / has raised`, `resolves / resolved by`, `belongs to / contains`, `requires / required by`, `blocks / blocked by`, `verifies / verified by`, `dispatched from / dispatched`, `attached to`, `same as`. Each type pair has a default relation (weld → NCR defaults to `raised against`), so most links need no choice at all.

**A link has its own lifecycle:**

| Field | Notes |
|---|---|
| `from`, `to` | Record or external reference |
| `relation` | From the vocabulary |
| `pin` | A specific revision/version, or floating to current |
| `note` | Optional |
| `source` | `manual`, `key_detected`, `tray`, `bulk`, `model_selection`, `thread_dispatch`, `rule`, `enricher`, `import`, `mapping` |
| `confidence` | For suggested links |
| `status` | `suggested`, `active`, `stale`, `broken`, `retracted` |
| `verified_by/at` | Optional human or rule verification |

Events: `Link.Suggested`, `Link.Added`, `Link.Accepted/Declined`, `Link.Repinned`, `Link.Verified`, `Link.Flagged`, `Link.Retracted`. Links are never deleted.

**Expected links** are declared in LinkML (`tl:expects_link`), e.g. a weld needs a WPS by `Welded`, an IWP needs a permit-to-work by `Issued`. Missing expected links show on the record and in data health reports, and can act as workflow guards.

### 7.2 Create

| Method | How |
|---|---|
| Link picker (`l`) | Search across types, filter, multi-select, preview, choose relation and pin, or create a new record and link it in place (sketch §10.6) |
| Key detection | Any recognisable key typed in a field, post, thread message, or correspondence body, or found by OCR in a document, becomes a suggestion chip; `Tab` accepts it inline |
| **Reference tray** (`R`) | A clipboard for references. Add records from anywhere (grid, search, model, feed, thread) across screens and sessions, then link the checked ones to the current record with one action (sketch §10.6) |
| Bulk | Grid selection → link to a target; paste a list of keys; import a CSV of pairs |
| Drag and drop | Drag a row or chip onto a record, panel, or tray (mouse) |
| From the model | Selected objects → link to a record (or the reverse) |
| From search results | "Link all results" with a relation |
| Create-and-link | New records start linked to their origin (e.g. `d` raises a deficiency against the selection) |
| Automatic | Rules, enrichers (as suggestions), import mappings, thread dispatch commands |
| API / MCP | `link_records`, `propose_links`, `add_external_ref` |

Creating a link needs read access on the target; cross-project links follow §3.

### 7.3 Maintain

- **Revision pins:** when a new revision is issued, pinned links go `stale` and owners are notified. **Re-pin** (single or bulk) shows what changed between revisions for that record before confirming.
- **Automatic health checks:**
  - target voided or superseded → `stale`;
  - external reference unreachable → `broken` (checked periodically);
  - activity missing from the latest XER snapshot → `stale` (orphaned);
  - tag renamed or split → follows `supersedes` and proposes re-targeting.
- **Suggestion queue:** suggested links (key detection, enrichers, mappings) wait for accept or decline. Declines are remembered, so the same suggestion does not come back.
- **Verification:** people or rules can mark links verified (e.g. QA confirms the NCR covers exactly these welds).
- **Retract, never delete**, with a reason; history stays visible.
- **Merge:** when duplicate records are merged (e.g. after an offline sync, §22.4), their links move to the survivor and a `same as` link records the merge.
- **Link health report** and data-health dashboard: stale pins, broken external refs, missing expected links, unreviewed suggestions.

### 7.4 Surface

- **Links tab:** inbound and outbound links grouped by relation and type with counts, plus expected-but-missing, suggestions, and external references.
- **Chips everywhere:** any key in any text shows as a chip with status colour; hovering (or `K`) shows a preview card without leaving the screen.
- **Grid columns:** link counts, linked keys, and linked status (e.g. "open NCRs", "stale pins") from current-state tables (§5.4), so they sort and filter.
- **Record header badges:** e.g. "3 open NCRs · 1 stale pin · 2 suggestions".
- **Context panel:** the top links of whichever row has focus.
- **Feeds:** link events appear as cards; a record's feed includes its linked records (one hop).
- **Model:** links drive spatial context (§7.6, §23.5).
- **Notifications:** watchers can be told when something links to their record (setting).

### 7.5 Follow

- `Enter` on a chip or link row opens the target; `Shift+Enter` opens it in a split; `Ctrl+Enter` in a new tab.
- **Back/forward history** (`Alt+←` / `Alt+→`) works like a browser across every followed reference, with a breadcrumb trail of the path taken.
- **Open related** (`Ctrl+O`): a fuzzy picker over everything linked to the current record.
- **Trace view** (`t`): n-hop tree or graph, e.g. deficiency → inspection → weld → spool → line → test package → subsystem → system.
- **Query operators** in the shared query language:
  - `linked:NCR`, `linked(raised_against).status:open`,
  - `path(weld>spool>iso).rev:C`,
  - `count(linked:NCR)>0`, `missing(link:permit)`.
- **API / MCP:** `GET /records/{id}/links?relation=…&depth=…`, `/trace`; MCP `get_links`, `trace`, `follow`.
- Deep links (§19.1) resolve from anywhere: email, chat, printed QR codes.

### 7.6 Visual context through links

A record without its own model reference inherits one along declared link paths (e.g. weld → spool → iso → line), so almost any record can be shown in the model (§23.5).

Cross-reference fields per record type are listed in each module spec (column "Key cross-references").

---

## 8. Cross-cutting concerns

| Concern | Approach |
|---|---|
| **Identity & auth** | OIDC/SAML SSO in prod; local accounts in dev. Service accounts and agent identities with on-behalf-of user context |
| **Authorisation** | RBAC (roles per company/project) + ABAC filters (area, discipline, subcontractor, record type, status). Same rules applied in TUI, API, and MCP |
| **Workflow engine** | Declarative state machines per record type (states, transitions, guards, required psets, required links, approvers, signatures, notifications). Versioned; company defaults with project overrides |
| **Electronic signatures** | Signature events with intent, signer, timestamp, and record hash; reauthentication on sign |
| **Numbering service** | Pattern-driven per project/type (e.g. `{project}-{type}-{discipline}-{seq:4}`), gap-free option, reserved ranges for offline/bulk use |
| **Threads & mentions** | Optional per-record threads with dispatch (§21.5); `@user` and `#key` everywhere; all ledgered |
| **Settings** | Layered, typed, ledgered about:config-style settings (§30) |
| **Offline** | Replica sync and merge (§22) |
| **Attachments** | Any record; content-addressed storage; previews where possible |
| **Notifications** | In-app inbox, email digest, webhook; subscription by record, saved query, or role |
| **Search** | SQLite FTS5 (dev) / Postgres full-text + trigram (prod); later optional external search engine. Includes psets and extracted document text |
| **Import/export** | CSV/XLSX with schema-validated templates generated from the model; dry-run with row-level validation report; imports are ledgered as one correlated batch |
| **Units** | Quantity values store magnitude + UOM; conversions via registry |
| **Time** | UTC storage; project time zone for display; `effective_at` for business dates |
| **Audit** | Native — the ledger is the audit trail. Record "History" tab shows event timeline with diffs |
| **Observability** | Structured logs, metrics, traces (OpenTelemetry) |
| **Data quality** | Validation rules per type; "data health" dashboards (missing required psets, orphans, stale pins, broken patterns) |
| **Localisation** | Strings externalised; English first |

---

## 9. Functional specifications by module

Each module lists principal record types, key fields (beyond the common envelope), key cross-references, workflows, and notable behaviour.

### M1 — Document Control

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `Document` | Doc number (pattern-validated), title, type, discipline, originator, confidentiality, current revision, status | Tags, lines, systems, WBS/CWP/EWP/IWP, correspondence, RFIs/NCRs, superseding document |
| `Revision` | Rev code (per scheme: A/B/C, 0/1/2, P1/C1), revision date, purpose/issue reason, status (IFR, IFC, AFC, As-Built, Void), reviewer comments | Parent document, previous revision, transmittal, review comments |
| `Rendition` (file) | File object key (hash), filename, MIME, size, page count, native vs PDF vs markup | Revision |
| `DerivedDocument` | Target schema (`x_schema.json` + version), method (manual/automated/hybrid), validation status, validation report | `derived_from` source revision/rendition, processing job, consuming records |
| `Transmittal` | Number, direction, recipients, purpose, due date, response code | Revisions included, correspondence |
| `ReviewCycle` | Reviewers, due dates, outcome codes | Revision, comments |
| `DocumentSchema` | Schema name, version, JSON Schema, sample, mapping notes | Document types it applies to, pset definitions |

**Revision control concepts**

- Document → Revisions → Renditions (one revision can have native, PDF, markup, signed copy).
- Revision schemes are configurable per project and document type.
- Only one "current" revision per status class; superseded revisions retained and visibly superseded.
- Links can pin a revision or float.

**Schema-validated derivation pipeline**

```
Receive (upload / email / transmittal / connector)
   → Register (metadata, number parse, classify)
   → [optional] Extract job (automated: PDF table extraction / OCR / AI-assisted;
                              manual: user uploads CSV/XLSX)
   → Validate derived output against DocumentSchema (JSON Schema)
        ├── pass  → Derived document "Valid"; optionally publish rows to target records
        └── fail  → row/field-level report; status "Needs correction"; reprocess or edit
   → Publish (e.g. schedule rows → schedule mirror; tag list → Engineering Data; MTO → Materials)
```

- Originating and derived files are both stored and linked (`derived_from` / `source of`), with method, actor, tool version, and schema version recorded.
- Re-processing a new source revision creates a new derived revision and a diff against the prior derived data.
- Publishing derived data into other modules is an explicit, ledgered import with a correlation ID back to the derived document, so every downstream value can be traced to a page in a source PDF.
- Processing jobs are pluggable (extractor plugins) and runnable from TUI, API, or MCP (agents can perform extraction, but publication requires a human approval step by default).

**Workflows:** Document: Draft → Registered → In Review → Issued → Superseded/Void. Derived: Pending → Processing → Invalid/Valid → Published.

### M2 — Engineering Data

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `Tag` (project-unique identifier) | Tag number (pattern-validated, parsed into segments), class (instrument, valve, pump, line, equipment, cable, …), service description, status (planned, design, installed, commissioned, deleted) | Documents (datasheets, P&IDs, isos, loop drawings), line, system/subsystem, area, WBS/CWP/IWP, item master, physical equipment serial, test packages, ITRs |
| `TagClass` | Class definition, required psets, applicable ITR templates | Standards registry |
| `Standard` (registry entries) | See §6.4 | Projects adopting |

**Behaviour**

- Engineering data is "mostly psets against a project-unique identifier": tag class determines mandatory psets (e.g. control valve: size, rating, body material, actuator type, fail action).
- Bulk import from derived documents (instrument index, line list, equipment list) with diff preview: new / changed / removed tags, property changes per pset.
- Property values carry source provenance (which document revision supplied them).
- Tag rename/split/merge is an explicit event with `supersedes` links.

### M3 — Field work packaging (GC scope: WBS and AWP / workface planning)

**Scope from the GC's side.** The general contractor builds. Engineering work packages (EWPs) and procurement work packages (PWPs) usually come from the owner, EPC, or engineer. Throughline therefore focuses on **field work packaging**:

- breaking the GC's contract scope into construction work packages (CWPs) and installation work packages (IWPs),
- removing constraints,
- releasing constraint-free IWPs to foremen,
- tracking progress and closing out.

It follows the **COAA Workface Planning model** (COAA's AWP/WFP practice material; CII's AWP work builds on the same model). EWPs, PWPs, and design deliverables are **referenced inputs and constraint sources**, not authored here.

```
GC WBS (contract & cost control)            AWP (field execution)
 Contract scope                              Path of Construction (sequence of CWAs)
  └ WBS nodes ── map to ── cost codes          └ CWA  Construction Work Area
        │                                          └ CWP  Construction Work Package (discipline scope)
        └─── many-to-many with allocation % ───────┤  inputs (referenced): EWPs / IFC documents,
                                                   │                      PWPs / materials, vendor data
                                                   └ IWP  Installation Work Package
                                                         (one foreman's crew, short window)
                                                          └ work steps → installed quantities
                                                            (welds, joints, steel, cable, …)
```

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `WBSNode` | GC contract WBS, schedule-of-values line, budget hours/quantities/$ | Cost codes, CWPs (with allocation %), contract |
| `PathOfConstruction` | Ordered CWA sequence, version, rationale | CWAs, XER activities |
| `CWA` | Area boundary (plot plan / model bounding box), sequence, area manager | Path of construction, model slices, systems |
| `CWP` | Discipline, scope, budget hours/quantities from the estimate, planned window, self-perform or subcontract, status (Planned → In development → Released for IWP development → Executing → Complete → Closed) | CWA, WBS nodes, referenced EWPs/PWPs, IWPs, cost codes, XER activities, subcontractor party |
| `EWPRef`, `PWPRef` | Mirror of the owner/EPC package: ID, status, forecast/actual dates | Documents (M1), materials (M4), constraints they cause |
| `IWP` | Scope and work steps, discipline, foreman and crew size, planned window, estimated hours (from norms and rules of credit), installed quantities by UOM, status | CWP, documents (pinned), tags, welds, joints, materials (reservations), scaffold, permits, labour requisitions, ITP lines, cost codes, XER activity, model slice, constraints |
| `Constraint` | Type, need-by date (derived from IWP start minus lead time), owner, status, source (manual, rule, feed `#hold`, thread `/hold`) | Constrained IWP/CWP; resolving record (receipt, document revision, RFI answer, scaffold WO, permit) |
| `LookAhead` | 3–6 week window built from the current XER snapshot plus IWP readiness | XER snapshot, IWPs, constraints |
| `WeeklyPlan` | Foreman commitments for the week, completed vs committed (PPC), reasons for misses | IWPs, foremen, crews |
| `RulesOfCredit` | Company standard per commodity (e.g. weld: fit-up 30% / weld 60% / NDE accepted 10%), held in the schema registry | Commodity record types |
| `IWPCloseout` | Actual hours (from external timesheets), quantities, redlines, remaining punch, field feedback | IWP, files, deficiencies |

**IWP contents.** COAA's minimum is scope, drawings, materials, safety, and quality, kept simple because the tradesperson is the primary user. Throughline holds each as linked records rather than copied text:

| Section | Held as |
|---|---|
| Scope and work steps | IWP fields + linked commodity records (welds, joints, tags, steel members…) |
| Drawings | Pinned document revisions (stale-pin alerts, §7.3) |
| Materials | MTO lines + reservations (M4) |
| Safety | Hazard assessment, permits, required training (linked records, file slots) |
| Quality | ITP lines, checklists, hold/witness points (M5) |
| Access and equipment | Scaffold requests/tags, crane lifts, tools (M9, M4) |
| Estimate | Hours and quantities by rules of credit |
| Model | IWP model slice (§23.4) |

**Roles** (COAA model): construction manager, area/general superintendent, **workface planner** (develops IWPs; sits between the superintendent and the foremen), general foreman, foreman (crew of about 10 in COAA's examples), materials coordinator, scaffold coordinator, field engineer, QC, safety, and an AWP champion / integration coordinator.

**Lifecycle**

```
Draft → In development → Constraint check → Ready (constraint-free, signed off)
      → Issued (to foreman) → In progress → Field complete → Closed (returned & closed out)
         side states: On hold (new constraint) · Split · Cancelled
```

**Rules and behaviour**

- **Release:** only constraint-free IWPs move to Ready, and IWPs are **signed off before release to the field** (COAA). Sign-off roles are a setting (default: workface planner + superintendent).
- **Lead time and backlog:** COAA material has IWPs complete about **4 weeks before work starts**. `awp.iwp.ready_lead_weeks` (default 4) drives constraint need-by dates; `awp.backlog.target_weeks` sets the target backlog of Ready IWPs per foreman. Dashboards show backlog weeks per foreman and discipline.
- **Sizing:** an IWP is sized for one foreman's crew over a short window. COAA examples range from roughly 60 to 850 hours. `awp.iwp.size_hours` sets warning bounds, and a split tool divides oversize IWPs by work steps or commodities.
- **Readiness check** (live, from linked records): documents current, RFIs answered, materials reserved, scaffold erected and tagged, permits planned, inspections planned, labour requested, predecessor areas handed over, model slice available (sketch §10.6).
- **Constraint removal:** every constraint has an owner and a need-by date; aging and escalation follow settings. A weekly constraint review screen groups constraints by owner and type.
- **Weekly workface planning cycle**, each step with its own screen:
  1. load the new XER snapshot and look-ahead,
  2. review constraints,
  3. release Ready IWPs,
  4. record foreman commitments,
  5. record progress and PPC,
  6. close out IWPs with field feedback.
- **Progress** is earned from linked records' states through rules of credit, with manual entry only for commodities without detailed records. It rolls up IWP → CWP → WBS/cost code, can be exported to the cost system (quantities), and later to P6.
- **Subcontracted scope:** CWPs/IWPs can be assigned to a subcontractor party. The subcontractor works through external-party access or guest links (§18.11); interface constraints are tracked; progress arrives through the portal or an inbound webhook.
- **IWP pack:** a printable/PDF pack generated from a template: cover sheet, scope and steps, drawing list (pinned revisions + QR to current), MTO, safety, ITP/checklists, permits, scaffold tags, model slice snapshot, sign-off sheet.
- **KPIs:**
  - backlog weeks per foreman,
  - % of IWPs released constraint-free,
  - constraints by type and age,
  - IWP schedule compliance and PPC,
  - earned vs burned hours per IWP,
  - IWPs issued with stale pins (target zero).

### M4 — Materials Management

**Levels:** Company → Region/Warehouse → Project → Laydown/Yard → Toolcrib → Crew/Gang box (hierarchical `InventoryLocation`).

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `ItemMaster` (item library, company) | Abstract item: commodity code, class, short/long description (generated from psets), base UOM, category (consumable / permanent / equipment / tool / rental) | Standards (classes, UOMs), catalog items, specs |
| `CatalogItem` | Vendor/manufacturer part number, pack size, UOM conversion | ItemMaster, vendors |
| `ProjectItem` | Project-specific identity of a permanent material (ident code, piping class item) | ItemMaster, MTO lines, spools, tags |
| `MTO` / `MTOLine` | Required qty, UOM, source document revision | Derived document, ProjectItem, CWP/IWP, line/iso |
| `POLineRef` | External PO number/line, qty, promised date | ProjectItem, receipts |
| `Receipt` | Qty, location, condition, heat number, MTR/cert | PO line, inspection (receiving), documents (MTRs) |
| `StockLot` / `SerializedItem` | Qty on hand per location, heat/batch, serial | ItemMaster/ProjectItem, location |
| `InventoryTransaction` | Receive, issue, transfer, return, adjust, scrap, reserve, unreserve | Lot/serial, requisition, IWP, cost code, person/crew |
| `Equipment` (asset) | Asset number, serial, make/model, owner (company/rental), current location/project, calibration-required flag | ItemMaster, calibration records, work orders, inspections performed with it |

**Behaviour**

- Inventory is itself ledgered: stock = projection of transactions.
- Consumables issued to crews post to cost codes; permanent materials trace from receipt → heat number → spool/weld → system.
- Reservations against IWPs feed AWP readiness.
- Toolcrib mode: fast issue/return screen (scan or type asset/item, person, qty) with keyboard-only flow.
- Company-level view aggregates across projects (equipment utilisation, surplus available for transfer).

### M5 — Quality Control and Quality Management

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `ITP` / `ITPLine` | Activity, characteristic, acceptance criteria, reference spec, inspection points (H/W/R/S per party) | Documents, record types it governs, checklist templates |
| `ChecklistTemplate` | Questions as pset definition; versioned | ITP line, tag classes |
| `Inspection` | Type, scheduled/actual date, inspector(s), result (Accept/Reject/Conditional), checklist responses (pset values), witness parties | Inspected record(s) (tag, weld, joint, spool, IWP, receipt…), ITP line, equipment/instruments used, deficiencies raised, documents |
| `Deficiency` / `Punch` | Category, priority (A/B/C), description, responsible party, due date, status, photos | Raised against (any record), inspection, system/subsystem, NCR (if escalated), work order (to fix), clearing inspection |
| `Instrument` (calibrated device) | ID, type, range, accuracy, calibration interval | Equipment |
| `CalibrationRecord` | Date, due date, result, certificate, lab | Instrument, documents (certificate) |
| `RFI` | Defined in M10 as a Technical-domain correspondence item (question, required-by, response, impact flags) | Documents (pinned revs), tags, IWPs, constraints, responding document revision, Commercial items raised from it |
| `NCR` | Nonconformance description, disposition (use-as-is / repair / rework / reject), root cause, approvals | Affected records, inspections, deficiencies, CARs, cost codes |
| `CAR` | Corrective action, root cause method, actions, effectiveness check | NCRs/QSRs/audits it addresses |
| `QSR` (quality surveillance report) | Observations, rating, area | Subcontractor, findings → deficiencies/NCR/CAR |
| `Audit` (optional v1.x) | Scope, findings | CARs |

**Behaviour**

- NCR/CAR/QSR share a common **Issue engine** (numbering, assignment, due dates, response cycles, escalation, closure) with type-specific psets and workflows.
- Formal exchanges about quality issues with clients and subcontractors (NCR notifications, CAR requests) are Quality-domain correspondence in M10, linked to the internal NCR/CAR/QSR records. RFIs live in M10's Technical domain and remain visible from the Quality module.
- **Calibration impact analysis:** when an instrument fails calibration, list every inspection/test performed with it since its last good calibration, with one-click bulk link to an NCR.
- Instruments past due cannot be selected on new inspections/tests (configurable hard/soft block).
- Deficiencies can be raised from any record in two keystrokes and are always linked to their origin.

### M6 — Piping (Welds and Boltup)

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `Line` | Line number (pattern), piping class, size, service, design/test pressure & temperature, insulation, paint, PWHT and NDE requirements | Tag (line is often a tag), P&IDs, isos, system/subsystem, test package |
| `Isometric` | Iso number, sheet, revision | Line, document revision (pinned), spools, welds |
| `Spool` | Spool number, shop/field, fabrication status, location | Iso, line, material lots/heat numbers, welds, shipping/receipt |
| `Weld` | Weld number, type (BW, SW, FW…), size, schedule/thickness, material group, shop/field, WPS, welder(s), fit-up date, weld date, visual result, PWHT required/done, hardness, status | Iso (revision), spool, line, WPS document, welder qualification, heat numbers of both components, NDE requests/results, repairs (repair weld links original), IWP, test package |
| `WelderQualification` | Welder, process, positions, range, expiry, continuity log | People, WPQ document |
| `NDERequest` / `NDEResult` | Method (RT, UT, PT, MT, PMI, hardness), % selection, lot, result, report number, reject reason | Welds, inspection, NDE report document, NCR |
| `BoltedJoint` | Joint number, flange size/rating/face, gasket type, bolt spec, lubricant, target torque/tension, method, sequence, status (Open / Assembled / Torqued / Verified / Broken for test / Reinstated) | Line, iso, tags (equipment nozzle, valve), procedure document, tools used (calibrated), test package, IWP |
| `BoltupRecord` | Date, technician, tool, measured values, passes, verification | BoltedJoint, tool calibration record, inspection |

**Behaviour**

- Weld map import from derived iso data; weld numbering validation.
- NDE selection rules per piping class/percentage, with lot management and penalty (progressive) selection on rejects.
- Welder continuity and qualification checks at weld record time.
- Joint history supports break/remake cycles (e.g. broken for testing, reinstated after), each ledgered with tool calibration links.
- Progress quantities (inch-dia, welds complete, joints torqued) roll up to IWP/CWP and to cost codes.

### M7 — Pressure Testing

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `TestPackage` | Number, test medium, test pressure, hold time, limits (boundary description), status | Lines, isos (pinned revs), welds, joints, tags (inline valves, instruments to remove/isolate), subsystem, test limit drawings, punch, IWP |
| `PreTestChecklist` | Walkdown items, documentation complete, NDE complete, PWHT complete, punch A cleared | Test package, deficiencies, inspections |
| `PressureTest` | Date, actual pressure, duration, ambient/medium temp, gauges/recorders used, chart, result, witnesses | Test package, instruments (calibration validated), documents (chart, certificate), deficiencies |
| `Reinstatement` | Joints remade, blinds removed, items reinstalled | Bolted joints, boltup records, inspections |

**Behaviour**

- Package readiness computed live: all welds accepted with required NDE, all joints in required state, punch A closed, pinned documents current, gauges in calibration.
- Test certificate generation from template; signed via e-signature.

### M8 — Systems Completion and Turnover

**Record types**

| Record | Key fields | Key cross-references |
|---|---|---|
| `System` / `Subsystem` | Number, description, priority, planned RFC/RFSU dates, status | Tags, lines, test packages, documents (system boundary drawings), P6 activities |
| `ITRTemplate` | A (construction/MC), B (pre-comm), C (commissioning) forms as psets | Tag classes |
| `ITR` (check sheet instance) | Template, status, completed by/date, verified by | Tag, subsystem, inspection, instruments used |
| `Punch` | (shared with Deficiency) Category A/B/C | Subsystem, tag, ITR |
| `Certificate` | Type (MC, RFC, RFSU, handover), status, signatories | Subsystem/system, required ITRs/punch status snapshot |
| `HandoverDossier` | Index, contents, completeness | Documents, ITRs, test packages, certificates |

**Behaviour**

- Tags are assigned to subsystems; ITRs are auto-generated per tag class × phase.
- Completion dashboards: ITRs by status, punch by category, test packages, certificates; burn-down by subsystem.
- Certificate issuance captures a snapshot (hash) of the supporting record set at signing.
- Dossier builder compiles documents and generated reports into an indexed package stored in the object store (and exportable).

### M9 — Requisitions and Work Orders

A **generic Request → Work Order engine** with specialisations sharing numbering, approval, scheduling, assignment, status, and closeout.

| Record | Key fields | Key cross-references |
|---|---|---|
| `Requisition` (generic) | Requester, need-by date, location/area, description, priority, approval chain | IWP, cost code, P6 activity, tags, documents |
| `WorkOrder` (generic) | Assigned crew/sub, planned/actual start/finish, hours, status | Requisition, IWP, cost code, materials issued, inspections |
| **Scaffold** `ScaffoldRequest` | Purpose, location (elevation/gridline), dimensions, load class, required-by, duration | IWP(s), tags/equipment being accessed, permits |
| **Scaffold** `Scaffold` (asset) | Scaffold number, type, status (Requested → Designed → Erecting → Inspected/Tagged Green → In Use → Modify → Dismantle → Removed), current tag colour, inspection due | ScaffoldRequest(s), work orders (erect/modify/dismantle), scaffold inspections, IWPs using it, cost codes, material quantities |
| **Labor** `LaborRequisition` | Craft/trade, classification, headcount, start/end dates, shift, location, requirements (certs, tickets) | CWP/IWP, cost code, P6 activity, subcontractor/union hall |
| **Material** `MaterialRequisition` | Lines (item, qty, UOM), from-location | IWP, cost code, inventory transactions |
| **General** `GeneralRequisition` | Free-form with type-specific psets (e.g. crane lift, cleaning, survey) | Any |

**Behaviour:** Scaffold inspection intervals drive due lists; scaffolds tied to IWPs feed readiness; dismantle requests check that no open IWP still depends on the scaffold.

### M10 — Correspondence (core + domain layer)

Correspondence has two layers:

- A shared **correspondence core** handles the mechanics every formal exchange has: parties, threading, register, issue/receipt, attachments, transmittal, and the response clock.
- A **domain layer** sits on top. Each domain (RFI, Quality, Commercial, Legal, …) adds its own subtypes, workflow, numbering, required data, clocks, confidentiality, and routing.

One register shows everything. Each domain still behaves the way its discipline needs.

```
Correspondence core  (envelope, parties, thread, register, files, clocks, issue/receive)
   ├── Domain: Technical / RFI        → RFI, TQ, deviation/concession request
   ├── Domain: Quality                 → NCR notification, CAR request, quality notice, audit letter
   ├── Domain: Commercial              → change/variation notice, early warning, instruction, claim, payment, back-charge
   ├── Domain: Legal / Contractual     → formal notice, dispute, termination/suspension, privileged advice
   ├── Domain: HSE                     → incident notification, stop-work, safety observation letter
   ├── Domain: Interface / Coordination→ interface query/agreement, access & handover requests
   ├── Domain: Document control        → transmittals and review returns (links M1)
   └── Domain: General / Admin         → everything else
```

#### Core records

| Record | Key fields | Key cross-references |
|---|---|---|
| `Correspondence` (core item) | Number, direction (in/out/internal), medium (letter, email, portal, meeting minute), from/to/cc parties and people, sent/received dates, subject, body/summary, confidentiality class, domain, subtype, status, response required/by | Thread (responds-to / superseded-by), domain item, documents (pinned revisions), attachments, affected records (any), cost codes, IWPs, viewpoints, feed posts |
| `CorrespondenceThread` | Subject, domain, parties, open/closed | All items in the thread, the governing domain item |
| `ResponseClock` | Start trigger, duration, calendar (working/calendar days, project holidays), warning thresholds, stop/restart rules, contractual basis, state (Running/Paused/Met/Expired) | Correspondence item, contract clause, owner |
| `ContractClause` | Contract, clause number, title, time bar, notice requirements, required recipients and method | Contract document (M1), domains/subtypes that cite it |
| `Party` / `ContactRole` | Organisation, role on project (client, engineer, subcontractor…), authorised representatives per domain | People, contracts |

Core behaviour:

- **One register, many views.** The master correspondence register covers all domains. Each domain has its own register, filters, and dashboards. Confidentiality rules apply to every view, including the master.
- **Ingest:**
  - email (per-project and per-domain mailboxes or forward-to addresses),
  - portal and inbound webhooks (client systems, §18.5),
  - upload.

  The triage step proposes the domain, subtype, referenced records (by detected keys), and clocks. A human confirms, or an enricher does so in `auto` mode where permitted.
- **Issue:**
  - generated from domain templates (letterhead, references, required clauses),
  - approval per domain workflow, then e-signature, then send (email/portal/transmittal).
  - The issued PDF and sent email are stored as immutable renditions, and send/delivery receipts are recorded.
- **Re-classification** between domains is allowed before issue. After that, a misfiled item gets a linked item in the correct domain, so the history stays intact.
- **Threading:** replies, follow-ups, and superseding letters thread automatically from email headers, references in the subject/body, and domain keys.

#### Domain definition (what each domain configures)

Each domain is a LinkML `CorrespondenceDomain` definition (company default, project override) plus a per-domain record class that extends the core item.

| Aspect | What a domain defines |
|---|---|
| Subtypes | e.g. Commercial: Early Warning, Change Notice, Instruction, Claim, Payment Application, Back-charge |
| Workflow | Its own state machine (versioned, §8): states, transitions, guards, approvers, signature rules |
| Numbering | Its own pattern (e.g. `{project}-CN-{seq:4}`, `{project}-RFI-{disc}-{seq:4}`) |
| Required data | Domain psets and required links per state (e.g. a claim needs affected cost codes and schedule activities) |
| Response clocks | Default clocks per subtype, tied to `ContractClause` time bars |
| Routing | Who receives, reviews, and approves: roles, parties, authorised representatives |
| Confidentiality | Default class and who can see it. Legal is restricted, privileged items are role-gated, commercial is limited to commercial roles + PM |
| Feed policy | Full cards, minimal cards ("A commercial notice was issued"), or none (legal) |
| Integration policy | Which webhook payload modes are allowed (legal: thin only), which external parties may respond via portal/guest links |
| Templates | Outgoing letter/form templates, response forms |
| Reports | Domain registers and KPIs |

#### Initial domains

| Domain | Subtypes | Workflow (summary) | Domain-specific data & links | Notes |
|---|---|---|---|---|
| **Technical / RFI** | RFI, Technical Query (TQ), Deviation/Concession request | Draft → Internal review → Issued → Awaiting response → Answered → (Accepted / Rejected → re-issue) → Closed | Question, proposed solution, discipline, required-by, cost/schedule impact flags, answer, answering document revision; links to documents (pinned), tags, IWPs, viewpoints, constraints | The RFI record is a Technical-domain correspondence item. It feeds AWP constraints (IWP blocked until answered). If the answer flags cost or schedule impact, a rule proposes a linked Commercial item |
| **Quality** | NCR notification to client, CAR request to subcontractor, quality notice, audit notification/report letter, concession acceptance | Draft → QA review → Issued → Response due → Responded → Verified → Closed | Links to the M5 NCR/CAR/QSR records (the quality record holds the technical substance, the correspondence holds the formal exchange), inspections, affected records | Keeps the formal exchange with client/subs separate from the internal Issue engine, while they stay linked |
| **Commercial** | Early warning, change/variation notice, site instruction (received), quotation/proposal, claim notice, detailed claim, payment application/certificate, back-charge | Draft → Commercial review → PM approval → Issued → Awaiting assessment → Assessed (Agreed / Disputed / Partially agreed) → Closed (or escalated to Legal) | Contract clause, estimated value ($, hours, qty by cost code), schedule impact (P6 activities, days), entitlement basis, assessed value; links to RFIs, instructions, cost codes, activities, photos, daily records | Time bars are hard clocks with escalating warnings. The register exports to the cost system as pending/approved changes (M11). Forecast impacts are visible to the future cost module |
| **Legal / Contractual** | Formal notice under contract, notice of dispute, suspension/termination notices, legal advice (privileged), without-prejudice correspondence | Draft → Legal review → Authorised signatory → Issued (method per clause, proof of delivery) → Response period → Closed / Escalated | Clause, method of service, proof of delivery, privilege marker, without-prejudice marker; links to commercial items and evidence records | Restricted by default. Privileged items are visible only to named legal roles, excluded from feeds, exports, AI retrieval, and client handover bundles. Thin webhooks only |
| **HSE** | Incident notification, stop-work notice, safety observation letter, regulator correspondence | Issued → Acknowledged → Actions → Closed | Incident record, location, people (personal data protected), corrective actions | Fast path: issue first, review after. Regulatory clocks |
| **Interface / Coordination** | Interface query, interface agreement, access request, area handover | Raised → Responded → Agreed → Closed | Interface points, areas, systems, CWAs, other contractors | Links to AWP constraints and systems completion |
| **Document control** | Transmittal, review return (codes), document submittal | Per M1 transmittal workflow | Revisions, review codes | The M1 `Transmittal` is a Document-control domain item, so all formal exchanges sit in one register |
| **General / Admin** | Letter, memo, minutes, notification | Draft → Issued → (Response) → Closed | — | Default for anything unclassified |

New domains (e.g. Environmental, Permits & Regulatory, Logistics) can be added per company through configuration: domain definition + workflow + numbering + templates. No code is needed unless the domain has unusual logic, in which case it ships as a small module plugin (§13).

#### LinkML sketch

```yaml
classes:
  Correspondence:
    is_a: Record
    slots: [direction, medium, from_party, to_parties, cc_parties, sent_at, received_at,
            subject, body, confidentiality, domain, subtype, thread, responds_to,
            response_required, response_due, clocks, affected_records]
  CorrespondenceDomain:
    slots: [name, subtypes, workflow_ref, numbering_pattern, required_psets,
            default_clocks, routing, confidentiality_default, feed_policy,
            integration_policy, templates]
  ResponseClock:
    slots: [start_event, duration, calendar, warnings, stop_rules, basis_clause, state]
  RFI:
    is_a: Correspondence
    slot_usage: {domain: {equals_string: technical}}
    slots: [question, proposed_solution, required_by, cost_impact, schedule_impact,
            answer, answering_revision]
  CommercialNotice:
    is_a: Correspondence
    slot_usage: {domain: {equals_string: commercial}}
    slots: [contract_clause, estimated_value, cost_code_impacts, schedule_impacts,
            entitlement_basis, assessed_value, assessment_status]
  LegalNotice:
    is_a: Correspondence
    slot_usage:
      domain: {equals_string: legal}
      confidentiality: {minimum_value: restricted}
    slots: [contract_clause, service_method, proof_of_delivery, privileged, without_prejudice]
```

#### Cross-domain behaviour

- **Escalation paths** are explicit, linked transitions:
  - RFI → Commercial (impact),
  - Quality → Commercial (back-charge),
  - Commercial → Legal (dispute),
  - HSE → Quality/Commercial.

  Each creates a new item in the target domain, linked `derived from`, with its own workflow and clocks.
- **Clock dashboard:** every running clock across domains, by time remaining, with time-bar items always at the top for those with access.
- **Evidence trail:** for any Commercial or Legal item, one view assembles the full linked chain: correspondence, RFIs, instructions, photos, daily records, schedule activities, and cost codes, all as of the relevant dates (time-travel reads).
- **Feed and webhooks** follow each domain's policy: an RFI answered posts a full card, a commercial notice a minimal card, a legal notice nothing.

### M11 — Cost and Schedule Links

**Cost**

| Record | Key fields |
|---|---|
| `CostCode` (mirror) | Code, description, hierarchy, UOM, and a measure matrix: {hours, quantity, $} × {budget, actual, earned, forecast-to-complete, estimate-at-completion} with as-of date |
| `CostSnapshot` | Imported period values (ledgered imports per period) |

- Source of truth stays in the external cost system; the suite stores mirrored, time-stamped snapshots.
- Any record can carry `cost_code_ref`; quantities and hours from execution records (welds, joints, IWPs, work orders) can be summarised by cost code for comparison and optionally exported back as progress/quantities.

**Schedule (P6 standard): XER snapshots first**

v1 integrates with P6 **only through XER file uploads**. Each upload is an immutable snapshot. P6 XML and the P6 API are later connectors that produce the same snapshot structure.

| Record | Key fields | Key cross-references |
|---|---|---|
| `Schedule` | Schedule name, type (baseline, current/update, look-ahead, what-if), owner, P6 project ID(s), current snapshot pointer | Project, contract, CWAs |
| `ScheduleSnapshot` | Data date, P6 export version, source XER (M1 document revision + file hash), import status, validation report, counts | Schedule, previous snapshot, baseline it compares against |
| `ScheduleActivity` (per snapshot) | Activity ID (stable key across snapshots), name, WBS path, type, status, original/remaining/actual durations, early/late/actual/baseline dates, total and free float, % complete (all types), calendar, activity codes, UDFs, resource summary | Snapshot; linked CWPs/IWPs/systems/correspondence through the stable Activity ID |
| `ScheduleWBS`, `ScheduleRelationship`, `ScheduleCalendar`, `ActivityCode`, `UDF` | As in XER (`PROJWBS`, `TASKPRED`, `CALENDAR`, `ACTVTYPE`/`ACTVCODE`/`TASKACTV`, `UDFTYPE`/`UDFVALUE`) | Snapshot |

Pipeline (reuses the M1 derived-document path):

```
Upload .xer → register as Document (type: Schedule) revision
  → parse XER tables (all tables kept raw in lake bronze, §28)
  → validate against XER DocumentSchema (required tables/columns, P6 version, single vs multi-project)
  → build ScheduleSnapshot + typed activity tables (immutable)
  → compare with previous snapshot / baseline: added/removed activities, date shifts,
    float erosion, logic changes, % complete movement, critical path changes
  → publish: set as current (approval optional) → Schedule.SnapshotPublished event → feed, webhooks
```

- **Linking is by stable Activity ID, not snapshot row.** A link from an IWP to activity `A1230` resolves to whatever the current snapshot holds, and can be viewed as of any earlier snapshot. Activities that vanish from a new snapshot flag their links as orphaned.
- **Snapshot series** give schedule history without P6 access: trend of float per activity, slip charts, and "what was planned for this IWP at data date X".
- **Look-aheads** (3–6 week) are generated from the current snapshot plus AWP readiness, so planners see which upcoming activities have unready IWPs.
- Activities link to CWPs/IWPs/systems; readiness and progress can be compared to activity dates.
- **Later:** P6 XML import, P6 EPPM API connector (read, then progress write-back), and the schedule display/commenting module (§13).

---

## 10. TUI (Textual) specification

### 10.1 Layout

```
┌ Header: Company ▸ Project ▸ Module ▸ View        [sync ● live] [user] [inbox 3] ┐
├──────────┬──────────────────────────────────────────────┬────────────────────────┤
│ Nav tree │ Main area: grid / record / dashboard          │ Context panel          │
│ (modules,│ (tabs; split horizontal/vertical)             │ (links, preview,       │
│ saved    │                                               │ history, thread,       │
│ views)   │                                               │ psets, attachments)    │
├──────────┴──────────────────────────────────────────────┴────────────────────────┤
│ Footer: context key hints  │ status / job progress  │ selection count            │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- Panels are collapsible and resizable (keyboard and mouse-drag).
- Multiple tabs; each tab can be split; layouts are saved per user.
- Responsive: narrow terminals collapse side panels into overlays.

### 10.2 Core screens / widgets

| Widget | Purpose |
|---|---|
| **Command palette** | Fuzzy search over every command, record type, saved view, and record key. The universal entry point |
| **Go-to** | Type any record key → open it (`g` then key, or palette) |
| **Data grid** | Virtualised; column chooser incl. pset properties and linked-record fields; sort, filter, group, inline edit, multi-select, freeze columns, copy as TSV/CSV |
| **Filter bar** | Structured query builder plus text query language (e.g. `status:open discipline:PIP psets.nde.method=RT due<+7d linked:NCR`) |
| **Record view** | Header (key, title, status, badges, workflow actions), tabs: Details · Psets · Links · Files · Thread (if enabled) · Feed · History · Trace |
| **Reference tray** | Collects references from any screen for linking (§7.2) |
| **Thread** | Record message thread with dispatch commands (§21.5) |
| **about:config** | Settings screen (§30) |
| **Sync status** | Online/offline, pending commands, conflicts (§22.7) |
| **Forms** | Auto-generated from schema + pset definitions; field-level validation; lookup fields with inline search; "create and link" from lookups |
| **Link picker** | Universal cross-type search and link (§7) |
| **Trace view** | Tree/graph of linked records with expand/collapse |
| **Dashboards** | Tiles with counts, mini-bars (Unicode), sparklines; each tile drills to a filtered grid |
| **Inbox** | Assignments, mentions, approvals, due items |
| **Job monitor** | Imports, extractions, report runs with progress and logs |
| **File preview** | Metadata, text extract, image/PDF thumbnail where the terminal supports graphics; "open externally" |
| **Diff view** | Revision-to-revision and import diffs |

### 10.3 Interaction model

- **Keyboard:** modal-light (no vim mode required), with optional vim-style navigation profile. Every action shown in the footer for the focused context and in the palette.
- **Mouse:** click to focus/select, double-click to open, right-click context menus mirroring keyboard actions, drag to resize panels, scroll everywhere, clickable links/keys in text, clickable column headers for sort.
- **Both:** shift-click/ctrl-click multi-select aligns with `space`/`shift+arrow` selection; context menu shows the shortcut beside every item, teaching keys over time.
- **Discoverability:** `?` shows contextual help; `F1` full key map; palette shows shortcuts.
- **Live data:** rows changed by others highlight briefly; record view shows "updated by X — reload/merge" on conflict.
- **Undo:** "Undo last action" issues a compensating event where the workflow allows (within a short window); otherwise offers "Correct…".
- **Accessibility:** high-contrast and colour-blind-safe themes, no meaning by colour alone (status also as text/symbol), screen-reader-friendly mode with reduced decoration.

### 10.4 Default key map (proposal)

| Key | Action |
|---|---|
| `Ctrl+P` / `:` | Command palette |
| `g` + key | Go to record by key |
| `/` | Focus filter/search |
| `Enter` / double-click | Open record |
| `Esc` | Back / close overlay |
| `n` | New record (current type) |
| `e` | Edit |
| `Ctrl+S` | Save |
| `l` | Link… (link picker) |
| `R` / `Shift+R` | Add selection to reference tray / open tray |
| `Alt+←` / `Alt+→` | Back / forward through followed references |
| `Ctrl+O` | Open related (picker over everything linked) |
| `K` | Preview card for the reference under the cursor |
| `L` | Show links panel |
| `t` | Trace view |
| `d` | Raise deficiency against selection |
| `T` / `c` | Open record thread / compose thread message (if enabled) |
| `a` | Attach file |
| `h` | History |
| `w` | Workflow actions (transition menu) |
| `Space` / `Shift+↑↓` | Select / extend selection |
| `Ctrl+A` | Select all (in grid) |
| `b` | Bulk actions on selection |
| `x` | Export current view |
| `Ctrl+T` / `Ctrl+W` | New / close tab |
| `Ctrl+\` / `Ctrl+-` | Split vertical / horizontal |
| `F6` / `Shift+F6` | Cycle panels |
| `[` / `]` | Previous / next record in current list |
| `F` | Activity feed for current context (record, project, hashtag) |
| `M` | Toggle model context panel for the current record (§23.5) |
| `Ctrl+M` | Open the record in the full web model workspace (browser / QR) |
| `p` | Post to feed (composer) |
| `Ctrl+,` | about:config (settings) |
| `?` / `F1` | Contextual help / full key map |

All bindings user-configurable; conflict detection in the binding editor.

### 10.5 Specialised fast-entry screens

- **Toolcrib issue/return** (scan-friendly, single-line flow)
- **Weld daily log** (grid entry by iso, with welder/WPS auto-checks)
- **Boltup entry** (joint, tool, values; tool calibration check)
- **Inspection checklist runner** (question-by-question, keyboard answer keys)
- **Punch walkdown** (rapid create with location/system prefill)

### 10.6 Screen sketches

Sketches are 100 columns wide. Every bracketed control, tab, key hint, record key, `#tag`, and `@mention` is also clickable; context menus (right-click) list the same actions with their keys.

**1. Shell: grid with live updates and context panel**

```text
┌─ ACME ▸ P123 ▸ Piping ▸ Welds ───────────────────────────── ● live · jsmith · ✉ 3 · ⏱ 2 at risk ─┐
│ ▾ P123 North Exp│ [Welds: A12 open RT] [IWP-PIP-0042] [+]            │ 47-1234-W013  v7          │
│   Home          │ / status:welded area:A12 nde:pending psets.nde     │ Welded · BW · CS · Ø6.0   │
│   Feed          │   .method=RT                     ⌫ clear  ★ save   │ ─ Links ────────────────  │
│   Inbox (3)     │ ───────────────────────────────────────────────────│  ↑ spool  47-1234-S03     │
│ ▸ Documents     │      Weld         Iso     Ø in Status  NDE IWP     │  ↑ iso    ISO-1234 rC ▪   │
│ ▸ Eng. data     │  [x] 47-1234-W012 1234 rC  6.0 Welded  RT… 0042    │  ↑ line   6"-P-1234-A1    │
│ ▸ AWP / WBS     │ ▶[x] 47-1234-W013 1234 rC  6.0 Welded  RT… 0042    │  ↑ iwp    IWP-PIP-0042    │
│ ▸ Materials     │  [x] 47-1234-W014 1234 rC  2.0 Welded  RT… 0042    │  ↑ tp     TP-047-003      │
│ ▸ Quality       │  [ ] 47-1236-W002 1236 rB  8.0 Welded  RT… 0044    │  ↓ nde    NDE-0331 (RT)   │
│ ▾ Piping        │  [ ] 47-1236-W003 1236 rB  8.0 Welded* RT… 0044    │  ↔ welder W-117 ✓ qual    │
│    Lines        │  [ ] 47-1240-W007 1240 rA  4.0 Welded  RT… 0047    │ ─ Psets ────────────────  │
│    Isos         │  [ ] 47-1240-W008 1240 rA  4.0 Repair  RT✗ 0047    │  wps      WPS-CS-01       │
│    Spools       │  …  612 rows · sorted Iso ▲ · grouped: none        │  vt       Accept          │
│  ▶ Welds        │                                                    │  nde      RT 10% · lot 12 │
│    NDE          │ * row changed by mlee 4s ago (live)                │  x.hydro  Y (P123)        │
│    Bolted joints│                                                    │ ─ Files 2/3 ───────────   │
│ ▸ Testing       │ ┌ Tiles ────────────────────────────────────────┐  │  ✓ vt-photo  ✓ fitup      │
│ ▸ Completions   │ │ Welded 1,204/1,880 ▕████████████▏     64%     │  │  ✗ nde_report (req.)      │
│ ▸ Correspondence│ │ RT backlog 37 ▕███▏  Reject rate 2.1% ▕▏      │  │ ─ Feed (4) ─────────────  │
│ ▸ Models        │ └───────────────────────────────────────────────┘  │  mlee: root gap ok, see   │
│ ▸ Schedule (XER)│                                                    │  photo #47-1234-W013      │
│ ★ Saved views   │                                                    │ ▪ pinned revision         │
├─────────────────┴────────────────────────────────────────────────────┴───────────────────────────┤
│ Enter open  l link  d deficiency  b bulk  w workflow  F feed  : palette  ? help                  │
│ 2 selected · RT request draft ▸ [b]                       sync ✓ seq 48,211,933                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Rows changed by others are marked and briefly highlighted. Columns include promoted pset properties and denormalised reference columns from current-state tables (§5.4).
- The context panel follows the cursor: links, psets, file-slot completeness, and the record's feed.

**2. Record view: psets by layer and enforcement**

```text
┌─ 47-FV-1001 · Control valve · FCV on 6"-P-1234-A1 discharge ─────────── Design ▸ [w] transition ─┐
│ Details   [Psets]   Links 14   Files 3   Feed 6   History 23   Trace   Model                     │
│ ─────────────────────────────────────────────────────────────────────────────────────────────────│
│ Property                    Value                    Layer       Rule                 Source     │
│ ▾ valve_data   co:acme/engineering 3.2.0 · required · conformance 5/5 ✓                          │
│   size_in                   6.0 in                   standard    ● req@Design   ✓     ISD rC     │
│   rating                    CL300                    standard    ● req@Design   ✓     ISD rC     │
│   body_material             SS316L-NACE → SS316L     std + P123  ● extensible   ✓     ISD rC     │
│   fail_action               Fail closed              standard    ■ locked       ✓     ISD rC     │
│   seat_leakage              —                        standard    ○ advisory     !                │
│   x.fat_witness_by          @party:client-acme       P123 x.     optional                        │
│   x.tie_in_window           SD-2027-03               P123 x.     optional                        │
│ ▾ prj.shutdown_tie_in       P123 custom 1.4.0                                                    │
│   window / isolation        SD-2027-03 / ISO-PLAN-7  P123        optional                        │
│ ▸ enrich.ai_classifier      2 proposed values         enrichment  [Enter] review                 │
│ ▸ src.ifc.Pset_ValveTypeCommon   MOD-PIP-001 rD       source      4 mapped · 2 unmapped          │
│ ▸ src.legacy-spi.*          17 values (legacy load)  source      mapping 15/17                   │
│                                                                                                  │
│ ● required  ○ advisory  ■ locked  x. project custom section  ! conformance warning               │
│ Waiver: none   Conformance mode: strict with waivers   Effective schema #a91f…3c                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ e edit  Tab next  W request waiver  P propose promotion  h property history  m map source  ? help│
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Standard, project-custom (`x.`), project pset, enrichment, and source layers are visible at once, with enforcement markers and the source document for each value.
- Waivers and promotions start from here; both go through approval workflows.

**3. Command palette** (overlay, `Ctrl+P` or `:`)

```text
┌─ > weld 1234 ────────────────────────────────────────────────────────┐
│ ▶ 47-1234-W012        Weld · Welded · ISO-1234 rC          g         │
│   47-1234-W013        Weld · Fit-up                                  │
│   ISO-1234            Isometric · rev C · IFC                        │
│   47-1234-S03         Spool · On site · HOLD                         │
│ ─ Screens & views ─────────────────────────────────────────────      │
│   Weld daily log for ISO-1234                          Ctrl+D        │
│   View: Welds on ISO-1234 (saved)                                    │
│ ─ Commands ────────────────────────────────────────────────────      │
│   New weld on ISO-1234                                 n             │
│   Raise deficiency against ISO-1234                    d             │
│   Show ISO-1234 in model (slice SLC-ISO-1234, 6 MB)    M             │
│                                                                      │
│ Tab type filter · ↑↓ move · Enter run · Esc close · mouse: click     │
└──────────────────────────────────────────────────────────────────────┘
```

**4. Link picker** (`l` on a selection)

```text
┌─ Link 3 selected welds → ────────────────────────────────────────────────────────────┐
│ Relation [raised against ▾]   Type [NCR ▾]   Scope [P123 ▾]   Pin [floating ▾]       │
│ Search  ncr bevel▏                                                                   │
│ ──────────────────────────────────────────────────────────────────────────────────── │
│ ▶ NCR-P123-0042   Bevel damage, spools ex Fab-A       Open      QA    2026-10-07     │
│   NCR-P123-0039   Bevel prep out of tolerance A11     Closed    QA    2026-09-22     │
│   CAR-P123-0011   Fab-A bevel protection              Open      QA    2026-10-08     │
│   + Create new NCR and link                                         Ctrl+N           │
│ ─ Preview ────────────────────────────────────────────────────────────────────────── │
│ NCR-P123-0042 · Open · disposition: repair · 6 linked welds · 2 spools · CAR-0011    │
│ Note  [Found at fit-up, see photos on W012-W014                              ]       │
│                                                                                      │
│ Space select · Enter link · Ctrl+N create & link · Esc cancel      [ Link ] [Cancel] │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**5. IWP readiness**

```text
┌─ IWP-PIP-0042 · 6" P-1234 tie-ins, A12 · Readiness 5/7 ──────────────────────── Ready ▸ blocked ─┐
│ Check                   State     Detail                                          Resolve via    │
│ ───────────────────────────────────────────────────────────────────────────────────────────────  │
│ ✓ Documents current     ok        12 pinned · all IFC · 0 stale pins                             │
│ ✗ Materials reserved    short     2 × 6" CL300 WN flange (PI-0457) · ETA 10-16    MR-0221 ▸      │
│ ✗ Scaffold              erecting  SCF-0088 · inspection due 10-15                 SCF-0088 ▸     │
│ ✓ RFIs                  ok        RFI-P123-0102 answered 10-03                                   │
│ ✓ Inspections planned   ok        ITP-PIP lines 4.1-4.6 · witness: client H/W                    │
│ ✓ Labour                ok        LR-0031 · 2 welders, 2 fitters · W-117 qual ✓                  │
│ ✓ Model slice           ok        SLC-IWP-0042 · 18 MB · mobile ✓                                │
│                                                                                                  │
│ Scope   24 welds (31.5 in-dia) · 8 joints · 3 tags · est 212 h · cc 4210-PIP-WLD                 │
│ Sched   A1230 · ES 10-19  EF 10-30  TF 4d · XER snapshot DD 2026-10-05 (prev TF 9d ▼)            │
│ Feed    3 posts · #hold on 47-1234-S03 → constraint proposed [a] accept                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Enter open check · c add constraint · i issue (blocked) · p print pack · M open slice · F feed   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**6. Activity feed pane** (`F`)

```text
┌─ Feed · P123 · following ───────────── [All] Posts Events #hold ─┐
│ mlee · 09:42                                                     │
│ Spool arrived with damaged bevels #47-1234-S03 #hold             │
│ @party:fab-a  [photo ×2]                                         │
│   ack 3 · proposal: constraint on IWP-0042 [a] · thread ▸ [t]    │
│ ───────────────────────────────────────────────────────────────  │
│ ▤ jsmith recorded 14 welds on ISO-1234 rC · 09:15                │
│ ▤ NDE-0331 RT results in via inbound:acme-nde · 2 rejects        │
│   47-1240-W008 ✗  47-1240-W011 ✗  → repair welds proposed [a]    │
│ ▤ SLC-IWP-0042 model slice updated · 14 objects changed          │
│ ▤ Commercial notice issued (restricted)                          │
│ ───────────────────────────────────────────────────────────────  │
│ agent:triage ⚙ · 08:51                                           │
│ Classified 3 incoming letters → Technical (2), Quality (1)       │
│   review in Inbox ▸                                              │
│                                                                  │
│ p post · . react · o open · t open thread · f follow · j/k move  │
└──────────────────────────────────────────────────────────────────┘
```

**7. Correspondence response clocks**

```text
┌─ Correspondence ▸ Clocks · P123 ─────────────────────── domain [All ▾] · 11 running · 2 at risk ─┐
│ Left    Bar          Item            Domain      Subtype          Clause  Due         Owner      │
│ ───────────────────────────────────────────────────────────────────────────────────────────────  │
│ 2d !!   ██▏          P123-EW-0017    Commercial  Early warning    15.2    2026-10-11  kchan      │
│ 3d !!   ███▏         P123-RFI-M-0119 Technical   RFI (client)     8.4     2026-10-12  dpatel     │
│ 6d      ██████▏      P123-NCRN-0008  Quality     NCR notification 11.1    2026-10-15  qa.lead    │
│ 9d      █████████▏   P123-CN-0021    Commercial  Change notice    16.1    2026-10-20  kchan      │
│ 14d     ████████████ P123-IF-0004    Interface   Interface query  —       2026-10-27  awong      │
│ ▒ 1 legal clock hidden (restricted to legal roles)                                               │
│                                                                                                  │
│ Selected  P123-EW-0017 · time bar 14 cd from awareness 09-27 · source RFI-P123-0102 (impact)     │
│           evidence: 3 photos, 2 daily reports, A1230 float -5d (DD 10-05 vs 09-28)               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Enter open · i issue draft · e escalate → Legal · x export register · ? help                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**8. Schema workbench** (§27)

```text
┌─ Schema workbench · co:acme/engineering 3.3.0-draft ──────────────────────── Draft ▸ [r] review ─┐
│ ▾ co:acme          │ valve_data   applies ed.Tag where class in (ControlValve, ManualValve)      │
│   core-ext 1.1.0   │ 3.3.0-draft (base 3.2.0) · adoption mandatory · custom section ≤10          │
│   engineering ●    │ ─────────────────────────────────────────────────────────────────────────── │
│   quality 2.4.1    │   Property         Type           Unit  Enforce   Values      Mat  Change   │
│   piping 3.0.0     │   size_in          decimal        in    required  —           ✓             │
│   correspondence   │   rating           PressureClass  —     required  closed      ✓             │
│   codelists 7.2.0  │   body_material    MaterialCode   —     required  extensible  ✓             │
│ ▾ x/P123           │   fail_action      FailAction     —     locked    closed      ·             │
│   engineering 1.4.0│ + seat_leakage     LeakageClass   —     advisory  closed      ·    added    │
│   prj 1.4.0        │ ~ actuator_type    ActuatorType   —     advisory  extensible  ·    renamed  │
│ ▸ x/P118           │                      alias: actuator_typ (3.2.0) → no event rewrite         │
│ ─────────────────  │ ↑ fat_witness_by   Party          —     advisory  —           ·    promoted │
│ Drafts 2           │                      from x.fat_witness_by on P123, P118 (212 values)       │
│ In review 1        │                                                                             │
│ Conformance ▸      │ Lint ✓ descriptions · ✓ units · ! 1 near-duplicate: seat_leak_cls (P118)    │
│ Waivers 3 ▸        │                                                                             │
│                    │                                                                             │
├─ Impact · linkml diff: additive 2 · rename 1 · promote 1 · breaking 0 ───────────────────────────┤
│ 4,812 tags on 6 projects · newly non-conformant 0 · cur_ed_tag +2 cols · 6 project views         │
│ Lake: ed_tag +2 cols (schema evolution) · MCP tool schemas 3 · webhook mappings on old path 1     │
│ (acme-bi → owner notified) · reports using actuator_typ 2 (auto-aliased)                         │
│ v validate · i impact · d diff · m mappings · t test on sample · r send to review · ? help       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**9. Record with model context slid out** (`M`, §23.5)

```text
┌─ NCR-P123-0042 · Bevel damage, spools ex Fab-A · Open ┬────────── ◆ model context available [M] ─┐
│ Details  Psets  [Links 9]  Files  Feed  History       │ Model context · MOD-PIP-001 rD    ◂ M    │
│ ──────────────────────────────────────────────────────│ ┌─────────────────────────────────────┐  │
│ Relation        Record             Status             │ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │  │
│ raised against  47-1234-W012       Welded             │ │ ░  ┌─────── 47-1234-S03 ───────┐  ░ │  │
│ raised against  47-1234-W013       Welded             │ │ ░  │ ▓W012    ▓W013    ▓W014   │  ░ │  │
│ raised against  47-1234-W014       Welded             │ │ ░  └───────────────────────────┘  ░ │  │
│ raised against  47-1234-S03        HOLD               │ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │  │
│ resolves        CAR-P123-0011      Open               │ │ rendered snapshot (kitty / sixel)   │  │
│ referenced by   P123-NCRN-0008     Issued             │ └─────────────────────────────────────┘  │
│                                                       │ Text context (any terminal)              │
│ Model context (x-ref)                                 │  P123 › CWA-12 › Unit 47 › EL+104.5      │
│  xref_model_id       MOD-PIP-001 (floating → rD)      │  grid C/7 · near: 47-FV-1001, P-4702B    │
│  xref_model_location EL+104.5 · grid C/7 · CWA-12     │  5 linked objects · 2 HOLD · 3 RT pend   │
│  objects             5 (via links: welds, spool)      │ ←/→ orbit preset  +/- zoom  o objects    │
│  viewpoint           VP-0221 (attached photo view)    │ v viewpoints  B open in browser / QR     │
│                                                       │ P pair with open web viewer (sync)       │
│                                                       │                                          │
├───────────────────────────────────────────────────────┴──────────────────────────────────────────┤
│ M toggle model panel · Ctrl+M full-screen viewer (browser) · F6 cycle panels · ? help            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- In terminals with graphics support (Kitty, iTerm2, Sixel), the panel shows a server-rendered snapshot of the record's objects in context. Every terminal gets the text spatial context.
- `P` pairs the TUI with an open web viewer, so moving through records in the TUI flies the viewer in real time.

**10. Web/desktop model workspace** (wireframe for the web client, §23.3)

```text
┌─ Search  weld nde:pending area:A12 ▏            records · objects · properties · views ──────────┐
├────────────────────────────────────────────────────────┬─────────────────────────────────────────┤
│ [Federated: PIP rD + STR rB + E&I rA ▾] [Overlay: RT ▾]│ 47-1234-W013 · Weld · Welded  v7        │
│                                                        │ [Record] Links Files Feed History       │
│    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░        │ ─────────────────────────────────────── │
│    ░                                          ░        │ Iso      ISO-1234 rC (pinned)           │
│    ░   ╔═════ 6"-P-1234-A1 ═════════════╗     ░        │ Spool    47-1234-S03  HOLD              │
│    ░   ║   ●W012    ▓W013▓    ○W014     ║     ░        │ Line     6"-P-1234-A1                   │
│    ░   ╚══════════════╦═════════════════╝     ░        │ IWP      IWP-PIP-0042  blocked 5/7      │
│    ░    P-4702B ▒▒▒▒▒▒╝      47-FV-1001 ◇     ░        │ Test pkg TP-047-003                     │
│    ░                                          ░        │ NDE      RT 10% · lot 12 · pending      │
│    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░        │ Context  via spool → iso → line         │
│     ▓ selected (W013)   ░ x-ray context                │          (inherited, 3 objects)         │
│                                                        │ ─────────────────────────────────────── │
│                                                        │ Results 3 of 14 ◂ ▸    list ▾  grid ▸   │
│ Legend  ● RT pending  ○ RT done  ✗ reject  ▓ selection │  ▶ 47-1234-W013  Welded   RT pending    │
│ Storey EL+104.5 · Grid C/7 · CWA-12                    │    47-1234-W012  Welded   RT pending    │
│                                                        │    47-1240-W008  Repair   RT reject     │
│ ⌖ Fit  ✂ Section  ◐ X-ray  ⊟ Isolate  ⟷ Measure        │                                         │
│ ◎ Save viewpoint · → Raise RFI / punch from view       │                                         │
│                                                        │                                         │
├────────────────────────────────────────────────────────┴─────────────────────────────────────────┤
│ Divider drag ◂▸ · select object → record · select record → fly to · Esc clears · / search        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**11. Narrow terminal** (80 columns or less: side panels become overlays on `F2`/`F3`)

```text
┌─ P123 ▸ Welds ──────────────────────────── ● ✉3 ─┐
│ / status:welded area:A12 nde:pending             │
│ ───────────────────────────────────────────────  │
│ ▶ 47-1234-W013  Welded  RT…  IWP-0042            │
│   47-1234-W014  Welded  RT…  IWP-0042            │
│   47-1236-W002  Welded  RT…  IWP-0044            │
│                                                  │
│ F2 nav · F3 context · Enter open · : palette     │
└──────────────────────────────────────────────────┘
```

**12. Links tab with reference tray** (§7)

```text
┌─ IWP-PIP-0042 · 6" P-1234 tie-ins, A12 ──────────────────────────┬────────────── Reference tray ─┐
│ Details Psets [Links 52] Files Thread 9 Feed History Trace       │ Reference tray (4)        [R] │
│ ───────────────────────────────────────────────────────────────  │ ───────────────────────────── │
│ ▾ contains (35)      welds 24 · joints 8 · tags 3      [expand]  │ [x] 47-1240-W008   Weld       │
│ ▾ requires (3)                                                   │ [x] NCR-P123-0042  NCR        │
│     MR-0221    Material requisition   Open        ✓ verified     │ [x] VP-0221        Viewpoint  │
│     SCF-0088   Scaffold               Erecting                   │ [ ] D-4471         client DMS │
│     LR-0031    Labour requisition     Approved                   │                               │
│ ▾ references (12)    documents                                   │ Link checked here as:         │
│     ISO-1234 rC         ▪ pinned   ✓ current                     │  [requires ▾] [floating ▾]    │
│     ISO-1236 rB         ▪ pinned   ! rC issued 10-08 [u] re-pin  │   [ Link 3 ]  [ Clear tray ]  │
│ ▾ blocked by (1)     CON-0412 material constraint  Open          │                               │
│ ▸ referenced by (5)  RFI-P123-0102 · P123-EW-0017 · +3           │ Collected from: grid, model,  │
│ ▸ suggested (2)      47-FV-1002 (enricher 0.82)  [a] accept      │ search, feed, thread          │
│ ▾ external (2)       client DMS D-4471 ↗ · ERP PO 4500123 ↗      │                               │
│ ! expected but missing: permit-to-work (rule: IWP@Issued)        │                               │
│                                                                  │                               │
│                                                                  │                               │
├──────────────────────────────────────────────────────────────────┴───────────────────────────────┤
│ Enter follow · Alt+← back · l link · R add to tray · u re-pin · v verify · x retract · t trace   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Grouped by relation, with stale pins, suggestions, external references, and expected-but-missing links.
- The tray collects references from any screen; checked items link to the current record in one action.

**13. Record thread with dispatch** (§21.5)

```text
┌─ IWP-PIP-0042 · Thread · 9 participants ───────── dispatch on · project setting threads.enabled ─┐
│ 07:02 rgarcia (GF)    Crew P-07 starting tie-ins 07:30. Flanges short for W019/W020.             │
│ 07:05 lchen (mat)     /dispatch material-request 2x 6" CL300 WN urgent                           │
│                       ▤ MR-0224 created · requires-link added · ETA 13:00 · @kpatel              │
│ 07:11 sbrown (QC)     Client witness needed for W019 at 10:00 @party:client-acme                 │
│ 07:12 sbrown (QC)     /raise inspection witness #47-1234-W019 10:00                              │
│                       ▤ INS-0881 scheduled · guest link sent to client-acme                      │
│ 09:40 rgarcia (GF)    /assign @crew:P-07 W021-W024                                               │
│                       ▤ 4 welds assigned to crew P-07                                            │
│ 09:41 agent:planner   SCF-0088 inspection due 10-15. Propose /dispatch scaffold-inspect  [a]     │
│ ───────────────────────────────────────────────────────────────────────────────────────────────  │
│ > /dispatch scaffold-mod SCF-0088 add lift EL+107▏                                               │
│   Tab complete · /help · Enter send · @ people · # records · Ctrl+R reference tray               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**14. about:config** (§30)

```text
┌─ about:config · P123 (inherits ACME) ────────────────── filter: threads · 9 of 214 · 3 modified ─┐
│ Setting                                  Value               Type   Origin       Lock            │
│ ───────────────────────────────────────────────────────────────────────────────────────────────  │
│ threads.enabled                          true                bool   P123 ●       ·               │
│ threads.enabled_types                    [IWP, NCR, RFI, +2] list   P123 ●       ·               │
│ threads.dispatch.enabled                 true                bool   ACME         ·               │
│ threads.dispatch.roles                   [gf, foreman, qc…]  list   P123 ●       ·               │
│ threads.domains.legal.enabled            false               bool   ACME         ■ locked        │
│ threads.external_parties.can_post        true                bool   default      ·               │
│ threads.retention_days                   3650                int    ACME         ·               │
│ threads.notify.mentions                  inbox+email         enum   default      ·               │
│ threads.agents.can_dispatch              propose             enum   ACME         ■ locked        │
│                                                                                                  │
│ threads.enabled_types · Record types that get a message thread on this project.                  │
│ default []  ·  ACME [IWP, NCR, RFI]  ·  P123 [IWP, NCR, RFI, ScaffoldRequest, TestPackage] ●     │
│ Scopes: company, project · Changed by dpatel 2026-10-02 (reason: field pilot)                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Enter edit · r reset to inherited · L lock (company) · h history · d diff vs project · / filter  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. APIs and MCP

### 11.1 Inbound APIs

| Interface | Details |
|---|---|
| **REST/JSON** | Resource-oriented, generated from the model; OpenAPI 3.1; JSON-LD `@context` on responses; filtering with the same query language as the TUI; pagination by cursor; ETags = `stream_version` |
| **Commands endpoint** | `POST /commands/{CommandName}` for workflow transitions and complex operations (mirrors service layer) |
| **Events** | `GET /events?after={seq}&scope=…&type=…` (pull), WebSocket/SSE subscriptions (push) |
| **Files** | Pre-signed upload/download URLs to object store; server verifies hash on registration |
| **Bulk** | Async import jobs with validation reports |
| **Auth** | OAuth2/OIDC bearer tokens; API keys for service accounts; scopes per module |

### 11.2 Outbound

- **Webhooks** (signed, retried, with replay by `seq`)
- **Connectors** (plugin framework): cost system, P6 (XER/XML/API), email (IMAP/Graph), ERP/procurement (PO lines, receipts), engineering databases/3D models (tag lists, line lists), document management systems of clients/EPCs, BI tools (read replicas / exports to Parquet)
- Connectors run as jobs, emit ledgered imports, and record source system IDs in an `external_ids` map on every record for idempotent sync.

### 11.3 MCP

**MCP server (suite → AI agents)**

- **Resources:** record by key/URI, saved views, schema/model docs (LinkML/JSON-LD), pset definitions, standards registry, document text extracts.
- **Tools:** `search_records`, `get_record`, `get_links`, `trace`, `create_record`, `update_psets`, `link_records`, `transition_workflow`, `raise_deficiency`, `run_report`, `start_extraction`, `validate_against_schema`, `propose_import` (staged, needs human approval).
- **Prompts:** templated tasks (e.g. "draft RFI from selected records", "summarise NCR trends for area X").
- All tool calls run with the invoking user's permissions, are tagged `source=mcp:{agent}`, and can be configured as "propose only" (create drafts/staged changes) per tool and per project.
- Resource-change notifications via the change feed.

**MCP client (suite → external MCP servers)**

- The suite can call external MCP servers (e.g. a vendor's document system, a cost system, an AI extraction service) through configured connectors, primarily inside the document processing pipeline and connectors framework.

> §18 expands this section into the full open integration architecture: integration-point granularity, the event catalog, webhook delivery, actions, rules, enrichment, external parties, and AI hooks.

---

## 12. Base reporting

Reporting runs on projections (and, at scale, a reporting replica / columnar export). Every report is: a saved query + layout template + parameters, runnable in TUI, via API, MCP, or on schedule; outputs XLSX, CSV, PDF, and on-screen. Report runs are ledgered with parameters and data `seq` watermark, so any issued report is reproducible.

| Module | Base reports |
|---|---|
| Document Control | Document register; revision history; overdue reviews; transmittal log; documents by status/discipline; derived-document validation status; stale pinned revisions |
| Engineering Data | Tag register by class/system/status; missing mandatory psets; tag changes since date; pattern-violation report |
| AWP/WBS | CWP/IWP status; IWP readiness & constraint log; constraints by type/owner/age; backlog of ready IWPs (weeks of backlog) |
| Materials | Stock on hand by location/item; transaction log; MTO vs received vs issued; shortages against IWPs; equipment utilisation & location; consumable usage by cost code; heat number traceability |
| Quality | Inspection log; ITP compliance; deficiency/punch aging; NCR/CAR/QSR registers and trends; RFI log with response times; calibration due/overdue; calibration impact report |
| Piping | Weld log; weld progress (count/inch-dia) by line/iso/area; welder performance & repair rate; NDE status & backlog; NDE reject rate by welder/method; PWHT status; boltup log and joint status |
| Pressure Testing | Test package status & readiness; test certificates; reinstatement status |
| Systems Completion | ITR status by system/subsystem/discipline; punch by category; MC/RFC certificates; completion burn-down; handover dossier completeness |
| Requisitions/WO | Open requisitions; scaffold register (status, tag colour, inspection due); scaffold quantities on hire; labor requisition forecast by craft/week; WO backlog |
| Correspondence | Master register (confidentiality-filtered); per-domain registers; responses due/overdue; running clocks and time bars; RFI log with response times and impact flags; commercial notice/claim register with values (estimated vs assessed); contractual notice log with proof of delivery; escalation chains |
| Cost/Schedule links | Records without cost code; quantities by cost code vs budget; IWPs vs P6 activity dates; activities with open constraints |
| Cross-cutting | Audit trail by record/user/date; data health; user activity; link integrity (orphans, voided targets) |

Dashboards (TUI tiles; later web) for project home, QC, piping, completions, and materials.

---

## 13. Extensibility and future modules

- **Module plugin contract:** a module ships (a) LinkML schema fragment, (b) command/event handlers, (c) projections, (d) workflows, (e) TUI screens (Textual widgets registered by entry point), (f) reports, (g) MCP tools/resources, (h) migrations. Discovered via Python entry points.
- **Costing frontend (future):** cost code tree with the measure matrix (hours/qty/$ × budget/actual/earned/FTC/EAC), period selector, variance highlighting, record drill-through (which welds/IWPs contributed quantities), comments per code/period. Later: forecast editing pushed back via connector.
- **Schedule frontend (future):** activity list and text Gantt (TUI), filtered by WBS/activity codes; linked AWP readiness overlay; comments per activity; later progress statusing exported back to P6.
- **Web client:** v1 ships only a lightweight web model workspace (§23.3). Mobile and desktop PWAs are deferred and will use the same API, generated forms, and the offline replica protocol (§22.9). Textual's web serving remains a power-user option ("TUI in a browser").
- **Extension record types:** directory/object-store backed types for fast expansion without releases (§31).

---

## 14. Tech stack

| Layer | Dev | Prod | Notes |
|---|---|---|---|
| Language | Python 3.12+ | same | Type-hinted throughout |
| TUI | Textual (+ Rich) | same | Embedded or remote client mode |
| Schema/semantics | LinkML → Pydantic v2, JSON Schema, SQL DDL, JSON-LD, SHACL | same | Codegen in build; checked into repo |
| Validation | Pydantic v2, `jsonschema` | same | JSON Schema 2020-12 for derived documents/psets |
| Data access | SQLAlchemy 2.x Core (+ Alembic for projection schema) | same | Event store via thin repository layer |
| Database | SQLite (WAL, JSON1, FTS5) | PostgreSQL 16+ (JSONB, GIN, `pg_trgm`, LISTEN/NOTIFY, partitioning on events) | Adapter interface; parity test suite runs on both |
| Object store | MinIO (docker compose) | S3-compatible (AWS S3, Azure via gateway, or MinIO cluster) | `boto3`/`aioboto3`; content-addressed keys; versioning + object lock (WORM) in prod |
| API | FastAPI (Starlette), Uvicorn | same, behind reverse proxy | OpenAPI generated; WebSocket/SSE |
| Realtime | In-process async bus | LISTEN/NOTIFY + cursor reads; optional NATS later | |
| Jobs | Lightweight DB-backed queue (SQLite table) behind an interface | Postgres-backed queue (e.g. `SKIP LOCKED` pattern) | Workers for extraction, imports, reports, connectors |
| MCP | Official MCP Python SDK (server + client) | same | stdio for local, streamable HTTP for server |
| Auth | Local accounts | OIDC/SAML via IdP (e.g. Entra ID, Keycloak) | |
| Document processing | `pypdf`/`pdfplumber`, table extraction (e.g. Camelot / Docling), OCR (Tesseract), `openpyxl`, optional AI-assisted extraction via MCP/LLM | same | Pluggable extractor registry |
| Units | `pint` | same | Registry-backed |
| Reporting | Current-state views for operational reports; DuckDB over the lakehouse for heavy reports; Jinja2 templates; `openpyxl` (XLSX); WeasyPrint (PDF) | same | |
| Lakehouse | DuckDB + DuckLake (catalog: SQLite/DuckDB file; data: Parquet on MinIO) | DuckLake (catalog: PostgreSQL; data: Parquet on S3-compatible store) | Pin extension version; confirm maturity at Phase 1 (§28) |
| Schema runtime | linkml-runtime (`SchemaView`) for package merge; generated JSON Schema for validation; `linkml diff` for classification | same | Effective schema cached by hash (§27.3) |
| P6 | XER parser (in-house or proven library), all tables to bronze | + P6 XML, then EPPM API | XER-first (M11) |
| Model slicing & snapshots | IfcOpenShell element extraction for slices; headless Chromium + xeokit for record snapshots | same, scaled workers | Slices < 50 MB for mobile (§23.4) |
| Terminal graphics | Textual + an image widget supporting Kitty/iTerm2/Sixel, text fallback | same | Model context panel (§23.5) |
| Simulation | Simulation orchestrator (Python) exposing its own MCP server; role agents via MCP | sandbox tenants only | §29.5 |
| Search | FTS5 | Postgres FTS + trigram; optional OpenSearch later | |
| Tooling | `uv`, `ruff`, `mypy`/`pyright`, `pytest`, `hypothesis` (property tests for projections), `textual-dev` snapshot tests | + CI, containers, IaC | |
| Observability | `structlog` | OpenTelemetry → chosen backend | |
| Packaging | `uv` workspace monorepo; one package per module | Container images | |
| Event envelope | CloudEvents 1.0 (JSON), LinkML-defined `data` | same | Same envelope for webhooks, the change feed, and exports |
| Webhook delivery | DB-backed outbox + delivery workers | same, horizontally scaled; optionally a managed delivery service | HMAC signing (Standard Webhooks convention), retries, DLQ, replay |
| Rules/mapping | Declarative rule + mapping definitions validated by LinkML; JSONata or JMESPath for payload mapping | same | No arbitrary code in rules; code goes in actions |
| Uploads | S3 multipart with presigned parts (resumable); MinIO | same; S3 event notifications | Client-side SHA-256; server verification |
| File processing | ClamAV (malware), libvips/Pillow (thumbnails), ExifTool (metadata), Tesseract (OCR) | same, scaled workers | |
| Web model workspace | TypeScript page hosting the xeokit component + generated record panel | same | v1 web surface: this page plus guest-link/portal pages |
| PWAs (deferred) | TypeScript PWA with IndexedDB replica | same | §22.9 |
| Offline replicas | Embedded SQLite ledger + local object cache; sync protocol over HTTPS | same | §22 |
| Settings | Setting registry (LinkML) + ledgered values | same | §30 |
| Extension types | Type packages in a directory (dev/git) or object store (prod); watcher + registry | same | §31 |
| 3D | IfcOpenShell (parse, validate, extract); xeokit-convert (IFC → XKT, Node); xeokit SDK viewer; IDS validation (ifctester) | same, GPU not required | xeokit SDK is AGPL-3.0 with commercial licences available; see Q9 |
| Backup | Litestream (SQLite → MinIO/S3) | pgBackRest (full/incremental + WAL PITR); object-store versioning, replication, object lock | Plus an independent ledger archive (§24) |
| Infra | docker compose | Containers on Kubernetes or a managed container platform; IaC (OpenTofu/Terraform) | |

**Repository layout (proposal)**

```
/schema            LinkML sources (core + per module), generated artefacts
/core              ledger, projections, links, psets, workflow, numbering, auth
/adapters          sqlite, postgres, minio/s3, queue
/modules/<m>       per-module handlers, projections, workflows, reports, mcp, tui
/api               FastAPI app, websocket/sse, webhooks
/mcp               MCP server + client glue
/tui               app shell, shared widgets (grid, palette, link picker, forms)
/connectors        cost, p6, email, erp, ...
/extractors        document extractor plugins
/reports           templates
/dev               docker-compose (minio), seed data, demo project
```

---

## 15. Non-functional requirements (initial targets)

| Area | Target |
|---|---|
| Scale (prod, per project) | 1M+ records, 50M+ events, 5M+ files, 300 concurrent users |
| TUI responsiveness | Grid scroll/filter < 150 ms on projections up to 100k rows (virtualised, server-side paging beyond) |
| Realtime latency | Change visible to other clients < 2 s |
| Durability | Ledger committed synchronously; object store with versioning + object lock in prod |
| Rebuild | Full projection rebuild for a large project within a maintenance window (hours, not days); per-module rebuild supported |
| Availability (prod) | 99.5% initial |
| Security | TLS everywhere; encryption at rest; least privilege; signed webhooks; per-tool MCP permissions |
| Portability | Same test suite green on SQLite and Postgres |

---

## 16. Roadmap

### Phase 0 — Foundations (core platform)
- LinkML core model, codegen pipeline
- Ledger, projections, change feed (SQLite + Postgres adapters, parity tests)
- Record envelope, psets, links, numbering, workflow engine, comments, attachments (MinIO)
- TUI shell: palette, nav, grid, record view, forms, link picker, history, trace
- REST API skeleton + MCP server skeleton (read tools)
- Event catalog (CloudEvents + LinkML), webhook subscriptions and delivery, upload service with attachment slots
- Activity stream core: event cards and posts, hashtag parser, TUI feed pane
- Ops baseline: backup (Litestream/pgBackRest), ledger archive, restore drill, upgrade and rebuild tooling
- Agent-dev baseline: AGENTS.md, scaffolding CLI, dev MCP server, CI codegen drift check
- Cross-reference operations v1: link lifecycle, key detection, reference tray, back/forward (§7)
- about:config settings v1 (§30); extension type registry v0 (§31)
- Materialized current-state generator for every entity type (§5.4)
- Layered psets, schema registry v0, effective schema compiler, conformance (§6.3, §27)
- Simulator v0 driving the suite through MCP (§29.5)
- DuckLake lakehouse v0: bronze events + silver current state (§28)
- Increment plan: §29.3
- **Exit:** create/link/pset any generic record in TUI, API, and MCP. Live updates between two TUIs. An external webhook receiver gets a signed event for a filtered subscription. Full restore from backup passes verification.

### Phase 1 — Information backbone
- M1 Document Control incl. revision control, derived-document pipeline with schema validation
- M2 Engineering Data + Standards registry
- M10 Correspondence core + Technical/RFI, Document control, Commercial, and General domains (Quality, Legal, HSE, Interface follow in Phase 2–3)
- M11: cost code snapshots; **P6 via XER upload snapshots** with snapshot compare and look-aheads
- Schema workbench, package review/publish workflow, adoption and impact reports (§27)
- Lakehouse: XER history and document marts; reports move to the lake where heavy
- Legacy loader framework and first loads (document register, tag lists, line lists) (§29.6)
- Base reports for these
- Optional record threads with dispatch (§21.5)
- Actions registry, rules engine, inbound webhooks, enrichment providers (first: AI document extraction)
- **Exit:** receive a PDF schedule/list, derive validated CSV/XLSX, publish into target records with full traceability. The full chain is visible in the feed and pushed to subscribers.

### Phase 2 — Execution planning and materials
- M3 field work packaging: GC WBS, path of construction, CWA/CWP/IWP, constraints, release sign-off, backlog, weekly workface planning cycle, rules of credit, IWP packs, closeout
- M4 Materials (item library, inventory, toolcrib, equipment)
- M9 Requisitions/WO (scaffold, labor, material, general)
- Lakehouse gold marts for AWP readiness history, materials, schedule trend
- Simulation scenarios for AWP/materials/scaffold
- **Exit:** issue an IWP with readiness check covering documents, materials, scaffold

### Phase 3 — Quality and piping
- M5 Quality incl. calibration and Issue engine (RFI/NCR/CAR/QSR)
- M6 Piping (welds, NDE, boltup)
- M7 Pressure testing
- Offline replicas (site laptop, site server) with sync and merge (§22); TUI fast-entry screens for field capture
- M12 Models: IFC ingest, XKT conversion, tag mapping, model workspace (split model/data + search), slices for mobile (< 50 MB), spatial context resolver, slide-out model context in web, PWA, and TUI
- External-party access (guest sign-off links, subcontractor/client accounts)
- **Exit:** weld → NDE → test package → certificate end-to-end. Progress is colour-overlaid in the model. NDE contractor results arrive by inbound webhook.

### Phase 4 — Completions and turnover
- M8 Systems completion, ITRs, certificates, handover dossiers
- Completion dashboards
- **Exit:** subsystem MC certificate with snapshot and dossier export

### Phase 5 — Expansion
- Cost display/commenting module; schedule display/commenting module (over XER snapshot history)
- P6 XML import and EPPM API connector
- Lakehouse: cross-project benchmarking, per-project data sharing catalogs
- Mobile and desktop PWAs on the replica protocol (§22.9)
- Full desktop web client
- Connector hardening (ERP, client DMS, engineering DBs), MCP write tools broadened

### Roadmapping considerations
- **Build the platform once:** resist module-specific shortcuts around links, psets, workflows, and numbering; each later module should be mostly schema + workflow + screens.
- **Pilot early with real data:** run Phase 1 against a live project's document register to shake out numbering, revisions, and schema pipeline.
- **Schema governance:** a change process for company psets/standards (owner, review, versioning) is needed before multiple projects run.
- **Event schema evolution:** commit to upcasting discipline from day one; breaking event changes are costly.
- **SQLite/Postgres parity:** keep SQL dialect-neutral in core; isolate dialect features (JSONB indexes, LISTEN/NOTIFY) behind adapters.
- **AI in the loop:** default to "propose, human approves" for writes; log prompts/model versions for derived data provenance.
- **Web readiness:** keep all business logic out of the TUI; TUI screens consume the same query/command contracts the web client will.
- **Data migration:** plan importers from spreadsheets and incumbent tools (common sources: Excel weld logs, legacy completions databases, DMS exports). See §29.6.
- **Schema change is routine:** invest early in the registry, classification, and impact tooling (§27); it pays back every week.
- **Simulation before pilots:** every module ships with simulator actors, so demos, load tests, and report validation never wait for real data.

---

## 17. Risks and open questions

| # | Item | Notes |
|---|---|---|
| R1 | Projection rebuild time at production scale | Mitigate with snapshots, per-module rebuild, partitioned events |
| R2 | Pset query performance | Typed index tables + GIN on JSONB; monitor heavy filters |
| R3 | TUI suitability for drawing/markup-heavy tasks | Keep markups external; preview + open externally; web later |
| R4 | Extraction accuracy from PDFs | Schema validation + human review gate; per-source extraction profiles |
| R5 | Workflow configurability vs complexity | Ship sensible company defaults; limit per-project overrides |
| Q1 | Which cost system(s) and integration method (API, file drop)? | Drives M11 connector |
| Q2 | ~~P6 access~~ | **Decided:** XER upload snapshots first; XML/API later |
| Q3 | Required reference data standards (CFIHOS, ISO 15926, client-specific)? | Affects LinkML mappings |
| Q4 | E-signature legal requirements per jurisdiction/client | |
| Q5 | Hosting model (self-hosted vs managed cloud) and IdP | |
| Q6 | Do subcontractors/clients get accounts (external parties), and with what isolation? | Affects ABAC model |
| Q7 | Gap-free numbering requirements by record type | Affects numbering service concurrency |
| Q8 | Retention periods and legal hold requirements | Object lock settings |
| R6 | Integration sprawl (hundreds of subscriptions/agents nobody owns) | Integration registry with owners, expiry, usage stats, auto-disable on failure |
| R7 | Feed noise drowns signal | Aggregated event cards, importance levels, mutes, digests, sensible defaults |
| R8 | Offline conflicts in field capture | Command replay, declared merge policies, quantities as transactions, conflict inbox (§22) |
| R9 | Large IFC models on mobile devices | Mobile opens slices only, under 50 MB, with automatic splitting (§23.4) |
| R10 | Agent-written code and agent runtime writes eroding quality/trust | Spec-driven generation, CI gates, human review for schema/migration/security changes, "propose" mode for runtime agents |
| Q9 | xeokit licensing: AGPL-3.0 compliance vs commercial licence | Must be decided before Models ships to customers |
| Q10 | Which external parties (NDE, scaffold, subcontractors, client) integrate by webhook vs portal accounts? | Drives Phase 3 external-access work |
| Q11 | Push notification needs on iOS (installed-PWA requirement) | Deferred with the PWAs |
| R11 | Contractual clocks miscalculated (calendars, stop rules) | Clock definitions reviewed by commercial/legal; simulation tests; clocks recomputable from ledger |
| Q12 | Which contract forms (e.g. FIDIC, NEC, bespoke) need preconfigured domain workflows and clauses? | Drives Commercial/Legal templates and clocks |
| Q13 | Where does privileged legal correspondence live: in the suite (restricted) or only referenced from an external legal system? | Affects Legal domain scope |
| R12 | Frequent schema change breaks integrations, reports, or meaning | Classification, aliases, impact reports, notice periods, forbidden meaning changes (§27) |
| R13 | DuckLake maturity | Lake is a rebuildable copy; Parquet + SQL underneath; version pinned; evaluate at Phase 1 |
| R14 | Simulated data is unrealistic and hides real problems | Calibrate scenario rates from legacy data; validate with pilot users; treat as supplement to pilots |
| R15 | Spatial context wrong or misleading (bad mappings, stale inheritance) | Show `ctx_source` everywhere; recompute on revision; mapping review queue |
| Q14 | Which pset properties must be `locked` company-wide from day one? | Drives first company packages |
| Q15 | Who are the company schema stewards per discipline, and what review cadence is realistic? | Drives §27.9 |
| R16 | Threads become a second email: decisions stay in chat | Dispatch creates linked records; `/summarise`; threads off by default |
| R17 | Extension type sprawl | Registry ownership, review, adoption metrics, promotion/retirement reviews (§31) |
| Q16 | Which rules-of-credit standards and IWP sizing norms does the GC already use? | Seeds M3 company packages |
| Q17 | How are subcontractors expected to work: portal accounts, guest links, or their own systems via webhooks? | Drives M3 subcontracted scope |
| Q18 | Which sites need offline replicas, and for how long can they be disconnected? | Sets `sync.max_offline_days` and site node rollout |

---

# Part II — Openness, activity, offline, models, operations, development

## 18. Open integration architecture

The goal is that external people, systems, and AI agents can **use** the data (read, query, export), **enrich** it (add properties, links, classifications), and **trigger and receive actions** on almost anything. Every interaction uses the same permissions, ledger, and semantic model as the native clients.

### 18.1 Integration surface

| Direction | Mechanism | Typical use |
|---|---|---|
| Out (push) | **Outbound webhooks** (filtered subscriptions) | Notify NDE contractor of new requests; push IWP issue to a field app; feed a data lake |
| Out (push) | **Realtime streams** (WebSocket/SSE) | Live dashboards, external UIs, agents watching a project |
| Out (pull) | **Events API** (`after=seq`), **Query API**, **bulk/CDC exports** (Parquet, NDJSON, JSON-LD/RDF) | BI, analytics, ML, semantic graph stores |
| Out (call) | **Actions** executed by webhook, MCP tool, connector, or job | "Send to fabricator", "Request AI review", "Create client transmittal" |
| In (push) | **Commands API**, **inbound webhooks** with declarative mappings, **email-in**, **file-drop** (bucket event) | NDE results, survey data, scaffold contractor status, client DMS returns |
| In (enrich) | **Enrichment API** (namespaced psets, links, classifications with provenance and confidence) | AI classification, geocoding, model-derived quantities, vendor data |
| In (gate) | **Validation hooks** (synchronous, on workflow transitions only) | Client system must confirm before "Issued for Construction" |
| Bi-directional | **MCP server and client** (§11.3) | AI agents read, propose, act |
| People | **External-party accounts**, **scoped guest links**, feed participation | Third-party inspector sign-off, client comments, subcontractor punch response |

### 18.2 Integration points — granularity

Subscriptions, actions, rules, enrichers, and hooks can attach at any level of this hierarchy. Narrower always takes precedence, and every level inherits permissions:

| Level | Example selector |
|---|---|
| Company | All projects of company `ACME` |
| Project | Project `P123` |
| Module | `piping`, `quality`, `documents`, `correspondence` |
| Correspondence domain | `correspondence.commercial`, `correspondence.rfi` (§9 M10) |
| Record type | `piping.Weld`, `quality.NCR` |
| Record class / pset filter | Tags where `class = ControlValve`; welds where `psets.nde.required = RT` |
| Saved query | Any saved view (e.g. "Open punch A in subsystem 47-01") |
| Single record | `NCR-P123-0042` or `urn:tl:01J…` |
| Field / pset property | Changes to `Weld.status` or `psets.valve_data.size_in` |
| Workflow transition | `Document: InReview → Issued`; `TestPackage: * → Passed` |
| Clock / deadline | `ResponseClock.Warning` on any commercial notice; time bar 5 days from expiry |
| Link relation | Any `raised against` link added to a `Weld` |
| File slot | New file in the `mtr` slot of any `Receipt` |
| Feed / hashtag | Posts tagged `#safety` in project `P123`; mentions of `@nde-contractor` |
| Action | Every invocation/result of action `send_to_nde` |

**Subscription filter model.** Every filter is a LinkML-validated `SubscriptionFilter`. It combines scope, event types (glob, e.g. `piping.Weld.*`), record selector (type + query-language expression, or record IDs), changed-fields, transitions, link relations, file slots, and hashtags. The same filter language is used in the TUI, the API, and rules.

### 18.3 Event catalog and envelope

- Every event type is defined in LinkML, with its schema, description, semantic URI, and version. A browsable, generated **event catalog** is published from it: docs, JSON Schema, sample payloads, and AsyncAPI.
- One **CloudEvents** envelope is used for webhooks, streams, the events API, and exports:

```json
{
  "specversion": "1.0",
  "id": "01J9Z6Q4…",
  "source": "https://tl.example.com/c/acme/p/P123",
  "type": "tl.piping.Weld.ResultRecorded.v1",
  "time": "2026-10-09T03:14:07Z",
  "subject": "urn:tl:01J8…",
  "dataschema": "https://tl.example.com/schema/piping/WeldResultRecorded/1",
  "datacontenttype": "application/ld+json",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "tlcorrelationid": "01J9…",
  "tlactor": "user:jsmith",
  "data": {
    "@context": "https://tl.example.com/schema/context.jsonld",
    "origin": {
      "id": "urn:tl:01J8…",
      "key": "47-1234-W012",
      "type": "piping:Weld",
      "uri": "https://tl.example.com/c/acme/p/P123/r/piping.Weld/47-1234-W012",
      "version": 7,
      "api": "https://tl.example.com/api/v1/p/P123/piping/welds/01J8…"
    },
    "changes": { "status": ["FitUp", "Welded"], "psets.vt.result": [null, "Accept"] },
    "links": [
      { "rel": "belongs_to", "type": "piping:Spool", "key": "47-1234-S03", "uri": "…" },
      { "rel": "belongs_to", "type": "awp:IWP", "key": "IWP-PIP-0042", "uri": "…" }
    ]
  }
}
```

- **Payload modes** (per subscription):
  - **thin**: envelope + origin only. The receiver fetches what it needs.
  - **delta**: changes + immediate links.
  - **full**: the record projection at that version.
- Payloads **always** include the originating record URI, the ledger `seq`, and the stream version, so any consumer can trace back or re-fetch an exact version.
- Records under restricted confidentiality (e.g. legal/privileged correspondence) only ever emit **thin** payloads, and only to subscriptions whose owner is cleared for that confidentiality level.

### 18.4 Outbound webhooks

| Aspect | Specification |
|---|---|
| Subscription record | Owner, integration app, target URL, filter (§18.2), payload mode, event schema version pin, batching (single / batch up to N or T seconds), secret(s), status, expiry, rate limit |
| Delivery | Transactional **outbox** written with the event, then delivered by workers. At-least-once delivery, ordered per subject (record), parallel across subjects |
| Security | HMAC-SHA256 signatures (Standard Webhooks headers: id, timestamp, signature). Secret rotation with overlap. Optional mTLS. Egress allow-list per company |
| Retries | Exponential backoff with jitter over ~24 h, then dead-letter queue. Auto-disable after sustained failure, with owner notified |
| Replay | Replay by `seq` range, time range, or DLQ selection. Receivers dedupe on the event `id` |
| Observability | Per-subscription delivery log (status, latency, response excerpt), success-rate metrics, TUI/web screens for both |
| Testing | "Send test event" with sample payload from the catalog; local tunnel support in dev |
| Webhooks provided by default | Record lifecycle (`Created`, `Updated`, `StatusChanged`, `Voided`), `Link.Added/Removed`, `Pset.ValuesSet`, `File.Uploaded/Processed/Rejected`, `Workflow.Transitioned`, `Signature.Applied`, `Action.Requested/Completed/Failed`, `Feed.Posted/Mentioned`, `Import.Completed`, `Validation.Failed`, `Enrichment.Proposed/Accepted`, `Calibration.Failed`, `Constraint.Cleared`, `IWP.Ready`, `TestPackage.Ready`, `Certificate.Issued`, `Model.RevisionPublished`, `Correspondence.Received/Issued/ResponseDue/Overdue`, `ResponseClock.Started/Warning/Expired/Stopped` |

### 18.5 Inbound integration

- **Commands API.** Every service-layer command is callable, with an `Idempotency-Key` and an expected `stream_version` for concurrency.
- **Inbound webhook endpoints.** Per integration app: `POST /in/{app}/{endpoint}`. Each endpoint has:
  - signature verification (HMAC/JWT/mTLS),
  - a declarative **mapping** (JSONata) from the foreign payload to one or more commands,
  - key resolution (external ID → record via `external_ids` or number patterns),
  - dry-run mode,
  - an error queue with manual fix-and-retry.

  Example: an NDE contractor posts RT results, which map to `RecordNDEResult` on the matching welds.
- **Email-in.** Project/module/domain/record-specific addresses (e.g. `ncr-p123-0042@in.…`, `commercial-p123@in.…`). The body becomes a comment or correspondence and attachments go into file slots. Domain addresses pre-classify incoming correspondence (§9 M10).
- **File-drop.** Bucket prefixes watched per integration. A dropped file starts a document registration or import job.
- Every inbound write is ledgered with `source=inbound:{app}/{endpoint}` and the raw payload stored as an object, for audit.

### 18.6 Synchronous validation hooks

- These attach **only** to workflow transitions and selected commands, never to every write.
- The external endpoint must answer `allow`, `deny` (with reasons), or `allow_with_warnings` within a timeout. Each hook is configured fail-open or fail-closed.
- The decision and response are stored on the transition event.

### 18.7 Actions registry

An **Action** is a named, parameterised operation that can be invoked on a record, a selection, or a context.

| Field | Notes |
|---|---|
| `name`, `label`, `description`, semantic URI | Shown in TUI/mobile context menus, the command palette, the API, and MCP |
| `applies_to` | Integration-point selector (§18.2) |
| `parameters` | LinkML class → auto-generated form |
| `executor` | `webhook` (sync or async callback), `mcp_tool` (external MCP server), `connector`, `job` (internal), `agent` (AI agent task) |
| `permissions` | Roles allowed to invoke; whether it needs approval |
| `result_handling` | Map the result to commands, attach files, post to feed, or create linked records |
| `side_effect_class` | `read`, `propose`, `write`, `external` (affects confirmation UX and MCP exposure) |

The lifecycle (`Action.Requested → Running → Completed/Failed`) is ledgered, linked to the target records, and shown in the feed. Async executors call back to a signed result URL.

### 18.8 Rules (automation)

- Rules take the form **When** event matches filter → **If** condition (query-language expression over the event and the current record) → **Then**:
  - run actions,
  - send notifications,
  - post to the feed,
  - add links/hashtags,
  - propose records.
- Rules are declarative, versioned, scoped (company/project/module/domain), and dry-runnable against historical events ("what would this rule have done last month?").
- Loop protection: rule-caused events carry causation IDs, and there is a maximum chain depth.
- Examples:
  - Calibration failed → run the impact query and propose an NCR linking the affected inspections.
  - Post with `#safety` → notify HSE and pin it to the project feed.
  - IWP ready → webhook to the field app.
  - RFI answer received with `cost_impact = yes` → propose a linked commercial change notice and start its notification clock.

### 18.9 Enrichment

- **Enrichers** are registered integration apps (AI or otherwise) that subscribe to events and write back only into:
  - their own **namespaced psets** (e.g. `enrich.ai_classifier.*`),
  - **proposed links**,
  - **classifications/hashtags**,
  - **derived files** (e.g. OCR text, thumbnails, model quantities).
- Each enrichment value carries provenance: enricher, version, model/prompt hash for AI, confidence, inputs (record version + file hash), and timestamp.
- **Acceptance policy** is set per pset/property: `auto` (above a confidence threshold), `propose` (human accepts in an enrichment review queue), or `shadow` (stored, not shown, for evaluating an enricher).
- Enrichment never overwrites authoritative fields. Promoting an enriched value to an authoritative field is an explicit, ledgered user action.
- A typical enricher is incoming-correspondence triage: suggest the domain, subtype, referenced records, and response clocks. It stays in `propose` mode by default.

### 18.10 Data utilisation

- **Query API:** the same query language as the TUI, with projections and pset filters, cursor pagination, and field selection. An optional GraphQL facade is generated from LinkML for graph-shaped reads (record + links n-deep).
- **Lakehouse:** the DuckLake lakehouse (§28) is the primary analytics path. Agents get a read-only `lake_query` MCP tool.
- **Bulk exports:** scheduled or on-demand Parquet/NDJSON per record type and per project. A **CDC stream** of events goes to object storage, partitioned by date and scope, for lakehouse ingestion.
- **Semantic exports:** JSON-LD and RDF (Turtle/N-Quads) dumps per project, using the LinkML-generated OWL/SHACL. They load directly into graph stores for cross-project analytics and AI retrieval.
- **Read replicas** (prod) for heavy BI, with governed views per role.
- Confidentiality classes (e.g. legal-privileged) are excluded from bulk and semantic exports unless explicitly included by an authorised export definition.

### 18.11 External people

| Mechanism | Use |
|---|---|
| **External-party accounts** | Subcontractors, client reps, third-party inspectors, vendors. Bound to a `Party` record and limited by ABAC to their scope (records assigned to or shared with their party) |
| **Scoped guest links** | Single-purpose, expiring, optionally OTP-protected links: sign off an inspection, respond to an RFI, upload MTRs to a receipt slot, acknowledge a transmittal. All activity is ledgered as `guest:{party}/{link}` |
| **Feed and thread participation** | External parties can post in feeds and take part in threads of records shared with them, and can be @mentioned |
| **Portal view** | A trimmed web page for external parties (part of the small v1 web surface with guest links): "my items", uploads, sign-offs, correspondence addressed to them |

### 18.12 AI hooks

- **Agent identities** are first-class principals, each with an owner, scopes, a project allow-list, budgets (calls, tokens, cost), and a default **propose-only** mode.
- AI agents use the same surfaces as everyone else: MCP (§11.3), subscriptions/webhooks, actions (`executor: agent`), enrichment, feed posts (marked as agent-authored).
- **Approval gates:** agent writes outside "propose" go to a review queue unless the project explicitly grants auto-commit for that command type. Outgoing correspondence drafted by an agent always needs human issue.
- **Provenance:** agent events record model ID, prompt/tool-call hash, input record versions, and the human on whose behalf the agent acts.
- **Retrieval for AI:** semantic exports and document text extracts are available as MCP resources, filtered by permissions, so agents never see what their principal can't.

### 18.13 Integration governance

- **Integration registry:** every app, subscription, inbound endpoint, action, rule, enricher, and agent has an owner, purpose, scopes, expiry/review date, and usage/failure stats.
- **Credentials:** OAuth2 client credentials per app. Fine-grained scopes (`{module}:{read|write|act}`, project lists, correspondence domains). No shared keys.
- **Limits and controls:** rate limits and quotas per app and per company. An emergency **kill switch** per app, per company, or globally.
- **Integration audit report:** who accessed what, when, and via which app.

---

## 19. LinkML model for integration and activity

Everything in Part II is modelled in LinkML alongside the domain schema. That way webhooks, feeds, actions, and exports carry the same semantics, and every object links back to its originating records.

### 19.1 Identifier and URI scheme

| Form | Example | Use |
|---|---|---|
| Stable URN | `urn:tl:01J8XK…` (ULID) | Permanent identity, never changes |
| Resolvable URI | `https://{host}/c/{company}/p/{project}/r/{type}/{key}` | Human and API resolvable. Content negotiation: HTML, JSON, JSON-LD |
| Versioned URI | `…/{key}@v7` or `…?asof=seq:48211933` | Exact historical version |
| Schema URI | `https://{host}/schema/{module}/{Class}` | LinkML class/slot URIs, also in `@context` |

### 19.2 Core integration classes (sketch)

```yaml
# schema/core/integration.yaml (excerpt)
id: https://tl.example.com/schema/core/integration
prefixes:
  tl: https://tl.example.com/schema/
  prov: http://www.w3.org/ns/prov#
  as: https://www.w3.org/ns/activitystreams#
default_prefix: tl
imports: [linkml:types, tl:core/record]

classes:
  RecordRef:
    description: Pointer to an originating record at a specific version.
    slots: [id, key, record_type, uri, version, seq]

  LedgerEvent:
    class_uri: prov:Activity
    slots: [event_id, seq, event_type, scope, subject, actor, source,
            recorded_at, effective_at, correlation_id, causation_id, changes, links]
    slot_usage:
      subject: {range: RecordRef, required: true}

  SubscriptionFilter:
    slots: [scope_selector, event_types, record_selector, changed_fields,
            transitions, link_relations, file_slots, hashtags]

  WebhookSubscription:
    is_a: Record
    slots: [integration_app, target_url, filter, payload_mode,
            event_schema_version, batching, secret_ref, expires_at]

  ActionDefinition:
    is_a: Record
    slots: [name, applies_to, parameters_class, executor, side_effect_class,
            requires_approval, result_handling]

  ActionInvocation:
    is_a: Record
    class_uri: prov:Activity
    slots: [action, targets, parameters, invoked_by, status, result, result_files]
    slot_usage:
      targets: {range: RecordRef, multivalued: true}

  EnrichmentValue:
    class_uri: prov:Entity
    slots: [target, property_path, value, enricher, enricher_version,
            confidence, inputs, model_ref, acceptance_state]

  ActivityPost:
    is_a: Record
    class_uri: as:Note
    slots: [author, body, mentions, hashtags, record_refs,
            attachments, visibility, importance]

  ThreadMessage:
    class_uri: as:Note
    slots: [thread, record, author, body, mentions, record_refs, attachments,
            dispatched_commands]

  Link:
    slots: [from_ref, to_ref, relation, pin, note, source, confidence, status,
            verified_by, verified_at]

  ExternalRef:
    slots: [system, external_id, url, label, last_checked, status]

  EventCard:
    class_uri: as:Activity
    description: Feed rendering of one or more aggregated LedgerEvents.
    slots: [events, summary, subjects, actor, importance]

  Hashtag:
    slots: [text, kind, resolves_to, scope]
```

The correspondence core and domain classes (`Correspondence`, `CorrespondenceDomain`, `ResponseClock`, and so on) are sketched in §9 M10.

### 19.3 Rules

- Every integration and activity object **must** carry `RecordRef`s to its originating records. Examples: a webhook delivery references its event, an action invocation its targets, an enrichment value its inputs, a post its mentioned records.
- PROV-O (`prov:wasDerivedFrom`, `prov:wasAssociatedWith`, `prov:used`) is used for derivation chains: derived documents, enrichment, model conversions, imports.
- ActivityStreams 2.0 vocabulary is used for feed objects, so feeds are exportable and federatable.
- External payload mappings (§18.5) are themselves LinkML-validated, and record which external schema they map from.

---

## 20. Uploads and files

Most record types need files: MTRs, NDE reports, calibration certificates, inspection photos, test charts, scaffold tags, signed certificates, IFC models, correspondence attachments. Files are modelled explicitly.

### 20.1 Attachment slots

Each record type declares **file slots** in LinkML (and psets can add slots):

| Slot attribute | Example |
|---|---|
| `name`, `label` | `mtr`, "Mill Test Report" |
| `cardinality` | one / many |
| `accepted_types` | PDF, image/*, IFC, XLSX, CSV, EML/MSG |
| `max_size` | 50 MB (IFC slot: 2 GB) |
| `required_in_states` | Required before `Receipt: Accepted` |
| `capture_hint` | `camera` (opens camera on mobile), `scan` (document scan), `file` |
| `metadata_pset` | pset filled per file (e.g. photo: before/after, location, direction) |
| `processing` | Pipelines to run: thumbnail, OCR, extraction, model conversion |
| `retention_class` | Drives object lock and retention |
| `confidentiality` | Inherits from the record by default; can be stricter (e.g. legal enclosures) |

Generic, unslotted attachments remain possible on every record.

### 20.2 Upload flow

```
Client computes SHA-256 (streamed) → POST /uploads (slot, size, hash, type)
  → server returns existing object (dedupe) or presigned multipart URLs
  → client uploads parts (resumable, parallel, retry per part; background on mobile)
  → POST /uploads/{id}/complete → server verifies hash & size, malware scan
  → File.Uploaded event; File attached to record slot (ledgered)
  → processing jobs (thumbnail, EXIF strip/extract, OCR, extraction, conversion)
  → File.Processed / File.Rejected events → feed + webhooks
```

- **Quarantine:** files are unreadable by others until the scan passes.
- **Privacy:** EXIF GPS is extracted to metadata, then stripped from the shared rendition (configurable). The original is kept under restricted access.
- **Large files** (models, scans) use multipart with resume across sessions.
- **Bulk upload:** a folder or zip, with key-pattern matching from filenames to records (e.g. `47-1234-W012_RT.pdf` → that weld's `nde_report` slot), shown as a review grid before committing.
- The TUI supports upload by path, drag-and-drop where the terminal supports it, and watch-folder mode. Mobile supports camera, gallery, files, and document scan.
- **Previews:** images, PDFs (page thumbnails), office docs (converted PDF rendition), emails (rendered body + attachment list), IFC (viewer, §23).

---

## 21. Activity stream and record threads

### 21.1 Activity stream (broadcast, no replies)

The activity stream is a **broadcast surface**, not a conversation: a twitter-style, realtime timeline of what is happening, with lightweight hashtag semantics. It has no replies. When a discussion is needed, it happens in the record's **thread** (§21.5), if threads are enabled for that project and record type.

| Item | Source | Example |
|---|---|---|
| **Event card** | Ledger events rendered by templates. Bursts are aggregated by actor/type/target ("Jo recorded 14 welds on ISO-1234 Rev C") | Status changes, uploads, certificates, imports, rule/action results, thread dispatch results |
| **Post** | Human, agent, or external-party authored `ActivityPost` | "Spool S03 arrived with damaged bevels #47-1234-S03 #hold @party:fab-a" |
| **Digest card** | Scheduled summary per feed | "Today in #A12: 3 NCRs opened, 41 ITRs completed" |

- Posts are ledger events (`Feed.Posted`, `Feed.Edited`, `Feed.Retracted`). Edits keep visible history; retractions leave a tombstone.
- **Reactions** are limited to acknowledgements (`ack`, `+1`, `resolved`), controlled by `feed.reactions.enabled`.
- A post or card about a record offers **"Open thread"** (`t`) when that record's thread is enabled.

### 21.2 Hashtag semantics (lightweight)

| Syntax | Kind | Resolution | Effect |
|---|---|---|---|
| `#NCR-P123-0042`, `#47-FV-1001`, `#ISO-1234` | **Record reference** | Parsed via Standards registry numbering patterns, then resolved to a record | Creates a suggested `references` link (§7). The post appears in that record's feed |
| `#area:A12`, `#disc:PIP`, `#sys:47-01`, `#cc:4210` | **Namespaced code** | Standards registry code lists, systems, cost codes | Classifies the post; it appears in that code's feed and is filterable |
| `#PIP`, `#A12` | **Short code** | Unambiguous code-list match; ambiguous ones prompt the author to choose | As above |
| `#safety`, `#hold`, `#decision`, `#urgent`, `#fyi` | **Signal tags** (small, configurable set: `feed.signal_tags`) | Fixed vocabulary | Rules can react (notify HSE, pin, raise importance). They never change records directly |
| `#bevel-damage` | **Topic** (free) | Auto-creates a project-scoped `Topic` on first use | A feed per topic. Topics can be merged, aliased, or **promoted** to a code-list entry |
| `@jsmith`, `@crew:P-07`, `@party:acme-nde` | **Mention** | People, crews, parties, agents | Notification, inbox item, mention webhook |

**Hashtags never mutate records.** Any change a tag implies is a proposal ("This post mentions #47-1234-S03 with #hold. Create a constraint on IWP-PIP-0042?"), accepted with one key.

### 21.3 Feeds and following

- **Feeds:** Home (everything followed), Project, Module, Record (with linked records one hop away, toggle), Hashtag/topic/code, Person/crew/party, Saved query.
- Users **follow** records, hashtags, codes, people, and saved queries; they auto-follow records they create, are assigned to, or are mentioned on.
- **Noise control:**
  - importance levels (system cards low, posts normal, signal tags high),
  - per-feed filters (posts, events, event types),
  - mutes,
  - digests,
  - catch-up collapse after absence.
- **Visibility:** a post inherits the strictest visibility of the records it references, plus the project. Correspondence domains set their own feed policy (M10).
- **Actions from the feed:** react, follow, open record, open thread, add to reference tray (`R`), **convert post into record** (deficiency, RFI, NCR, constraint, correspondence) with photos carried over and a `derived from` link.
- **Integration:** feeds are subscribable via webhooks and streams, exportable as ActivityStreams JSON-LD; agents can post (labelled as agents).

### 21.4 Feed UX (TUI)

- Feed pane (side panel or tab): `j/k` move, `Enter` open, `p` new post, `t` open thread, `f` follow, `.` react, `o` open first referenced record, `R` add to tray.
- Mouse: click any `#tag`, `@mention`, or key.
- The composer autocompletes keys, codes, topics, and people on `#` and `@`.

### 21.5 Record threads (optional) with dispatch

Any record type can have a **message thread**, if the project turns it on. When enabled, people discuss the item in place and **dispatch work directly from the thread**, and every dispatched item links back to the message that caused it.

**Enabling** (about:config, §30):

| Setting | Default | Notes |
|---|---|---|
| `threads.enabled` | `false` | Project switch |
| `threads.enabled_types` | `[]` | Record types with threads (e.g. IWP, NCR, RFI, ScaffoldRequest, TestPackage) |
| `threads.dispatch.enabled` | `true` | Allow slash-command dispatch |
| `threads.dispatch.roles` | — | Roles allowed to dispatch |
| `threads.domains.<domain>.enabled` | legal: `false` (company-locked) | Per correspondence domain |
| `threads.external_parties.can_post` | `true` | External parties on records shared with them |
| `threads.agents.can_dispatch` | `propose` | Agents propose; humans accept |
| `threads.email_bridge` | `false` | Reply-by-email posts into the thread |
| `threads.retention_days` | per company | |

**Model:**
- One thread per record, created on the first message, stored as its own stream (`thread:<record id>`) so messages do not bump the record's version.
- Events: `Thread.MessagePosted`, `Thread.MessageEdited`, `Thread.MessageRetracted`, `Thread.Dispatched`.
- Participants: record owner, assignees, followers, anyone mentioned, crews, external parties (if shared and allowed), agents.
- Messages support key detection (suggested links, §7.2), `@mentions`, `#records`, attachments (file slot `thread_attachment`), and acknowledgements.

**Dispatch commands:**

| Command | Effect |
|---|---|
| `/assign @person\|@crew [items]` | Set assignee on the record or on listed child items (e.g. welds in an IWP) |
| `/dispatch <request-type> [args]` | Create a requisition or work order (material-request, scaffold-erect/mod/inspect, labour, crane-lift, general) or invoke a registered Action (§18.7) |
| `/raise <type> [against] [text]` | Create a deficiency, NCR, RFI, constraint, or inspection request, pre-linked |
| `/link <keys> [relation]` | Add links |
| `/status <transition>` | Workflow transition (guards and signatures apply) |
| `/hold [reason]`, `/release` | Add or clear a constraint (IWPs, test packages) |
| `/due <date>`, `/notify @who`, `/remind <when>` | Dates, notifications, reminders |
| `/summarise` | Agent summary of the thread (posted as a proposal) |

- Each command is a ledgered command: permissions (`threads.dispatch.roles`) and validation apply. Side-effecting commands show a preview to confirm (setting). The result posts back into the thread as a card.
- Created items carry a `dispatched from` link to the message and the thread's record, so the "why" is always one hop away.
- Thread messages do **not** appear in the activity stream; dispatch results do, as normal record events. Mentions go to inboxes.
- Integration: webhooks `Thread.MessagePosted` and `Thread.Dispatched`; MCP `read_thread`, `post_thread_message`, `propose_dispatch`.
- Visibility equals the record's visibility. Restricted records never expose threads to people outside the domain.
- TUI: `T` opens the thread tab, `c` composes; sketch in §10.6.

---

## 22. Offline tolerance: sync and merge (PWAs deferred)

### 22.1 Scope

Mobile and desktop PWAs are **deferred** (§16, Phase 5). v1 offline tolerance is delivered by **replicas**: Throughline running in embedded mode on a site laptop, or as a site server (edge node) serving TUIs on the site LAN. Each replica has its own local append-only ledger (SQLite + local object cache) and syncs with its upstream when connected. The PWAs will reuse the same protocol with an IndexedDB ledger (§22.9).

```
                   ┌──────────────────────────┐
                   │ Central (authoritative)  │  Postgres ledger, canonical seq
                   └────────────┬─────────────┘
                     sync (HTTPS, resumable)
          ┌─────────────────────┴───────────────────────┐
┌─────────▼──────────┐                        ┌─────────▼──────────┐
│ Site node (edge)   │  SQLite ledger         │ Laptop replica     │  SQLite ledger
│ serves site TUIs   │                        │ (embedded TUI)     │
└─────────┬──────────┘                        └────────────────────┘
          │ sync (same protocol, multi-level)
┌─────────▼──────────┐
│ Laptop replica     │
└────────────────────┘
```

### 22.2 Replica model

- **Replica identity:** registered device/node with a certificate, an owner, a **scope subscription** (project, CWAs/areas, IWPs, record types), and a maximum offline duration (`sync.max_offline_days`).
- **The local ledger has two append-only segments:**
  - **Mirror segment:** canonical events pulled from upstream, carrying the upstream `seq`.
  - **Local segment:** provisional entries created while working. Each wraps the **command** (the user's intent) and its provisional events, with:
    - a command ID (ULID, also the idempotency key),
    - the replica ID,
    - a hybrid logical clock timestamp,
    - `captured_at` (device clock) and `effective_at` (business time),
    - a **base context**: the upstream `seq` known at the time, plus the `stream_version` of every stream the command touched,
    - a local hash chain.
- **Local current state** = mirror state + pending provisional events. Provisional rows are marked ◌ in the TUI.
- **Nothing is deleted locally.** After sync, provisional entries are marked reconciled (`Sync.Reconciled`) with a mapping to the canonical event IDs that replaced them.

### 22.3 Sync operation

```
1 handshake   identity, protocol & schema versions, cursors, clock-skew check
2 pull        upstream events after the mirror cursor (scope-filtered) → mirror segment
3 rebase      re-apply pending local commands over the new mirror state (local preview)
4 push files  content-addressed objects referenced by pending commands (dedupe by hash, resumable)
5 push cmds   pending commands in local order, each with its base context
6 merge       upstream re-executes each command against current canonical state → outcome
7 ack         outcomes + canonical events → mirror segment; provisional entries reconciled
8 conflicts   unresolved outcomes → SyncConflict records → inboxes (replica and central)
```

**Commands are replayed; events are never copied.** The central ledger never accepts foreign events verbatim. It re-validates each intent against current state. That keeps one canonical order, and keeps every guard, permission, numbering rule, and hash chain authoritative.

### 22.4 Merge outcomes and policies

| Outcome | Meaning |
|---|---|
| **Accepted** | No concurrent change on the touched streams since the base context |
| **Auto-merged** | Concurrent changes exist, but the merge policy says they are compatible |
| **Conflict** | Needs a person: a `SyncConflict` is opened |
| **Rejected** | Invalid now (permission revoked, record voided, transition impossible); recorded as `Command.Rejected` with the reason |

No command is ever silently lost; every pending command ends in one of these four outcomes.

Merge policies are declared per slot or event type in LinkML (`tl:merge`), with defaults by kind of data:

| Data kind | Default policy | Example |
|---|---|---|
| Append-only facts: new records, inspection results, weld records, inventory transactions, files, thread messages, links added, posts | Always merge (commutative) | Two inspectors record different welds offline |
| Quantities | Modelled as transactions/deltas, never absolute values, so they merge by summation | Toolcrib issue offline + another issue online |
| Set-valued fields (participants, tags, links) | Add-wins; removals apply only to items present in the base | |
| Scalar fields and pset values | Apply if unchanged upstream since base; otherwise field-level conflict, unless the slot declares `lww_effective` (latest `effective_at` wins), `upstream_wins`, or `replica_wins` | Two edits to the same visual inspection result |
| Workflow transitions | Re-evaluated: valid from current state → apply; already in the target state → no-op; otherwise conflict | Two foremen close the same IWP |
| Numbering | Provisional keys (`~P123-NCR-7F3Q`) or reserved ranges per replica (`numbering.offline.mode`); the final key is assigned at merge and the provisional key kept as an alias | |
| Natural-key uniqueness | Duplicate check (e.g. weld number per iso) → conflict "possible duplicate", resolved by merging records (`Record.Merged` + `same as` link) | Same weld logged on two laptops |
| Signatures | Valid only if the signed record hash matches the merged state; otherwise re-sign is required | |
| Formal correspondence | Drafts only offline; issue happens online | |

**Conflict resolution:**
- The conflict screen shows base, mine, and theirs field by field.
- Choices:
  - **keep mine** (re-issued as a new command),
  - **keep theirs** (mine recorded as discarded),
  - **merge field by field**,
  - **merge records**.
- Identical conflicts can be resolved in bulk.
- Agents may propose resolutions; people decide.

### 22.5 Ordering, time and integrity

- Hybrid logical clocks order local work; device clock skew is detected at handshake and flagged on affected events.
- `effective_at` comes from the device; `recorded_at` is the upstream acceptance time; `captured_at` is kept for audit.
- Replicas keep their own hash chain over the local segment and submit it with pushed commands as capture evidence. The central chain covers canonical events only.
- Commands carry the effective schema hash. Upstream upcasts compatible commands; otherwise it raises a "schema changed" conflict for re-validation.

### 22.6 Security

- Replicas receive only what their identity may see; restricted classes (legal, privileged) are never replicated.
- Local stores are encrypted at rest; replicas can be revoked and remotely wiped. A revoked replica's pending commands are quarantined for review, not applied automatically.
- Beyond `sync.max_offline_days`, pending commands need supervisor review before merge.

### 22.7 UX

- Status bar: `● online` or `◌ offline · 14 pending · last sync 2h`. Provisional rows show ◌; conflicts appear in the inbox.
- **Take offline:** choose IWPs or areas before going to a disconnected location. The replica pulls those records, their pinned documents, and their model slice snapshots.
- A sync screen lists pending commands, outcomes, and open conflicts.

### 22.8 Testing

- The simulator (§29.5) injects partitions, concurrent edits, duplicate captures, and clock skew.
- Property-based tests:
  - **convergence**: all replicas and central reach the same state after a full sync,
  - **idempotency**: re-sending commands changes nothing,
  - **no lost writes**: every command ends Accepted, Auto-merged, Conflict, or Rejected,
  - **causal consistency** of the merged order.

### 22.9 Deferred PWA design notes

These are kept for when the PWAs are scheduled:

- **Same protocol:** an IndexedDB ledger implementing the replica protocol, so PWAs are just another kind of replica.
- **First field flows:** feed, record lookup by key/QR, uploads from the camera, inspections and checklists, punch walkdown, weld/boltup entry, toolcrib issue/return, scaffold status, IWP packs, raise RFI, model slices under 50 MB (§23.4), approvals and guest links.
- **UX rules:** one-handed primary actions, touch targets of 44 px or more, outdoor/glove modes, deep links everywhere, QR codes encoding resolvable URIs, Web Push (iOS requires an installed PWA).
- **Native wrapper** only if PWA limits (background upload, MDM, camera) require it.

---

## 23. M12 — Models (3D)

**Principle:** a model is just another versioned document. `ModelDocument` is a Document subtype. Model revisions are Revisions with the full revision control, transmittals, pinning, and feed behaviour from M1. M12 adds model-specific renditions, object extraction, mapping, and viewing.

### 23.1 Record types

| Record | Key fields | Key cross-references |
|---|---|---|
| `ModelDocument` (is_a Document) | Discipline, authoring tool, IFC schema (IFC2x3/IFC4/IFC4.3), coordinate reference / project base point, LOD, area/unit coverage | Systems, areas, CWAs, contracts |
| `ModelRevision` (is_a Revision) | Rev code, purpose, conversion status, object count, validation results | Previous revision, source transmittal |
| Renditions | `ifc` (source, original upload), `xkt` (viewer), `props` (extracted properties, JSON/SQLite), `thumb` (images), optional `glb` | Revision |
| `ModelObject` (projected per revision) | IFC GlobalId, IfcClass, name, storey/space, properties (as psets namespaced `ifc.*`), bounding box | Mapped records (tags, lines, equipment, spools, scaffolds), model revision |
| `ObjectMappingRule` | e.g. "IFC property `Pset_Tag.TagNumber` → Tag key"; class filters; regex transforms | Standards registry patterns |
| `FederatedView` | Set of model revisions (pinned or floating), transforms, default visibility | Model documents |
| `Viewpoint` (BCF-like) | Camera, section planes, visible/hidden/selected/coloured objects, snapshot image, markup | Any record (RFI, punch, NCR, correspondence, post, IWP), federated view |
| `Overlay` | Query + colour rules ("weld status", "ITR completion", "IWP", "test package") | Saved queries |

### 23.2 Processing pipeline

```
Upload IFC (resumable, §20) → register ModelRevision
 → validate: IFC schema check (IfcOpenShell); optional IDS validation (ifctester) against
   project Information Delivery Specification = the model's "x_schema"
 → convert: IFC → XKT (xeokit-convert), thumbnails
 → extract: ModelObjects + properties (IfcOpenShell) → props rendition
 → map: ObjectMappingRules → links ModelObject ⇄ Tag/Line/Spool/Equipment (proposed when ambiguous)
 → diff vs previous revision: added/removed/changed objects & properties; tag coverage changes
 → publish: ModelRevision.Published event → feed card, webhooks, enrichment hooks
```

- IDS validation results are stored like derived-document validation reports. A revision can be "Valid / Invalid against IDS v3".
- Model-derived data (e.g. quantities, tag properties) can be published into Engineering Data through the same ledgered import path as M1 derived documents, keeping provenance to the model revision.

### 23.3 Model workspace (xeokit): model and data side by side

The model is never shown alone. The web/desktop workspace is a **split view** (wireframe in §10.6):

- **model on one side** (xeokit, XKT),
- **data entities on the other** (the standard record view and result lists, using the same generated forms as everywhere else),
- **search as a first-class bar spanning both**.

The goal is visual context for anything, and data context for anything visual.

- **Search across everything at once:** records (keys, titles, any pset layer), model objects (GlobalId, name, IFC class, `src.ifc.*` properties), saved views, hashtags, and locations (grid, level, area). It uses the same query language as the TUI. Results appear simultaneously as a list in the entity panel and highlighted in the model (everything else X-rayed). Counts are shown per category, and results can be isolated or coloured by any field.
- **Two-way selection sync:**
  - Select an object, and its mapped record(s) open in the entity panel (a chooser appears if there are several).
  - Select a record or a result, and the model flies to its objects (direct, mapped, or inherited context, §23.5) and highlights them.
  - Arrow keys through a result list walk the model from item to item.
- **Full record capability beside the model:** edit, workflow transitions, link, comment, upload, raise RFI/punch/NCR from the current view (the viewpoint is attached automatically).
- **Layout:** resizable divider, swap sides, collapse either side, pop the entity panel out to a second monitor (kept in sync over the session channel).
- **Lightweight web component** built on the xeokit SDK, embedded in the web model workspace, guest links, and the slide-out panel (§23.5), and later in the PWAs. Navigation: orbit/pan/zoom, first-person, fit-to-selection, storey views, structure tree. Tools: section planes, X-ray, isolate/hide, measure, annotations.
- **Status overlays:** colour by any saved query, e.g.:
  - weld/joint progress,
  - ITR status by subsystem,
  - IWP assignment and readiness,
  - test package state,
  - open punch and open RFIs,
  - scaffold locations.

  Overlays update live from the change feed.
- **Viewpoints:** save camera + state + snapshot, then link it to an RFI, NCR, punch, correspondence, or post (e.g. "Raise RFI from this view"). BCF 3.0 import/export for exchange with design tools.
- **Federation:** combine multiple model documents (e.g. piping, structural, E&I) at pinned or current revisions. Revision compare highlights changed objects.
- **Mobile (when PWAs ship):** opens **slices only** (§23.4), never full models. The model fills the screen, with the entity panel and search results in a draggable bottom sheet. Touch gestures; simplified toolset (isolate, section, X-ray, select → record).
- **Bulk linking:** a selection of objects can be linked to records in one step (e.g. objects → IWP, objects → punch).
- **TUI:** object tree, properties, mapping status, revision diffs, and overlay summaries as tables. The model context panel and pairing are described in §23.5.
- **Licensing:** the xeokit SDK is AGPL-3.0, with commercial licences available. A licence decision is required before customer distribution (Q9). The viewer is isolated behind a component interface so an alternative (e.g. That Open Engine / web-ifc) could be swapped in.

### 23.4 Model slices

Slices serve IWP packs, offline replicas, TUI snapshots, and the web workspace today. When the PWAs ship (§22.9), mobile devices will only open **small, sliced models**. A slice is a derived, versioned subset of a model revision.

| Record | Key fields | Key cross-references |
|---|---|---|
| `ModelSlice` | Slice rule, source revision(s), IFC size, XKT size, object count, eligibility (`mobile` / `desktop_only`), status | Source `ModelRevision`(s) (`derived from`), the record that defines it (IWP, test package, subsystem, CWA, area/storey), renditions |
| `SliceRule` | Type (storey, area/CWA, system/subsystem, IWP, test package, discipline, bounding box, saved query of objects), parameters, floating or pinned to a revision | Standards, saved queries |

- **Generation:** server-side with IfcOpenShell (element extraction preserving spatial structure, types, and properties) → IFC slice → XKT + thumbnails. Slices are stored as renditions, linked `derived from` the source revision, with the slice rule and tool versions recorded (same provenance as derived documents).
- **Size gate:** a slice is mobile-eligible only if its **IFC is under 50 MB** (company setting, default 50 MB). Larger slices are split automatically by the next rule level (e.g. a CWA by storey, then by discipline) or marked `desktop_only`. The API only offers eligible slices to mobile clients, and the PWA enforces the limit again before download.
- **Automatic slices:** every IWP, test package, and subsystem gets a slice when a model revision is published, so field crews open exactly their scope. IWP offline packs include their slice.
- **Floating slices** regenerate when a new source revision is published. The feed card shows the change ("IWP-PIP-0042 model slice updated: 14 objects changed").
- **Overlays and selection** work on slices exactly as on full models, because object GlobalIds and record mappings are preserved.

### 23.5 Visual context for any record

Any record that is, or can be, cross-referenced to a model can show its model context. In the web model workspace (and later the PWAs) the viewer **slides in from the side** of the record view; in the TUI it is a slide-out context panel.

**Cross-reference fields** (envelope, §6.2):

| Slot | Shown as | Content |
|---|---|---|
| `xref_model_id` | x-ref-model-id | Model document, pinned to a revision or floating to current |
| `xref_model_objects` | x-ref-model-objects | IFC GlobalIds |
| `xref_model_location` | x-ref-model-location | Structured location: level/storey, space, grid, area/CWA, coordinates in project CRS, optional bounding box |
| `xref_viewpoint` | x-ref-viewpoint | Saved viewpoint (camera, sections, visibility) |

**Spatial context resolver.** Most records will never have these set by hand, so a resolver computes context in this order:

1. Explicit objects on the record.
2. Object mappings (§23.1): tags, lines, equipment, spools mapped to model objects.
3. Explicit location: picked in the viewer ("Locate in model"), captured on mobile, or imported coordinates.
4. **Inherited through links**, along per-type paths declared in LinkML (`tl:spatial_context_via`), for example:
   - Weld → `[spool, iso, line]`
   - NCR / deficiency → `[raised_against*]`
   - RFI → `[viewpoint, references*]`
   - Correspondence → `[affected_records*]`
   - IWP → `[slice, contains*]`
   - Test package → `[slice, lines*]`
   - Scaffold → `[xref_model_location, accesses*]`
5. Area/CWA/system bounding box as a last resort.

The result is materialized in current-state columns: `ctx_model_id`, `ctx_object_count`, `ctx_source` (direct / mapped / located / inherited / area), `ctx_location_label`. That makes "has model context" filterable, and lets grids show a ◆ marker. Context is recomputed when a new model revision or slice is published.

**Slide-out behaviour:**

- **Web:** every record view has a model panel (key `M`, or a button) that slides in with the context loaded: the record's objects highlighted, surroundings X-rayed, and the attached viewpoint applied if there is one. Mobile loads the smallest eligible slice (§23.4). The panel expands into the full workspace (§23.3).
- **Grids follow along:** with the panel open, moving through a list (a punch list, NCR's affected welds, RFI register) moves the model to each record.
- **TUI:**
  - (a) In terminals with graphics support (Kitty, iTerm2, Sixel), a **server-rendered snapshot**: headless Chromium running the same xeokit component, cached per record + model revision.
  - (b) Everywhere, a **text spatial context**: location breadcrumb, nearby tagged objects, linked object counts by status.
  - (c) **Pairing** with an open web viewer (same user; code or QR). Then the TUI drives the viewer live.
  - (d) `B` opens the deep link in a browser, or shows a QR code for a phone.
- **Locate in model:** on any record, pick objects or a point to set its cross-reference fields (ledgered, like any edit).
- **Permissions:** the viewer only shows models and objects the viewer may see. Records with restricted confidentiality do not reveal context to others.

---

## 24. Operations

### 24.1 Environments

| Environment | Purpose | Data |
|---|---|---|
| Dev (local) | Developer and agent work | SQLite + MinIO, synthetic seed project |
| CI / ephemeral | Per-branch test environments | SQLite and Postgres (parity), synthetic data |
| Staging | Release validation, upgrade rehearsal, restore drills | Anonymised copy of production (PII and privileged correspondence scrubbed) |
| Production | Live | Postgres HA + S3-compatible store |

Tenant isolation in production: company ID on every row, Postgres row-level security as defence in depth, and a separate bucket prefix and KMS key per company. Optional dedicated database per company for large or regulated customers.

### 24.2 Upgrades

| Concern | Approach |
|---|---|
| Versioning | Semantic versioning of the platform. Each module, LinkML schema, event type, API version, and webhook payload version is versioned independently and recorded in a **compatibility matrix** shipped with each release |
| Schema change classification | `linkml diff` in CI classifies changes as additive, deprecating, or breaking. Breaking changes require a new event type version + upcaster, an API version bump, and sign-off |
| Event store | Never migrated in place. Old events are upcast on read. Rare "copy-transform" migrations write to a new store and are verified by hash before cutover |
| Projections | Projection DDL changes run as **shadow rebuilds**: build v(n+1) projections alongside v(n) by replaying the ledger, catch up to the live `seq`, verify (row counts, checksums, sample queries), then cut over atomically. Rollback = switch back |
| Workflow definitions | Versioned. In-flight records (e.g. an open commercial notice) finish on the workflow version they started on unless explicitly migrated, so contractual clocks are never silently changed |
| Application deploy | Rolling or blue/green. API serves N and N-1 versions. Feature flags per company/project for gradual module rollout |
| Clients and replicas | TUIs and replicas negotiate API and sync-protocol versions on connect; minimum versions can be forced. Replicas must sync pending commands before upgrading across a protocol break |
| Integrations | Webhook subscriptions are pinned to payload versions. Deprecations are announced with dates in the integration registry, and owners are notified. Inbound mappings are tested against new versions in staging |
| Plugins/modules | Declare compatible core versions. Incompatible modules are disabled with a clear error, never half-loaded |
| Dev → prod migration | `tl migrate --from sqlite --to postgres` replays the ledger into Postgres and copies objects with hash verification. The same tool moves a project between environments |
| Rehearsal | Every production upgrade is rehearsed on staging with a recent production copy, including a timed projection rebuild |

### 24.3 Backup

| Layer | Dev | Prod | Notes |
|---|---|---|---|
| Database | Litestream continuous replication to MinIO/S3; SQLite online backup API for snapshots | pgBackRest: weekly full, daily incremental, continuous WAL archive (**PITR**). Encrypted, to a separate account/region | |
| Object store | MinIO versioning | Versioning + cross-region replication + **object lock (WORM)** for retention classes | Content-addressed keys make integrity checks trivial |
| **Ledger archive** | Hourly sealed segments | Sealed segments every N minutes or M events: NDJSON + Parquet, with a signed hash manifest continuing the hash chain. Written to an **independent** bucket/account with object lock | A database-independent restore path: everything can be rebuilt from this plus objects |
| Config & schema | Git | Git + config snapshots in backups | Rules, subscriptions, and definitions are ledgered records anyway |
| Secrets | Local `.env` | Vault/KMS with its own backup and recovery procedure | |
| Search indexes, projections, caches | Not backed up | Not backed up | Rebuildable |

Targets (initial, prod): **RPO ≤ 5 min** for the database (WAL), ≤ 15 min for the ledger archive. **RTO ≤ 4 h** for full-region recovery, ≤ 1 h for a single-database failover.

### 24.4 Restore

- **Full disaster recovery:** restore Postgres via PITR, verify against the ledger archive (hash chain continuity, last `seq`), and reconcile against the object store (every referenced hash present).
- **Rebuild-from-archive (last resort):** fresh database, replay the ledger archive, rebuild projections. Proves the system can survive total database loss.
- **Per-project export/restore:** a portable, signed **project bundle** containing events, referenced objects, schema versions, and a manifest. Used for archiving closed projects, client handover, moving between environments, or restoring a single project without touching others. Bundles can exclude confidentiality classes (e.g. privileged correspondence for a client handover).
- **Investigation restore:** restore a point in time into an isolated sandbox for forensics, without affecting production.
- **Restore drills:** quarterly in staging and after major upgrades. Results are recorded as an ops report with measured RPO/RTO.

### 24.5 Recovery capabilities (beyond backup)

| Scenario | Capability |
|---|---|
| Bad import / bad rule / runaway integration | **Compensate by correlation ID:** generate reversing events for everything in a batch (with preview). The original remains in the ledger |
| Mistaken void/transition | Ledgered reversal with reason, if the workflow allows. Issued correspondence is never reversed, only superseded or withdrawn by new correspondence |
| "What did the system show on date X?" | **Time-travel reads** (`asof=seq` or timestamp) in TUI, API, and reports. Important for disputes: what was known, sent, and received when |
| Corrupted or wrong projection | Rebuild one projection or module from the ledger without downtime (shadow rebuild) |
| Missed webhooks / downstream outage | **Replay** by `seq` or time range per subscription. DLQ redrive |
| Missing or corrupt objects | Reconciliation job compares referenced hashes with the store. Restore from object versions or the replica |
| Tampering suspicion | Hash-chain verification tool over the database and the archive. Reports the first divergence |
| Compromised credentials/integration | Kill switch, token revocation, secret rotation. Audit report of all actions by that principal. Compensate by actor + time range |
| Misbehaving AI agent | Same as above, plus budget caps. All agent writes are attributable and reversible by correlation |
| Clock engine outage | Response clocks are computed from ledgered start events and calendars, so they are recalculated on recovery. Missed warnings are sent as a catch-up digest |

### 24.6 Run-time operations

- **Observability:** OpenTelemetry traces across API → service → ledger → projector → webhook. Key SLOs:
  - API latency,
  - projection lag (`seq` behind head),
  - webhook delivery success and latency,
  - job queue age,
  - upload processing time,
  - model conversion time,
  - clock-warning delivery.
- **Alerting** on projection lag, outbox backlog, DLQ growth, hash-chain verification failures, backup age, and certificate expiry.
- **Runbooks** (kept in the repo, versioned) for every alert and recovery scenario. Agents can read them through the dev/ops MCP (§25).
- **Capacity:** partition the events table by scope and time. Archive closed projects to bundles with read-only reattachment. Size object storage by file class (models and photos dominate).
- **Security operations:** dependency and container scanning in CI, periodic penetration tests, egress allow-lists for webhooks (SSRF protection), malware scanning of uploads, and audit log export to the customer's SIEM.
- **Data lifecycle:** retention classes per record type and file slot, legal hold per project, domain, or record, crypto-shredding for personal data, and project close-out (bundle export, then read-only, then archive).

---

## 25. Agent-based development

The codebase is designed so AI coding agents can build and maintain most of it safely, with humans owning specs, schema decisions, and reviews. Development agents are distinct from runtime agents (§18.12), but they share tooling.

### 25.1 Spec-driven flow

```
Module spec (markdown, template)                 ← human-owned
  → LinkML schema fragment (classes, slots, psets, file slots, events, workflows)
  → codegen (Pydantic, SQL, JSON Schema, OpenAPI, TS types, MCP tools, TUI/PWA form metadata,
             event catalog, docs)                ← deterministic, checked in, CI drift check
  → hand-written: command handlers, projections, workflow guards, reports, screens
  → tests: generated contract tests + hand-written behaviour tests
```

Because most surfaces are generated from LinkML, adding a record type, or a new correspondence domain, is mainly a schema and workflow change. Agents are reliable at schema edits, and the generators guarantee consistency across the API, MCP, TUI, PWA, webhooks, and docs.

### 25.2 Repository affordances for agents

- **Instruction files:** `AGENTS.md` (plus `CLAUDE.md`) at the root and in each module, covering conventions, the architecture map, "never do" rules, how to run tests, and where generated code lives.
- **Task runner:** one documented interface (`just`/`make`): `gen`, `test`, `test-parity`, `test-tui`, `lint`, `rebuild-projections`, `seed`, `serve`.
- **Scaffolding CLI:**
  - `tl new module <name>`
  - `tl new record-type <module>.<Class>`
  - `tl new correspondence-domain <name>`
  - `tl new action|rule|enricher|connector|report`
  - `tl new extractor`

  Each produces a schema stub, handlers, tests, and docs placeholders.
- **Templates:** module spec template, ADR (architecture decision record) template, runbook template.
- **Synthetic project generator:** realistic, deterministic seed data (lines, isos, welds, tags, documents, correspondence threads, models) at configurable scale, for tests, demos, and performance work.
- **Golden datasets** for document extraction, correspondence triage, and model mapping, with expected outputs.

### 25.3 Dev/ops MCP server

A development MCP server (local and CI only, never pointed at production data) exposes:

- **Resources:** schema graph, event catalog, module specs, ADRs, runbooks, sample payloads, TUI screen snapshots, test reports.
- **Tools:** run tests (filtered), run codegen and report drift, query the dev database, replay or rebuild projections, generate seed data, render a TUI screen to an SVG snapshot, send test webhooks, validate a LinkML change (`linkml diff` + impact report), simulate workflows and clocks against a calendar, run the extraction evaluation suite.

Coding agents can then inspect the running system, not just the source.

### 25.4 Test and quality gates

| Gate | Purpose |
|---|---|
| Codegen drift check | Generated artefacts match the schema |
| Schema change classification | Breaking changes blocked without upcaster + version bump + human approval |
| SQLite/Postgres parity suite | Same behaviour on both adapters |
| Projection determinism | Property-based tests: replay(events) twice gives identical projections; projections after shadow rebuild equal live ones |
| Workflow and clock tests | Every domain workflow is simulated across all transitions. Response clocks are tested against calendars, holidays, and stop/restart rules |
| Contract tests | API, webhooks (payloads valid against the catalog), MCP tools, inbound mappings |
| TUI snapshot tests | Textual snapshot testing of key screens and key bindings |
| Sync tests | Convergence, idempotency, and no-lost-writes property tests across replicas; partition injection (§22.8) |
| Web workspace tests | Playwright tests of the model workspace page |
| Security | Dependency/container scanning, SSRF tests on webhook targets, permission tests (ABAC matrix generated from roles, including confidentiality classes) |
| Evaluation suites | Extraction accuracy and AI enricher precision against golden sets; regressions block release |

### 25.5 Agent roles and human gates

| Agent role | Does | Human gate |
|---|---|---|
| Schema steward | Drafts LinkML from module specs, runs impact analysis | Required for all schema merges |
| Module builder | Handlers, projections, screens, reports from schema + spec | Code review |
| Test writer | Behaviour, contract, and snapshot tests; seed scenarios | Spot review |
| Integration builder | Connectors, inbound mappings, actions against partner API docs | Review + staging test against sandbox |
| Reviewer | Second-agent review of PRs against conventions and spec (separate context from the author) | Final human approval |
| Ops agent | Reads runbooks and alerts, proposes remediation (replay, rebuild, compensate) | Human approval for any write in staging/production |

Guardrails:

- Agents work in isolated worktrees and ephemeral environments with no production credentials.
- Migrations, security-sensitive code, permission model changes, and contractual workflow/clock definitions always need a named human reviewer.
- Agent-authored commits are labelled for traceability.

---

## 26. Updated cross-reference summary (Part II additions)

| New record/object | Links to |
|---|---|
| `WebhookSubscription`, `InboundEndpoint`, `ActionDefinition`, `Rule`, `Enricher`, `AgentIdentity`, `IntegrationApp` | Owner (person), scopes (company/project/module/domain/record), each other; all deliveries and invocations |
| `ActionInvocation` | Target records, invoker, resulting events/records/files |
| `EnrichmentValue` | Target record + property, input record versions and files, enricher |
| `ActivityPost` | Author, mentioned records (via `#key`), codes, topics, people, attachments, derived records (post → deficiency) |
| `ThreadMessage` | Thread's record, author, mentions, linked records, dispatched records (`dispatched from`) |
| `Link`, `ExternalRef` | Both ends, relation, pin, source, verification (§7) |
| `SyncConflict`, `Replica` | Commands, base context, affected records, resolver (§22) |
| `SettingDefinition`, `Setting.Changed` | Scope (company/project/user), actor, reason (§30) |
| `TypeRegistration` | Package location and hash, owner, adopting projects, instances (§31) |
| `EventCard` | Underlying ledger events and their subjects |
| `File` / slot | Record, uploader, processing jobs, derived renditions |
| `Correspondence` + domain items | See §9 M10: thread, domain item, response clocks, contract clauses, affected records, cost codes, documents, viewpoints |
| `ModelDocument` / `ModelRevision` / `ModelObject` | Tags, lines, spools, equipment, scaffolds (mapped); viewpoints → RFIs/NCRs/punch/correspondence/posts; federated views; IDS spec document |
| `ProjectBundle` (ops) | Project, schema versions, ledger range, object manifest |
| `SchemaPackage`, `Waiver`, `Crosswalk` (Part III) | Owner, approvers, dependent packages, adopting projects; waived records/properties; mapped value lists |
| `ScheduleSnapshot`, `ScheduleActivity` | Source XER revision, previous snapshot, baseline; IWPs/CWPs/systems/correspondence via stable Activity ID |
| `ModelSlice` | Source model revision(s), defining record (IWP, test package, subsystem, area) |
| Spatial context (`xref_*`, `ctx_*`) | Model document/revision, objects, viewpoint; inherited via declared link paths |
| `SimulationRun`, `LegacyLoad` | Scenario/manifest, sandbox tenant or project, ledger correlation IDs, reconciliation reports |

---

# Part III — Schemas, data platform, implementation, settings, extensibility

## 27. Schema and semantic model management

Schemas will change often: weekly at company level, daily on busy projects. This section describes how change stays safe:

- data stays valid and traceable,
- integrations and reports keep working,
- meaning (semantics) is never silently altered,
- no event is ever rewritten.

### 27.1 Principles

1. **One modelling language.** Everything is LinkML: core classes, module classes, psets, code lists, correspondence domains, workflows' required data, document schemas, integration mappings. Company and project packages are LinkML too (a constrained subset authored through the workbench or as YAML).
2. **Build-time core, runtime extensions.** Core and module schemas change with platform releases (code, CI, review). Company and project packages change at runtime through the schema registry: no deploy, no downtime.
3. **Events are immutable; interpretation evolves.** Every event records the `effective_schema_hash` it was validated against. Later schema versions change how data is *read* (aliases, crosswalks, upcasters), never what was *written*.
4. **Meaning is append-only.** A property's definition can be clarified but never changed in meaning. A different meaning is a new property with a new IRI.
5. **Every change is classified and impact-assessed before it is published.**

### 27.2 Schema layers and ownership

| Layer | Content | Owner | Authored in | Change cadence | Released by |
|---|---|---|---|---|---|
| Core | Envelope, ledger, links, files, workflow, feed, integration classes | Platform team | Repo (LinkML) | Per platform release | CI + release |
| Modules | Record types, events, commands, typed references, default workflows | Platform/module teams | Repo (LinkML) | Per release | CI + release |
| Company packages | Standard psets, code lists, enforcement, correspondence domains, document schemas (`x_schema.json`), IDS specs, numbering patterns, slice rules | Company schema stewards | Schema registry (workbench or YAML, optional git sync) | Weekly-ish | Registry publish workflow |
| Project packages | Extensions of standard psets, project psets, project value lists, crosswalks, tightened rules | Project data manager | Schema registry | Any time | Registry publish (lighter approval) |
| Mappings | Source → standard mappings (IFC, P6 XER, legacy, inbound webhooks), external vocabulary mappings | Stewards, integration owners | Registry | As needed | Registry publish |
| Extension types | Additional record types as packages in a directory or object store (§31) | Companies, projects, partners | Type packages | Any time | Registry publish |

### 27.3 Effective schema

For each project, the platform composes an **effective schema**:

```
core (release N)
  + modules (release N)
  + company packages (pinned versions adopted by the project)
  + project packages (pinned versions)
  + mappings
  ──────────────────────────────────────────────────────────────
  = effective schema for project P123  (content hash #a91f…3c)
     → compiled artefacts (cached by hash):
        JSON Schema per record type (runtime validation)
        form/grid metadata (TUI, PWA, web)
        current-state DDL diff + project views (§5.4)
        lake table schemas (§28)
        OpenAPI fragment  (GET /schema/effective/{project})
        MCP tool input schemas (tools/list_changed notification)
        JSON-LD context + SHACL shapes (semantic exports)
        event catalog/docs
```

- Psets compile into LinkML classes (e.g. `ValveData`, plus `ValveData_P123_x` for the project's custom section), referenced from each record class's `psets` slot. Platform annotations carry the extra rules: `tl:enforcement`, `tl:value_list_policy`, `tl:materialize`, `tl:history`, `tl:confidentiality`, `tl:spatial_context_via`, `tl:file_slots`.
- Compilation uses linkml-runtime (`SchemaView`) to merge packages, then generates JSON Schema for fast runtime validation plus custom validators for cross-record rules (e.g. "required link before transition").
- The effective schema is **hot-reloaded**. Clients receive a `Schema.EffectiveChanged` event and refresh forms and metadata without a restart. Records being edited keep validating against the schema they were opened with until saved, then are re-checked.
- Company-level records (master data) use the company effective schema (core + modules + company packages).

### 27.4 Schema registry and package lifecycle

A `SchemaPackage` is itself a ledgered record: name, namespace, semver, owner, dependencies, content (LinkML YAML), changelog, classification report, impact report, approvals.

```
Draft → In review → Approved → Published → Deprecated → Retired
          │  (stewards; discipline leads for required/locked changes;
          │   legal/commercial leads for correspondence-domain clocks)
          └─ changes requested → Draft
```

- **Publishing** emits `SchemaPackage.Published` (feed card + webhooks) and makes the version available to adopt.
- **Adoption** is per project: additive versions can auto-adopt (company policy); constraining or renaming versions need the project data manager to adopt after reviewing their project-specific impact report. Projects pin versions; drift from the latest is visible in the conformance dashboard.
- **Git sync** (optional): packages export to and import from a git repo as YAML, so stewards who prefer pull requests can use them. The registry stays the system of record.
- **Test on sample:** before review, a draft is validated against a sample (or all) of the existing records it touches, producing the "newly non-conformant" count.

### 27.5 Change classification and handling

`linkml diff` plus platform rules classify every change:

| Change | Class | Handling |
|---|---|---|
| Add optional property, pset, value, code | Additive | Auto-adoptable; forms and columns appear |
| Add required property, tighten range/pattern, close a value list | Constraining | Grace period; existing records flagged non-conformant (not rewritten); conformance report; waivers possible |
| Rename property or value | Renaming | `aliases` + `deprecated_element_has_exact_replacement` in LinkML; read-time mapping in projections, queries, saved views, reports, and webhook payloads; old path accepted with a deprecation warning until retirement |
| Promote project custom property to company standard | Promotion | Alias from `x.<name>` (per project) to the standard path; values carried by mapping, no event rewrite |
| Change type or unit dimension | Breaking | Not allowed in place. New property; optional **conversion job** emits ledgered, correlated correction events (reversible, §24.5); old property deprecated |
| Remove property | Deprecation | Hidden from forms; values remain queryable in history and lake; retired after the notice period |
| Change meaning | Forbidden | Create a new property with a new IRI |

Additional rules:
- Every current-state row carries `conformance` (`ok`, `warning`, `nonconformant`, `waived`) evaluated against the project's **current** effective schema, alongside the `effective_schema_hash` it was written under.
- Integration deprecation notice: minimum notice period (company setting, e.g. 8 weeks) before an aliased path is retired; owners of subscriptions, mappings, reports, and agents that use it are notified automatically.

### 27.6 Semantic integrity

| Requirement | Rule |
|---|---|
| Identity | Every class, slot, pset, property, and value has a stable IRI in its owner's namespace, e.g. `https://tl.example.com/schema/co/acme/engineering/valve_data/size_in`. Versioned IRIs are also available for exact citation |
| Definition | Description mandatory; examples recommended; label + optional alternative labels/abbreviations (linked to the Standards registry mnemonics) |
| Units | Quantities declare a unit (UCUM codes; QUDT quantity kind). Unit dimension can never change |
| External alignment | `exact_mappings`, `close_mappings`, `broad_mappings`, `related_mappings` to external vocabularies: CFIHOS, IFC property sets, ISO 15926 reference data, P6 fields, client standards. Required for `materialize: true` properties where a counterpart exists (company policy) |
| Value lists | Values are LinkML enums with meanings (`meaning:` IRIs); project values crosswalk to company values |
| Lint | Naming conventions, missing definitions or units, orphan code lists, unmapped source properties, conflicting mappings |
| Duplicate detection | Lexical + embedding similarity across all company and project properties; the workbench warns when a "new" property resembles an existing one (e.g. `seat_leak_cls` vs `seat_leakage`) |
| Graph validation | SHACL shapes generated from the effective schema validate semantic exports; failures appear in the data health report |
| Provenance | Every package version records author, approvers, and rationale; the semantic export includes PROV links to the package version that defined each property |

### 27.7 Propagation on publish/adopt

| Target | What happens |
|---|---|
| Current-state tables (§5.4) | DDL diff: new promoted columns, regenerated project views; type changes trigger a shadow rebuild of that type only |
| Conformance | Re-evaluated asynchronously for affected records; dashboard updates |
| TUI / PWA / web forms | Runtime refresh via `Schema.EffectiveChanged` |
| API | Effective OpenAPI regenerated; endpoints accept and validate new fields immediately |
| MCP | Tool input schemas regenerated; `tools/list_changed` sent to connected agents |
| Webhooks & inbound mappings | Paths checked against the new schema; aliased paths auto-mapped; broken mappings flagged and owners notified before adoption completes |
| Saved views, reports, rules, overlays | Path references validated and aliased; broken ones listed in the impact report |
| Lakehouse (§28) | Table schemas evolved (add columns; renames via view aliases); history preserved |
| Semantic exports | New JSON-LD context version and SHACL shapes |
| Docs & event catalog | Regenerated and versioned |

### 27.8 Tooling

- **Schema workbench** (TUI, later web; sketch in §10.6): package tree, pset/property editor, enforcement and policy toggles, value lists and crosswalks, diff, lint, impact, test on sample, review and publish.
- **`tl schema` CLI:** `lint`, `diff`, `classify`, `impact --project P123`, `test --sample 1000`, `publish`, `adopt`, `crosswalk`, `promote`, `export-git` / `import-git`.
- **MCP tools:** `get_effective_schema`, `explain_property`, `find_similar_properties`, `propose_schema_change` (creates a Draft package with impact report), `propose_mapping` (for source/legacy properties). Agents can draft, but humans review and publish.
- **Conformance dashboard:** by project, pset, property: conformance rates, waivers (with expiry), adoption lag, unmapped source properties.

### 27.9 Governance

| Role | Responsibility |
|---|---|
| Platform schema owners | Core/module schemas, platform annotations, generators |
| Company schema stewards (per discipline) | Company packages, enforcement levels, value lists, mappings, approvals |
| Project data manager | Project packages, adoption, waivers requests, crosswalks |
| Integration owners | Respond to deprecation notices; keep mappings current |

Cadence: company packages on a predictable release train (e.g. weekly), with emergency fixes allowed; project packages any time. A quarterly review promotes widely used project properties to standards and retires unused ones.

---

## 28. Data platform: DuckDB / DuckLake lakehouse

### 28.1 Principle

The lakehouse is the **analytics copy** of the system: never a source of truth, always rebuildable from the ledger archive and current-state tables. It uses **DuckLake**: Parquet data files in object storage, with table metadata (snapshots, schema versions, file lists) in a SQL catalog database, queried by DuckDB. This matches the platform's dev/prod pattern exactly.

| | Dev | Prod |
|---|---|---|
| Catalog | SQLite or DuckDB file | PostgreSQL (separate database from the transactional one) |
| Data files | MinIO bucket `lake/` | S3-compatible bucket `lake/` (per-company prefixes, KMS keys) |
| Compute | DuckDB embedded in workers, CLI, notebooks | DuckDB in report workers, sync jobs, MCP lake tool, analyst notebooks; BI tools via DuckDB connectors |

```
Ledger / ledger archive ──┐
Current-state tables ─────┼─► tl lake sync (incremental by seq) ─► DuckLake
XER snapshots, imports ───┤        bronze → silver → gold            (Parquet + catalog)
Legacy extracts ──────────┘                                            │
                                    reports · dashboards · BI · notebooks · MCP lake_query
```

Note: DuckLake is a young format. Its version and maturity are confirmed at Phase 1 start and the extension version is pinned. Everything above the DuckLake boundary is plain Parquet + SQL, so the lake can be rebuilt into another table format if needed.

### 28.2 Layers

| Layer | Tables | Source |
|---|---|---|
| **Bronze** (raw, append-only) | `events` (partitioned by company/project/date); `xer_<table>` per snapshot (all XER tables verbatim); `legacy_<system>_<table>`; `inbound_payloads`; file metadata | Ledger archive segments (already Parquet, §24.3), import jobs |
| **Silver** (conformed) | `cur_<class>` and `hist_<class>` per entity type (same generated schema as §5.4, plus promoted pset columns); `links`; `pset_values` (long form); `schedule_activity` by snapshot; `cost_snapshot`; `clocks` | Current-state tables + event replay |
| **Gold** (marts) | Progress by cost code and period; weld/NDE statistics; IWP readiness history; completions burn-down; schedule trend (float erosion, slip by activity across XER snapshots); commercial exposure; data conformance; cross-project benchmarks | SQL models over silver (versioned in repo, tested) |

### 28.3 Sync and consistency

- `tl lake sync` runs incrementally (default every 5 minutes; on demand for reports). It reads events after the last synced `seq`, updates silver, and commits as one DuckLake snapshot.
- Every lake snapshot records the **ledger `seq` range** it covers. Reports built on the lake state "data as of seq 48,211,933 (09:15)" and are reproducible with DuckLake time travel.
- Schema evolution follows the effective schema diff (§27.7): new columns are added, and renames are exposed through views.
- Compaction, snapshot expiry, and partition pruning are scheduled. Retention follows the data lifecycle rules (§24.6).
- Full rebuild = replay the ledger archive into a new lake. It is tested in restore drills.

### 28.4 Uses

- Heavy reports and dashboards (moved off the transactional database).
- Schedule analytics from XER snapshot history (P6 never needs to be queried directly).
- Cross-project benchmarking in a company catalog (weld rates, NDE reject rates, RFI turnaround, punch closure).
- Data science and AI: agents get a read-only `lake_query` MCP tool (SQL with row limits, allowed catalogs only, logged).
- Data sharing: a filtered per-project DuckLake can be handed to a client or partner (their own catalog + Parquet), instead of bespoke exports.
- Simulation and legacy bootstrap profiling (§29).

### 28.5 Security

- Separate catalogs per company; sandbox/simulated tenants in their own catalogs.
- Restricted confidentiality classes (legal, privileged, some commercial) are excluded by default or held in a separate restricted catalog.
- Personal data columns are masked or pseudonymised in silver/gold.
- Users query through the service (report engine, MCP tool, governed notebooks) rather than with raw bucket credentials; data engineers get scoped credentials.

---

## 29. Implementation plan and bootstrapping

### 29.1 Approach

- **Vertical slices.** Each increment delivers schema → generated surfaces → handlers → TUI screen → API/MCP → tests, end to end.
- **Spec-driven, agent-assisted** (§25). Humans own specs, schema decisions, and reviews; agents do most of the generation, tests, and scaffolding.
- **Dogfood the open interfaces.** Bootstrap loaders and the simulator use only the public API and MCP, so they test the same surfaces customers and agents use.
- **Every phase exit is demonstrated on a simulated project**, then on real data when a pilot is available.
- Two-week increments; a demo and a restore drill at the end of every phase.

### 29.2 Workstreams

| Workstream | Scope |
|---|---|
| Platform core | Ledger, current-state generator, links, numbering, workflow, files, auth, change feed |
| Schema & semantics | LinkML core, generators, layered psets, schema registry, effective schema compiler, workbench, conformance |
| TUI | Shell, grid, record view, palette, link picker, forms, feed, workbench, fast-entry screens, model context panel |
| Web viewer | Web model workspace page, slices, snapshot renderer, pairing (PWAs deferred) |
| Offline & sync | Replica protocol, merge policies, conflict UI |
| Integration | API, MCP server/client, webhooks, inbound, actions, rules, enrichment |
| Data platform | Current-state tables, DuckLake sync, gold marts, reports |
| Modules | M1–M12 per roadmap |
| Ops | Backup, archive, restore, upgrade tooling, observability |
| Bootstrap & simulation | Loaders, legacy mapping, simulator, scenarios, seed data |

### 29.3 Phase 0 increments

| Inc | Delivers | Demo |
|---|---|---|
| 1 | Monorepo, LinkML core, codegen pipeline, SQLite ledger, current-state generator, `tl` CLI | Create a generic record from CLI; see `cur_` row and event |
| 2 | Layered psets, schema registry v0 (YAML packages), effective schema compiler, conformance; TUI shell + grid + record view | Company pset with enforcement + project extension; edit values in TUI |
| 3 | Links, numbering, workflow engine; palette, link picker, trace | Link records by key; transition with guard |
| 4 | Files/uploads on MinIO; REST API; MCP read tools; change feed; live TUI | Two TUIs + an agent watching the same record |
| 5 | Postgres adapter + parity suite; outbox + webhooks; event catalog | Signed webhook to a test receiver; replay |
| 6 | Feed core + hashtags; MCP propose/write tools; **simulator v0** | Simulated crew posts and records via MCP |
| 7 | Backup, ledger archive, restore; **DuckLake sync v0** (bronze events, silver current state) | Restore drill; DuckDB query over the lake |
| 8 | Hardening, docs, Phase 0 exit | Phase 0 exit criteria (§16) |

Later phases follow the roadmap (§16), each broken into increments the same way.

### 29.4 Bootstrapping a company and project

Bootstrap steps are idempotent, ledgered **bootstrap jobs** driven by a manifest (`bootstrap.yaml`), runnable from the CLI, TUI, API, or MCP. Each step validates, dry-runs, and loads with `source=bootstrap:<step>`.

```
 1  Tenant, IdP, roles                         7  Project from template; adopt packages
 2  Standards registry (codes, mnemonics,      8  Contracts, clauses, correspondence domains
    numbering patterns, units)                 9  Reference loads: cost codes, XER snapshot(s),
 3  Company schema packages (psets, domains)      document register, engineering data, models
 4  Item library, catalogs                    10  Transactional history (legacy) or simulation
 5  People, crews, parties, equipment fleet   11  Reconcile, conformance review, waivers
 6  Calibration register                      12  Go-live / sandbox open
```

Local developer bootstrap: `tl dev up` starts MinIO, creates the SQLite ledger and DuckLake catalog, loads a reference company, and optionally starts a simulation.

### 29.5 Simulated projects (MCP-driven)

A simulator generates realistic project activity by acting **through the suite's public MCP server and API**, as if it were a project team.

```
scenario.yaml ─► Simulation orchestrator (its own MCP server: sim_create, sim_advance,
                 │                         sim_inject, sim_status, sim_assert)
                 ├─ deterministic actors  (bulk mechanics: welds/day, receipts, ITRs, uploads)
                 └─ LLM role agents       (judgement & text: RFIs, posts, letters, NCRs, triage)
                          │  each an AgentIdentity with a real role and permissions
                          ▼
                 Suite MCP / API / inbound webhooks  ─► ledger (effective_at = simulated time)
                          │
                 ground-truth log (what the scenario intended) ─► sim_assert / evaluation
```

**Scenario contents:** reference project (or generated from a template: units, areas, systems, lines/isos/welds, tags, documents, a generated XER with activities and logic, cost codes, sample IFC models and slices), team composition, production rates, quality rates (NDE reject %, punch density), calendars, and injected events.

**Roles:**

| Role agent | Typical actions |
|---|---|
| Document controller | Registers revisions, transmittals, derived documents |
| Planner | Uploads XER updates (with slips), builds IWPs, clears constraints |
| Materials coordinator | Receipts with MTRs, reservations, toolcrib issues |
| Welding foreman / crew | Fit-up and weld records, photos, feed posts |
| NDE contractor (external) | RT/UT results via inbound webhook, with rejects |
| QC inspector | Inspections, deficiencies, NCRs, calibration events |
| Scaffold supervisor | Requests, erect/inspect/dismantle |
| Commercial manager | Early warnings and change notices from RFI impacts; clocks |
| Client representative (external) | RFI answers, witness sign-offs via guest links, letters |
| Completions engineer | ITRs, punch walkdowns, certificates |

**Fault injection:** late materials, failed calibration (with impact cascade), design revision superseding pinned isos, RFI storms, inbound webhook outages, bad imports (to test compensation), duplicated messages (idempotency), offline mobile conflicts.

**Time compression:** `sim_advance(days=…)` runs a working day in seconds; a 12-month project can run in about an hour for load and report testing.

**Determinism and cost:** seeded randomness; LLM outputs cached per seed so a scenario replays identically; LLM agents handle only a configurable share of text-heavy actions (templates cover the rest); per-run token and cost budgets.

**Isolation:** simulations run in sandbox tenants with `simulated = true` on every event, excluded from company benchmarks and real feeds.

**Uses:**
- demos and training (sandbox with a live, moving project),
- load and performance tests,
- workflow and response-clock validation,
- report correctness against ground truth,
- evaluating AI enrichers and triage agents,
- UX testing of the TUI and model workspace with realistic data,
- offline replica testing with partition injection,
- rehearsing upgrades and restores.

```yaml
# scenario excerpt
scenario: north-unit-expansion-12m
seed: 4711
template: refinery-piping-medium
start: 2026-11-02
duration_days: 365
rates:
  welds_per_welder_day: {dist: normal, mean: 2.4, sd: 0.6}
  rt_reject_rate: 0.025
  punch_per_subsystem: {A: 4, B: 22, C: 60}
agents:
  llm_share: 0.15
  budget_usd: 40
inject:
  - day: 45   event: material_late        {item: "6in CL300 WN flange", days: 21}
  - day: 80   event: calibration_failed   {instrument: TW-0012}
  - day: 120  event: design_revision      {isos: 35, rev_bump: true}
  - day: 150  event: inbound_outage       {app: acme-nde, hours: 18}
assert:
  - report: weld_progress   tolerance: 0.5%
  - clocks: no_missed_warnings
```

### 29.6 Legacy loading

| Source | Typical content | Loader |
|---|---|---|
| Spreadsheets | Weld logs, punch lists, registers, line lists, tag lists | XLSX/CSV extractor with column profiling |
| Legacy databases | Completions systems, QC databases (Access/SQL Server/Oracle) | DB extractor (read-only) → bronze |
| Document management exports | Metadata CSV/XML + files | Register + bulk upload with manifest |
| P6 | XER history (multiple data dates) | XER pipeline, one snapshot per file |
| Cost system | Cost code structure, period snapshots | Cost snapshot import |
| Email archives | PST/EML/MSG | Correspondence ingest + triage |
| Models | IFC files | M12 pipeline |

Pipeline:

```
Extract → bronze (raw, untouched, in the lake)
  → profile (DuckDB: columns, value distributions, keys, duplicates, pattern matches)
  → map (declarative, LinkML-validated mappings; crosswalks for value lists;
         key normalisation via Standards registry patterns)   ← AI-assisted proposals via MCP
  → dry-run validate against the effective schema (lenient conformance, time-limited waivers)
  → load via public commands: source=legacy:<system>, external_ids kept,
    unmapped columns kept in src.legacy-<system>.* psets, effective_at = original dates
  → reconcile (counts, sums, sampled record comparison, open-item lists)
  → delta loads during parallel run → cutover → legacy read-only
```

**Load modes:**
- **Snapshot:** current state only, as `Imported` events. Fast; history stays in the source system and bronze.
- **Milestone history:** current state plus key dated milestones (e.g. weld date, NDE date, certificate date) as backdated events.
- **Full replay:** reconstruct histories where the source has an audit trail.

Milestone history is the recommended default.

**Rules:**
- Nothing in the source is lost. Unmapped data stays in source psets and bronze, ready for later mapping.
- Every loaded record links to its source row (`external_ids` + bronze reference). Reconciliation reports are stored as documents.
- Loads are correlated batches, so a bad load can be compensated (§24.5) and re-run.

### 29.7 Mixed mode

A **training sandbox** can be seeded from a real project's reference data (standards, psets, tags, documents, schedule, models; no transactional or restricted data), then driven by the simulator. People train on their real project's structure without touching live data.

### 29.8 Definition of done (per module)

- LinkML schema reviewed; generated artefacts current; current-state tables and lake tables generated.
- Workflows, required psets, file slots, and spatial context paths declared.
- TUI screens, generated forms, API, MCP tools, and webhooks working from the same schema.
- Merge policies (§22.4), settings keys (§30), and expected links (§7.1) declared.
- Base reports in place on current state and lake.
- Simulation scenario actors added for the module; scenario assertions pass.
- Legacy mapping template provided.
- Parity, contract, snapshot, permission, and restore tests green.

### 29.9 Testing approaches, including mirroring a traditional project management suite

| Approach | What it proves |
|---|---|
| Automated gates (§25.4) | Code, contracts, schemas, permissions, sync properties |
| Simulation (§29.5) | Behaviour at scale, workflows, clocks, faults, offline merges |
| **Load or mirror a traditional PM suite** | Realism, and parity with how projects are run today |
| Pilot | Adoption and value |

**Backtest by loading.** Take a completed project from the incumbent stack (P6 XER history, cost snapshots, weld/QC/completions databases, document register, correspondence). Load it through the legacy pipeline (§29.6) in effective-time order into a sandbox. Then compare Throughline's reports at chosen dates with the reports the project actually issued: progress, NDE statistics, punch, IWP counts, RFI turnaround. Differences expose mapping gaps, rules-of-credit differences, or bugs.

**Shadow by mirroring.** For an active project still run in the traditional suite, create a **mirror project** fed continuously from it:
- scheduled XER uploads,
- spreadsheet and database extracts or connectors, applied as commands with `source=mirror:<system>`,
- at daily or faster cadence.

Mirror projects are read-only for normal users (`project.mode = mirror`). A test group can trial Throughline-only capabilities on top (links, readiness, model context, threads) without affecting the incumbent.

**Reconciliation.** An automated daily diff compares incumbent reports and exports with Throughline current state (counts, quantities, statuses, dates) using tolerance rules. The trend of reconciliation deltas is the acceptance criterion for cutover.

**Round trip (later).** Push selected Throughline activity back into the traditional suite (progress quantities to the cost system; IWP-linked activity status to P6 through XER/XML import) to validate outbound integrations before relying on them.

Mirror and backtest data are flagged and isolated like simulations. They are also used to calibrate simulation rates (R14).

---

## 30. Settings (about:config style)

Every tunable behaviour is a **named, typed, documented setting**, layered from platform default to company to project (and to user, for personal UI preferences). Settings are visible and editable in one about:config-style screen, and every change is ledgered.

### 30.1 Setting definitions

Settings are defined in LinkML (`SettingDefinition`) by the platform, modules, and extension types:

| Attribute | Notes |
|---|---|
| `key` | Dotted and namespaced, e.g. `awp.iwp.ready_lead_weeks` |
| `type` | bool, int, decimal, string, enum, list, duration, size, date, json |
| `default` | Platform default |
| `description`, `docs` | Shown in the screen |
| `scopes` | Which of platform / company / project / user may set it |
| `lockable` | Whether a company can lock it for its projects |
| `validation` | Range, enum, regex, or a company-defined bound for projects (e.g. projects may set ≤ 50) |
| `effect` | `live`, `reindex`, `rebuild`, or `restart` |
| `sensitivity` | `normal` or `secret` (stored in the vault, shown masked) |
| `risk` | `normal`, `advanced`, or `dangerous` |
| `since`, `deprecated` | Version information |

### 30.2 Layers and resolution

```
platform default → company → project → user (UI keys only)
```

- The **effective value** shows its origin. Values set at the current scope are marked ● (like about:config's "modified").
- A company can **lock** a key, so projects cannot override it, or constrain the range projects may use.
- **Templates:** project templates carry settings; company baselines can be diffed against any project.

### 30.3 Change control

- Every change is a `Setting.Changed` event: old value, new value, actor, reason (required for `advanced` and `dangerous` keys), and effective time.
- **Scheduled changes** take effect at a future time (e.g. switch the conformance mode at go-live).
- **Dangerous keys** need explicit confirmation ("I accept the risk"), and can require an approval workflow. Examples: hash-chain verification interval, sync merge defaults, retention.
- Changes apply live through the change feed. Keys needing a reindex or rebuild show a pending banner until done.
- Full per-key history, with revert.

### 30.4 Interfaces

- **TUI** `about:config` screen (`Ctrl+,`; sketch in §10.6): filter, toggle booleans with `Enter`, edit, reset to inherited, lock, history, diff against another project.
- **CLI:** `tl config get | set | reset | lock | diff | export | import`.
- **API:** `/settings` endpoints and `Setting.Changed` webhooks.
- **MCP:** `get_settings` (read), `propose_setting_change` (draft for human approval).
- **Export/import** as YAML for templates and reviews.

### 30.5 Representative keys

| Key | Default | Notes |
|---|---|---|
| `awp.iwp.ready_lead_weeks` | 4 | COAA lead time; drives constraint need-by dates |
| `awp.backlog.target_weeks` | 4 | Target Ready-IWP backlog per foreman |
| `awp.iwp.size_hours` | [60, 850] | Warning bounds (COAA example range) |
| `awp.release.signoff_roles` | [workface_planner, superintendent] | |
| `awp.rules_of_credit.set` | company standard | |
| `links.key_detection.enabled` | true | |
| `links.suggestions.min_confidence` | 0.7 | |
| `links.external.check_interval` | 24h | |
| `links.notify_on_inbound` | watchers | |
| `threads.enabled` | false | Project switch |
| `threads.enabled_types` | [] | |
| `threads.domains.legal.enabled` | false | Company-locked by default |
| `feed.reactions.enabled` | true | |
| `feed.signal_tags` | [safety, hold, decision, urgent, fyi] | |
| `schema.conformance.mode` | strict_with_waivers | |
| `schema.adoption.auto_additive` | true | |
| `schema.deprecation.notice_weeks` | 8 | |
| `sync.enabled` | false | Offline replicas for the project |
| `sync.max_offline_days` | 7 | |
| `numbering.offline.mode` | provisional | or `reserved_ranges` |
| `models.slice.mobile_max_mb` | 50 | |
| `xref.context.inherit` | true | Spatial context through links |
| `uploads.exif.strip_gps` | true | |
| `webhooks.retry.max_hours` | 24 | |
| `webhooks.egress.allowlist` | [] | Dangerous to widen |
| `lake.sync.interval` | 5m | |
| `ai.agents.default_mode` | propose | Typically company-locked |
| `project.mode` | live | `live`, `sandbox`, `simulated`, `mirror` |
| `ui.tui.keymap` | default | User scope; or `vim` |
| `ui.tui.graphics` | auto | User scope; Kitty/iTerm2/Sixel/off |

---

## 31. Extension record types (directory / object-store backed)

New record types can be added quickly by companies, projects, partners, or agents, **without a platform release or a database schema change**. Their definitions and their instance content live as files in a directory (dev, git) or an object-store prefix (prod). Throughline stores only **metadata**: the registration, the envelope, indexed properties, links, workflow state, and content pointers with hashes.

### 31.1 Type packages

```
types/                          directory (dev / git) or object-store prefix (prod)
  co.acme/
    LiftPlan/
      1.2.0/
        type.yaml               LinkML class (is_a tl:ExtensionRecord): slots, psets, file slots,
                                index fields (tl:index), xref fields, merge policies
        workflow.yaml           optional state machine
        form.yaml               optional layout hints for generated forms
        settings.yaml           optional setting definitions (§30)
        templates/              optional print/report templates
        examples/               sample instances (tests, simulation)
        README.md
        type.lock               content hashes of all files (signed on publish)
```

- **Registration:** the registry discovers packages (directory watch, bucket events, or `tl types sync`), validates them (LinkML lint, compile into the effective schema, examples validate), and records a `TypeRegistration` holding metadata only: namespace, name, version, location URI, content hash, owner, status, storage mode, index fields.
- The package files stay where they are; compiled artefacts are cached by hash.
- Publishing and adoption follow the schema package lifecycle (§27.4).

### 31.2 Storage modes for instances

| Mode | Instance body | What Throughline stores |
|---|---|---|
| `managed` | In the ledger, like core types | Everything |
| `object-backed` | A content-addressed JSON/YAML document (plus attachments) in the object store: `records/<type>/<id>/<hash>.json` | Ledger events with metadata only: envelope (id, key, type, scope, status, title), index fields, links, workflow transitions, indexed pset values, and a pointer `{uri, hash, size, schema_hash}` |
| `directory-backed` | Files in a watched directory (dev, or a synced share / git repo) | As object-backed; file changes are detected, validated, and registered as new versions |

**Write paths (object-backed):**
- **Through Throughline** (TUI/API/MCP): the body is validated, stored as an object, then a metadata event referencing its hash is appended.
- **Directly by external writers:** a document is put at a signed prefix (`incoming/<type>/…`). The watcher validates it and either registers a new version (`Record.Registered`, `source=objectstore:<prefix>`) or quarantines it with a validation report.
- **Updates** are new document versions (new hash). Old versions are immutable, and the ledger keeps the version chain.

### 31.3 What extension types get for free

Because they share the envelope, extension types get:
- numbering,
- cross-references (§7),
- threads,
- feed cards,
- webhooks,
- workflow,
- permissions,
- settings,
- a current-state table (index fields + pointer),
- search (index fields + extracted text),
- generic API (`/records/{type}`) and MCP tools,
- generic TUI grid and forms (from LinkML + `form.yaml`),
- model context (with xref fields),
- offline sync (merge policies from `type.yaml`),
- lakehouse tables: index fields in silver; full bodies loaded to bronze with DuckDB `read_json` over the prefix,
- simulation actors (from `examples/`).

### 31.4 Rules

- Bodies are never trusted without validation. Hashes are verified on read, and mismatches are quarantined.
- **Index fields are the query contract.** Other body fields are visible in the record view but not filterable server-side until promoted (re-index job).
- **Promotion path:** object-backed → managed, by a migration job that imports bodies as events and keeps hashes as provenance.
- Per-type permissions; per-integration write prefixes with signed writes; restricted confidentiality classes cannot be object-backed in shared prefixes.
- Typical uses: lift plans, permits-to-work, daily site reports, toolbox talks, survey records, weather logs, equipment telemetry summaries, client-specific forms.

---

## Appendix A — Change log

| Version | Changes |
|---|---|
| v0.1 | Initial brief: principles, scoping, ledger, LinkML semantic model and psets, linking, modules M1–M11, Textual TUI, APIs and MCP, base reporting, extensibility, tech stack, NFRs, roadmap, risks |
| v0.2 | Correspondence restructured as a shared core with domain layers (RFI, Quality, Commercial, Legal, HSE, Interface, Document control, General). Part II: open integration architecture and webhooks (§18), LinkML integration and activity model (§19), uploads (§20), activity stream (§21), mobile (§22), M12 Models with xeokit (§23), operations (§24), agent-based development (§25) |
| v0.3 | Layered psets and schema lifecycle (§6.3, §27); materialized current state (§5.4); P6 via XER snapshots (M11); model workspace, slices under 50 MB, slide-out model context (§23); DuckLake lakehouse (§28); implementation plan with simulation and legacy bootstrapping (§29); TUI sketches (§10.6) |
| v0.4 | Renamed **Throughline**. Gaps and pain points (§0). M3 rewritten for GC field work packaging on the COAA workface planning model. Cross-referencing as a first-class operation: create, maintain, surface, follow, reference tray, external references, link lifecycle (§7). Activity stream without replies; optional record threads with dispatch (§21). PWAs deferred; offline tolerance through replica sync and merge (§22). about:config settings (§30). Extension record types (§31). Testing by loading or mirroring a traditional PM suite (§29.9). Change log moved to this appendix |

**Sources consulted for the COAA model (v0.4):**
- [COAA — AWP/WFP 101 workshop (2015)](https://coaa.ab.ca/wp-content/uploads/2022/10/BPC-2015-PRS-05-2015-v1-Workshop-AWP-WFP-101.pdf)
- [COAA — Advanced Work Packaging summary (2016)](https://coaa.ab.ca/wp-content/uploads/2022/09/COP-AWP-PBP-01-2016-v1-Advanced-Work-Packaging-Summary.pdf)
- [CII — AWP acronyms and definitions](https://www.construction-institute.org/CII/media/Documents/AWP-Acronyms-Definitions.pdf)
