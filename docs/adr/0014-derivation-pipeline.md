# ADR-0014 — The derivation pipeline: records, job queue, validation, publication and compensation

Status: accepted 2026-10-17 by the orchestrator under ADR-0008 decision 6 (proposed by the P1-I3 workstream A supervisor)
Date: 2026-10-17
Deciders: P1-I3 workstream A supervisor (proposal); accepted by the orchestrator
Brief sections: §9 M1 (derivation pipeline), §9 M2 (bulk import, provenance), §20 (files), §24.5 (compensation), §11.3 and §18.12 (agents propose)

## Context
P1-I3 turns the §9 M1 pipeline into code around a frozen extractor contract (`tl_core/derivation/types.py`, ADR-0008 decision 8):
a source file is read by a plugin, the result is checked against a versioned `DocumentSchema`, and a valid `DerivedDocument` is
published into target records. FANOUT decisions D3 to D7 fix the shape (an operational claim queue, publication through module
commands, access by target type, the security-review list). They leave open where the records live, how rows are stored, how a
mapping is declared, what "compensate" can undo, and how agents take part. This ADR settles those.

## Decision

### 1. Records live in the documents module
`documents.DocumentSchema`, `documents.DerivedDocument` and `documents.ProcessingJob` are record types of the documents module
(ADR-0010: one `cur_core_record` row and one typed row each). The code is the sub-package `tl_mod_documents.derivation`. The
module's `ModuleSpec` lists the three types; each decides its own generic-command allow-list (section 7). Keys:
| Type | Key | Workflow |
|---|---|---|
| `DocumentSchema` | `<code>@<semver>` (`instrument-index@1.0.0`) | none; `is_active` is a column |
| `DerivedDocument` | `<document number>@<revision code>/<schema code>` (`ISD-001@A/instrument-index`) | `documents.derived-document`: Pending, Processing, Invalid, Valid, Published, Void |
| `ProcessingJob` | `JOB-<record id>` | none; `state` is a column moved by job events |

A source revision has at most one derived document per schema code. Each pass of an extractor over a file is a *content revision*
(`cur_documents_derived_content`, one row per pass): a person who fixes a CSV and runs again adds revision 2; revision 1, its report
and its rows stay. The diff of two passes, and of a derived document against the one of the previous source revision
(`previous_derived_id`), reads those rows.

### 2. Rows and reports are files, not payloads
Extracted rows (columns, rows, profiles, problems as canonical JSON) are stored through the file service in the slot `extracted`
of the derived document; the validation report in the slot `report`. The events carry counts, the SHA-256 of the file and its file
id, never the rows. A person attaches input only in the slot `content` (CSV or XLSX); the slots `extracted` and `report` are written
by the module. To allow that, `FileService.register_upload`, `complete_upload` and `attach_file` gain a **Python-only keyword-only
`by_module`** that skips the record type's generic-command allow-list and guard for the call (the pattern of ADR-0010 second
addendum, item 2). It is not a field of any command model, so no client can set it; the HTTP upload routes never pass it.
Everything else the service checks (slot, accepted types, size limit, scan, hash) still runs. An extractor reads only a file whose
status is `available`; a quarantined source makes the job fail with a retry (`source_not_available`).

### 3. The queue
`job_queue` is an operational table (`schema/core/jobs.yaml`): job id, kind, scope, state (queued, running, done, failed,
cancelled), attempt, `max_attempts`, `run_after`, `lease_owner`, `lease_until`. It is not a projection: no event writes it, a rebuild
never clears it, the archive, lake and webhooks never read it. `tl_core.jobs` holds the types and the portable SQL; the one
statement that differs by database, the claim, is a method of `SqliteJobQueue` and `PostgresJobQueue` in `tl_adapters.queue`
(Postgres: `SELECT ... FOR UPDATE SKIP LOCKED`; SQLite: a plain select, because its write transaction already holds the single
writer lock).
- **Claim** (one write transaction): pick the best claimable row (`queued` with `run_after <= now`, or `running` with
  `lease_until <= now`), set `running`, `attempt + 1`, `lease_owner`, `lease_until = now + lease` (default 300 s), and append
  `ProcessingJob.Started` in the same transaction. A running row whose lease expired and whose `attempt` has reached
  `max_attempts` is failed for good instead (`ProcessingJob.Failed`, `final`, code `lease_expired`).
- **Run** happens outside any transaction: read the file from the object store, call the extractor, validate. The extractor is a
  pure function (contract); a crash here loses nothing, because the lease expires and the job is claimed again.
- **Complete** (one write transaction): a compare-and-set on `(job_id, attempt, lease_owner, state = 'running')`. If it matches, the
  results are recorded and `ProcessingJob.Succeeded` is appended; if the row is already `done` with that attempt, the call is a
  no-op (idempotent); if the attempt or owner differ (the lease was taken over), the late worker writes nothing. A job therefore
  completes at most once, and a job killed mid-run is retried (with a growing delay, 30 s times the attempt) or failed, never
  lost.
- `reconcile` re-enqueues jobs whose record says queued or running but that have no queue row (a restore from the archive).
Job state changes are ledger events, so they are attributable and replayable; the queue only decides who runs next.

### 4. Validation
A `DocumentSchema` holds a JSON Schema (draft 2020-12) for one row. Cells arrive as text (contract); validation reads each cell
with the type its property declares (`integer`, `number`, `boolean`, `string` with the `date` format), treats an empty cell as
absent, validates the typed row object, and reports per row and field. The report (counts, then up to 1 000 issues in order)
is a JSON document in the slot `report`. A duplicate value in the schema's `key_column` is an error. `valid` means zero errors;
warnings (fields not in the schema) do not block.

### 5. Publication
- **Mapping is data.** A schema may carry a `PublishMapping` (LinkML class in `schema/modules/documents/publish_mapping.yaml`; the
  generated JSON Schema `json_schema/documents.publish-mapping.schema.json` checks every mapping at registration, and the code
  checks the rest: every mapped column is a property of the JSON Schema, the key column is mapped to the key). Columns map to
  `number`, `class`, `service` and `psets.<pset>.<property>` for tags, to `number`, `title`, `doc_type`, `discipline`,
  `originator` and `description` for documents, with optional value translations.
- **Only module commands write.** Tags are written by the engineering import (`plan_import`, `apply_plan`: `RecordTag` and the
  pset commands); documents by `RegisterDocument`. Never `CreateRecord`, so number patterns, code lists, limits and allow-lists hold.
- **One correlated import.** The whole publication is one unit of work with one correlation id and the source
  `import:derived-<derived id>`; any refusal rolls all of it back. `DerivedDocument.Published` records the correlation id, the
  content revision, the count and the hash of the mapping and of the rows.
- **Create only.** A publication creates records. A row whose key already exists is not written: the preview says `exists`, and
  whether its values differ; the apply skips it only when the caller states `skip_existing`. Changes to existing tags stay with
  `tl tag import --apply`. This keeps compensation exact (section 6).
- **Provenance.** Every record the publication creates gets the pset value `provenance.source = "src.doc.<number>@<revision>"` and
  `provenance.derived_document = <derived key>`, and a link `derived_from` from the record to the derived document
  (`link_source = import`, written with `by_module`). The pset `provenance` is defined by the company package (the sample
  `co.acme.engineering` gains it); a publication refuses with that message when the effective schema lacks it.
- **Access (D6).** `PublishDerivedTags` is an `admin` command (as `tl tag import --apply`); `PublishDerivedDocuments` is a
  `controller` command (as `tl doc import --apply`); `CompensatePublication` is `admin`. Which of the two a schema's rows need is
  the schema's `target_kind`; calling the other command for it is refused. Starting an extraction, validating, previewing a
  publication and cancelling a queued job are open to any signed-in person. Registering and retiring a document schema is `admin`
  (it decides what an import may contain; it is registry data like the standards).

### 6. Compensation (brief §24.5)
`CompensatePublication` reads the events of the recorded import correlation id and appends reversing events under a correlation id
of its own, with a preview first (`preview_compensation` lists every record and whether it can be reversed). For each created record:
a tag moves to `Deleted` through the workflow (`by_module`) and its provenance link is retracted; a document is voided by
`VoidDocument`. A record that can no longer be reversed (a tag that was superseded, a document that has revisions) is listed and the
whole compensation is refused: all or nothing. The original events stay. The derived document returns to `Valid` and
`DerivedDocument.PublicationCompensated` names both correlation ids. A key is used once (ADR-0010 addendum 4), so the compensated
keys cannot be published again; the preview of a later publication says so per row.

### 7. Allow-lists and guards (ADR-0010 addenda)
| Type | Generic commands allowed | Guard |
|---|---|---|
| `DocumentSchema` | `AddLink`, `SuggestLink` and the link-life commands | none |
| `DerivedDocument` | the same, plus `AttachFile` | `AttachFile`: only in `Pending`, `Invalid`, `Valid`, and only the slot `content` (never `extracted` or `report`; those are `by_module`) |
| `ProcessingJob` | none | none |
`SetPsetValues`, `UpdateRecord`, `TransitionWorkflow` and `VoidRecord` are allowed on none of them: state moves only through the
module's commands. The derived document's workflow transitions are made by `by_module` calls.

### 8. Agents
An agent never writes (B15). `start_extraction` and `propose_import` are **proposals**. The module declares them
(`ModuleSpec.proposable`; `proposable_tools()` merges them into `PROPOSABLE_TOOLS`): `start_extraction` proposes `StartExtraction`,
and `propose_import` is the two tools `propose_import_tags` (`PublishDerivedTags`) and `propose_import_documents`
(`PublishDerivedDocuments`), which the MCP tool chooses between by the schema's `target_kind`. `validate_against_schema`
reads a stored derived document and returns the report it would produce; it writes nothing. A person accepts a proposal through
the existing review queue; **accepting a publication proposal needs the access the command needs** (admin for tags, controller for
documents): the API route and the CLI check it on the accepting person, not on the agent. The check is in core
(`proposals.accept` takes a `holds(level)` callback from the client; the level of each command comes from the module's declaration
or `CORE_ACCESS`; a command nobody declared an access for is never accepted, so the check fails closed). A person without the
access gets `ProposalAccessError` (HTTP 403 `proposal_access`), and the proposal stays pending; rejecting needs no command access.
This tightens the review queue for every command, not only these: it applies the access the direct command route already enforces. A direct "staging" mode for agents (run an
extraction without a person) would change the permission model; it is not built.

### 9. Defaults
Lease 300 s; `max_attempts` 3; retry delay 30 s times the attempt; at most 100 issues per field kind and 1 000 in a report;
`StartExtraction` refuses while the derived document is `Processing`; a queued job may be cancelled by any signed-in person.

## Consequences
- Contracts changed: `FileService` (`by_module`, Python-only); `PROPOSABLE_TOOLS` and the proposal command table (core); the
  default projector registry gains `JobQueueTables`; `tl_schema.generators.jsonschema_gen` also emits the mapping schema.
  No 03 §7 interface changes.
- Schema: `schema/core/jobs.yaml`, `schema/modules/documents/{document_schema,derived_document,processing_job,publish_mapping,
  derivation_events}.yaml`, fixtures (workflow, file slots, the `provenance` pset in the sample company package, a mapping).
  All additive; no migration of existing data.
- Security review (D7): the job claim and lease, the proposal-accept access check, the file service keyword, the new commands'
  access levels and allow-lists, the upload slot, and compensation.
- Extractors run in a child process with a wall-clock limit (60 s) and a memory limit; the parent never imports plugin code
  that has not passed the registry's checks (`ExtractorLoadError` names the exception type only, never its text).
- Known limits: no updates through publication in Phase 1 (create only, no key reuse; a changed row is imported with
  `tl tag import --apply`); publication cannot change existing records; a compensated key is not reusable; queue rows are not in the archive
  (reconcile restores them); one derived document per source revision and schema code.

## Alternatives considered
| Option | Why not |
|---|---|
| A new module `derivation` | The records point at documents, revisions and renditions; a second module would need the documents tables and a dependency in the other direction |
| Rows as event payloads | 20 000 rows of up to 200 columns would make events megabytes long, and every projector and the lake would carry them |
| Rows as a typed table per schema | Schemas are data and versioned; a table per version is a migration per schema |
| Queue in the ledger only (jobs as events, claim by projection) | A claim is a compare-and-set that must be atomic with its lease; events are append-only and a projection lags |
| Publication through generic `CreateRecord` | It bypasses the module rules, limits and allow-lists (ADR-0010) |
| Publication that also updates existing records | Reversing an update needs the old values, which `Pset.ValuesSet` does not carry; the exactness of compensation matters more |
| Agents run extraction directly | B15; a direct staging mode is a permission-model change for the orchestrator |
