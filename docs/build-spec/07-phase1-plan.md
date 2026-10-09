# Build spec 07 — Phase 1 plan: Information backbone

Brief: §16 Phase 1. Modules M1, M2, M10 (Technical/RFI, Document control, Commercial, General), M11; schema workbench;
lake marts; legacy loaders; threads; actions/rules/inbound/enrichment. Eight increments. Ticket IDs `P1-I<n>-T<nn>`.

**Phase exit (§16):** receive a PDF schedule or list, derive validated CSV/XLSX, publish into target records with
full traceability; the chain is visible in the feed and pushed to subscribers.

**Human gates this phase:** every `schema/modules/**` merge (schema owner); clock and workflow definitions for the
Commercial domain (commercial lead); inbound signing and confidentiality filters (security). See `04-gates.md` §2.

**Standing rule:** each module increment ticket order is schema → generated surfaces → projectors → handlers →
API/MCP → TUI → reports → simulator actors → legacy mapping template (§29.8).

---

## Increment 1 — M2 Standards registry, numbering patterns, Tag/TagClass

**Goal:** the company "holding zone" (§6.4): mnemonics, code lists with `value_list_policy` and crosswalks, numbering
patterns that validate and parse keys, units; `Tag` and `TagClass` records whose class drives mandatory psets.
**Demo:** load the `acme` standards fixture; `tl tag create 47-FV-1001 --class ControlValve` parses segments
(`47`, `FV`, `1001`), rejects `47-XX-1`, and shows missing mandatory `valve_data` properties as non-conformant.
**Fanout:** no (single supervisor). **Supervisor builds:** T02 (registry LinkML), T05 (pattern engine integration with I3 numbering), T08 (class → required psets binding).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Standards fixture `schema/fixtures/co.acme.standards@1.0.0`: disciplines, areas, doc types, NDE methods, weld types, crafts, UOMs, mnemonics | H | — |
| T02 | LinkML `schema/modules/engineering.yaml`: `Standard`, `CodeList`, `CodeValue`, `Mnemonic`, `NumberingPattern`, `Tag`, `TagClass` | S | T01 |
| T03 | Standards registry records + projectors (`cur_engineering_standard`, `cur_engineering_codevalue`) | H | T02 |
| T04 | Code-list service: resolve value, crosswalk project→company, `value_list_policy` enforcement hooks into conformance | H | T03 |
| T05 | Numbering patterns as registry entries: register, validate, parse to segments; wire Phase 0 allocator to patterns | S | T03 |
| T06 | `Tag` commands: create/rename/split/merge with `supersedes` links; `cur_engineering_tag` with parsed segment columns | H | T05 |
| T07 | `TagClass` record: required psets list, applicable ITR templates (ref only) | H | T02 |
| T08 | Class binding: effective schema adds class-driven required psets; conformance reflects it | S | T07 |
| T09 | Tag register TUI grid + record view with segments and class; `tl tag` CLI | H | T06 |
| T10 | Bulk tag import from CSV with diff preview (new/changed/removed, pset changes) via ledgered import batch | H | T06 |
| T11 | Reports: tag register by class/status, missing mandatory psets, pattern violations | H | T09 |
| T12 | Simulator: tag-list actor; legacy mapping template for tag lists; demo; report | H | T10 |

---

## Increment 2 — M1 Document control core

**Goal:** Document → Revision → Rendition with configurable revision schemes, one current revision per status class,
pinned/floating links with stale-pin alerts and re-pin, transmittals and review cycles.
**Demo:** register `ISO-1234` rev A (IFR) with a PDF rendition; link a tag to it pinned; issue rev B (IFC); the tag's
link shows `stale`; re-pin shows the revision diff summary; a transmittal lists rev B.
**Fanout:** no. **Supervisor builds:** T02, T05 (revision scheme engine + current-revision invariant), T07 (pin/stale resolver).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Revision scheme fixtures (`A/B/C`, `0/1/2`, `P1/C1`) + document type code list | H | — |
| T02 | LinkML `documents.yaml`: `Document`, `Revision`, `Rendition`, `Transmittal`, `ReviewCycle`, file slots (`native`, `pdf`, `markup`, `signed`) | S | T01 |
| T03 | Projectors `cur_documents_*` with `current_revision_*` denormalised columns | H | T02 |
| T04 | Commands: `RegisterDocument`, `CreateRevision`, `AttachRendition`, `IssueRevision`, `SupersedeRevision`, `VoidDocument` | H | T03 |
| T05 | Revision scheme engine: next code, ordering, one-current-per-status-class invariant | S | T04 |
| T06 | Document workflow YAML (Draft → Registered → In Review → Issued → Superseded/Void) + guards | H | T05 |
| T07 | Pin/stale resolver: new revision → pinned links `stale`, watchers notified; `RepinLink` with diff summary | S | T04 |
| T08 | Transmittal commands + workflow; review cycle with reviewer outcomes | H | T06 |
| T09 | TUI: document register grid, document/revision record views, transmittal composer, re-pin dialog | H | T08 |
| T10 | API/MCP: document resources, `get_document_revisions`, `repin` | H | T08 |
| T11 | Reports: register, revision history, overdue reviews, transmittal log, stale pinned revisions | H | T09 |
| T12 | Simulator document-controller actor; DMS export legacy mapping template; demo; report | H | T11 |

---

## Increment 3 — M1 derivation pipeline and schema-validated derived documents

**Goal:** the pipeline in §9 M1: register → extract (plugin) → validate against `DocumentSchema` → publish into target
records as a ledgered, correlated import with provenance back to the source revision.
**Demo:** upload a PDF instrument index; run the table extractor; validation fails on one row; fix the CSV; re-run;
publish → 40 tags created, each with `src.doc.ISD-001@A` provenance and a `derived from` link to the derived document.
**Fanout (orchestrator):** WS-A pipeline and schemas; WS-B extractors. Contract: `Extractor` plugin Protocol and
`ExtractionResult` shape (orchestrator writes before fanout).

WS-A pipeline

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML: `DocumentSchema` (JSON Schema + version + sample), `DerivedDocument`, `ProcessingJob`; derived workflow (Pending → Processing → Invalid/Valid → Published) | S | — |
| T02 | Job runner v1: DB-backed queue adapter (SQLite table; Postgres `SKIP LOCKED`), worker loop, job events | S | — |
| T03 | Extractor registry (entry points) + `Extractor` Protocol + job wiring | H | T02 |
| T04 | Validation step: run JSON Schema over extracted rows; row/field-level report document | H | T01 |
| T05 | Publish step: map validated rows → commands (declarative mapping, LinkML-validated); correlated import batch; compensate by correlation (§24.5) | S | T04 |
| T06 | Derived-document diff vs prior derived revision | H | T05 |
| T07 | TUI: job monitor, validation report viewer, publish preview/approve | H | T05 |
| T08 | API/MCP: `start_extraction`, `validate_against_schema`, `propose_import` (staged, human approval) | H | T05 |

WS-B extractors

| ID | Title | Tier | Depends |
|---|---|---|---|
| T09 | CSV/XLSX extractor with column profiling and header mapping | H | contract |
| T10 | PDF table extractor (pdfplumber; Camelot optional) with per-source profiles | H | contract |
| T11 | OCR extractor (Tesseract if present, else skip with marker) | H | contract |
| T12 | Golden dataset: 3 sample PDFs/CSVs with expected rows; evaluation test | H | T09, T10 |
| T13 | Document schemas fixtures: instrument index, line list, equipment list (`x_schema.json`) | H | — |

Merge order: WS-A T01–T03 → WS-B → WS-A T04–T08. Demo and report by WS-A supervisor.

---

## Increment 4 — M11 cost snapshots and P6 XER snapshots

**Goal:** `CostCode` mirror with measure matrix and period snapshots; XER upload → bronze tables → validated
`ScheduleSnapshot` → typed activities → compare with previous → publish; links by stable Activity ID.
**Demo:** upload two XER files (data dates one week apart); compare shows date shifts and float erosion; a record
linked to `A1230` resolves to the current snapshot and as-of the earlier one.
**Fanout:** no. **Supervisor builds:** T03 (XER parser), T06 (snapshot compare).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML `cost.yaml`: `CostCode` (measure matrix), `CostSnapshot`; `schedule.yaml`: `Schedule`, `ScheduleSnapshot`, `ScheduleActivity`, WBS/relationship/calendar/code/UDF | S | — |
| T02 | Cost snapshot import (CSV) as correlated batch; `cur_cost_costcode` with as-of columns | H | T01 |
| T03 | XER parser: all tables to bronze (Parquet via lake bronze loader), typed `TASK`, `PROJWBS`, `TASKPRED`, `CALENDAR`, codes, UDFs | S | T01 |
| T04 | XER `DocumentSchema` validation (required tables/columns, version, single vs multi-project) | H | T03 |
| T05 | Snapshot build: immutable per-snapshot activity tables; `Schedule.SnapshotPublished` | H | T04 |
| T06 | Snapshot compare: added/removed, date shifts, float erosion, logic changes, % complete, critical path | S | T05 |
| T07 | Activity-ID link resolution: `schedule_activity_ref` resolves to current snapshot; as-of resolution; orphan flagging in link health | H | T05 |
| T08 | Look-ahead query (3–6 weeks) from current snapshot (readiness join lands in Phase 2) | H | T05 |
| T09 | TUI: schedule list, snapshot compare view, activity record; `tl xer upload` | H | T06 |
| T10 | Reports: quantities by cost code vs budget, records without cost code, IWP-vs-activity stub | H | T07 |
| T11 | Lake: `xer_*` bronze, `schedule_activity` silver by snapshot, float-trend mart | H | T05 |
| T12 | Simulator planner actor (generates XER with slips); demo; report | H | T11 |

---

## Increment 5 — M10 correspondence core, clock engine, General and Document-control domains

**Goal:** correspondence core (§9 M10): items, threads, parties, response clocks, contract clauses, register with
confidentiality filtering; domain definitions as LinkML; General and Document-control domains (transmittals become
domain items).
**Demo:** receive a letter by upload; triage proposes domain General; issue a reply with a 14-calendar-day clock on the
project calendar; the clocks screen shows it; the transmittal from I2 appears in the master register.
**Fanout:** no. **Supervisor builds:** T02, T04 (clock engine), T06 (confidentiality filters, human gate).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | Project calendar fixture (working days, holidays) + party fixtures | H | — |
| T02 | LinkML `correspondence.yaml`: `Correspondence`, `CorrespondenceThread`, `ResponseClock`, `ContractClause`, `Party`, `ContactRole`, `CorrespondenceDomain` | S | — |
| T03 | Projectors `cur_correspondence_*`, `cur_clocks` | H | T02 |
| T04 | Clock engine: start triggers, calendars, warnings, stop/restart, recompute from ledger; `ResponseClock.*` events | S | T03 |
| T05 | Domain definition compiler: subtypes, workflow ref, numbering, required psets, default clocks, routing, feed and integration policy | S | T02 |
| T06 | Confidentiality classes and filters on every query path (register, feed, API, MCP, exports) | S | T03 |
| T07 | Core commands: receive, triage (propose domain/subtype/refs/clocks), issue (template → PDF rendition → send stub), reclassify before issue | H | T05 |
| T08 | Threading from headers/subject/body keys; `responds to` / `superseded by` links | H | T07 |
| T09 | General domain + Document-control domain definitions (transmittal mapped to domain item) | H | T05 |
| T10 | TUI: master register, item view, triage inbox, clocks screen (sketch 7) | H | T07 |
| T11 | Email-in ingest (per-project address) parsing EML into items + attachments to slots | H | T07 |
| T12 | Reports: master register, responses due/overdue, running clocks; demo; report | H | T10 |

---

## Increment 6 — Technical/RFI and Commercial domains, escalation paths

**Goal:** RFI as a Technical-domain item feeding AWP constraints (stub until Phase 2); Commercial domain with time bars
and value fields; RFI → Commercial escalation rule; evidence trail view.
**Demo:** raise an RFI pinned to ISO-1234 rev B; client answers with `cost_impact = yes`; the rule proposes a linked
Early Warning with a 14-day time bar; the evidence view assembles the chain as of the answer date.
**Fanout:** no. **Supervisor builds:** T03 (Commercial workflow and clocks, human gate), T06 (evidence trail time-travel query).

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML: `RFI`, `TechnicalQuery`, `DeviationRequest` (Technical domain); Technical workflow YAML | S | — |
| T02 | RFI commands and screens: question, proposed solution, required-by, impact flags, answering revision; constraint hook stub | H | T01 |
| T03 | Commercial domain: subtypes, workflow, clocks with time bars, value and schedule-impact psets, numbering | S | — |
| T04 | Commercial commands and register; export to cost system as pending/approved changes (CSV) | H | T03 |
| T05 | Escalation rule RFI → Commercial (`derived from` link, new clock) using the rules engine stub (full engine I7) | H | T02, T04 |
| T06 | Evidence trail query: linked chain as-of dates (time-travel reads over ledger) | S | T04 |
| T07 | TUI: RFI register and record, commercial register, evidence view | H | T06 |
| T08 | Feed policy per domain: full / minimal / none cards | H | T05 |
| T09 | Reports: RFI log with response times and impact flags, commercial register with values | H | T07 |
| T10 | Simulator: client representative answers RFIs; commercial manager raises notices; demo; report | H | T09 |

---

## Increment 7 — Integration layer and record threads

**Goal:** actions registry, rules engine (when/if/then with dry-run and loop protection), inbound webhook endpoints
with JSONata mappings, enrichment framework with first AI document-extraction enricher in `propose` mode, record
threads with dispatch.
**Demo:** an inbound POST maps to `RecordNDEResult`-style command on generic records; a rule posts to the feed on
`#safety`; an enricher proposes a document classification; a thread `/raise rfi` creates a linked RFI.
**Fanout (orchestrator):** WS-A actions/rules/inbound/enrichment; WS-B threads. Contract: `Rule` and `ActionDefinition`
LinkML (§19.2) and the dispatch-command parser interface.

WS-A integration

| ID | Title | Tier | Depends |
|---|---|---|---|
| T01 | LinkML: `ActionDefinition`, `ActionInvocation`, `Rule`, `InboundEndpoint`, `Enricher`, `EnrichmentValue`, `IntegrationApp` | S | — |
| T02 | Actions registry + executors `job`, `webhook`; lifecycle events; TUI context-menu exposure | H | T01 |
| T03 | Rules engine: filter match, condition in query language, actions; causation depth limit; dry-run against history | S | T02 |
| T04 | Inbound endpoints: signature verification (HMAC/JWT), JSONata mapping to commands, key resolution, dry-run, error queue | S (verification) + H (mapping runtime) | T01 |
| T05 | Enrichment API: namespaced psets, proposed links, provenance, acceptance policy, review queue screen | H | T01 |
| T06 | First enricher: AI document classification via MCP client (propose mode); evaluation against golden set | H | T05 |
| T07 | Integration registry screen: apps, subscriptions, endpoints, rules, owners, kill switch | H | T04 |
| T08 | Contract tests for inbound mappings and action results | H | T04 |

WS-B threads

| ID | Title | Tier | Depends |
|---|---|---|---|
| T09 | Thread stream per record, events, participants, settings keys (§21.5) | H | — |
| T10 | Dispatch command parser (`/assign /dispatch /raise /link /status /hold /release /due /notify /remind /summarise`) → existing commands with preview | S | T09 |
| T11 | TUI thread tab (sketch 13), composer with completion, dispatch result cards | H | T10 |
| T12 | Webhooks `Thread.MessagePosted/Dispatched`; MCP `read_thread`, `post_thread_message`, `propose_dispatch` | H | T10 |

Merge order: WS-A T01–T03 → WS-B → WS-A T04–T08.

---

## Increment 8 — Schema workbench, legacy loaders, lake marts, reports, Phase 1 exit

**Goal:** `SchemaPackage` lifecycle with review/publish and adoption, impact reports, workbench TUI (sketch 8); legacy
loader framework with first loads; document and XER marts; phase-exit demo.
**Fanout (orchestrator):** WS-A workbench/registry; WS-B loaders and lake. Contract: package lifecycle events.

| WS | ID | Title | Tier | Depends |
|---|---|---|---|---|
| A | T01 | `SchemaPackage` record, lifecycle workflow, `SchemaPackage.Published`, adoption per project with pins | S | — |
| A | T02 | `linkml diff` classification + platform rules → classification report | S | T01 |
| A | T03 | Impact report: records, current-state columns, views, mappings, reports, MCP schemas affected | H | T02 |
| A | T04 | Workbench TUI: package tree, property editor, lint, diff, impact, test on sample, review/publish | H | T03 |
| A | T05 | Conformance dashboard; `Waiver` record; `tl schema` subcommands complete | H | T03 |
| B | T06 | Loader framework: extract → bronze → profile (DuckDB) → map → dry-run → load → reconcile | S | — |
| B | T07 | Loaders: document register CSV, tag list XLSX, line list XLSX; reconciliation report document | H | T06 |
| B | T08 | Lake marts: documents, XER history; reports moved to lake where heavy | H | — |
| B | T09 | Phase-exit demo script: PDF → derived → published → feed → webhook receiver | H | all |
| — | T10 | Phase report, risk register update, ADRs (orchestrator) | O | T09 |
