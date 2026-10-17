# Module spec: derivation pipeline (documents module, P1-I3)

Status: accepted (built in P1-I3). Brief sections: §16 (derive validated CSV/XLSX and publish), §24.5 (bulk import and
compensation), §9 M1. Decisions: [ADR-0014](../../adr/0014-derivation-pipeline.md) (this pipeline), ADR-0010 (module storage),
ADR-0008 decision 8 (PDF and OCR content extraction is stubbed), ADR-0013 (the document controller). Operations:
[derivation-pipeline](../../runbooks/derivation-pipeline.md).

## Purpose
A derived document is a table of data read from one revision of a controlled document (a PDF index, or a CSV or XLSX a
person attached), checked against a document schema, and, when valid and approved, published as tags or documents. Every
step is a ledger event, so a publication can be traced to its source and rolled back.

```
register schema ─▶ open derived document ─▶ start extraction ─▶ [job: extract] ─▶ validate ─▶ Valid
                                                   ▲                               │ Invalid: fix the file, run again
                                                   └───────────────────────────────┘
Valid ─▶ preview ─▶ publish (admin: tags, controller: documents) ─▶ Published ─▶ compensate (admin) ─▶ Valid
```

## Records
| Type | Key | Table | Workflow |
|---|---|---|---|
| `documents.DocumentSchema` | `<code>@<semver>` | `cur_documents_document_schema` | none (`is_active`) |
| `documents.DerivedDocument` | `<number>@<revision>/<schema code>` | `cur_documents_derived_document`, `cur_documents_derived_content` (one row per pass) | `documents.derived_document`: Pending, Processing, Invalid, Valid, Published, Void |
| `documents.ProcessingJob` | `JOB-<n>` | `cur_documents_processing_job` | none (the state is a column) |

Every record is also a row of `cur_core_record`. `job_queue` is operational (not a projection, not in the archive):
`reconcile_orphans` queues again the jobs the ledger holds that the queue lost (`tl derive worker --requeue`).

## Where the rows are
The rows an extractor read and the report of their validation are **files** in the file service, in the slots `extracted`
and `report` of the derived document. They are never event payloads. The module writes them (`by_module`, Python only); a
person cannot upload to those slots. A person attaches the data to the slot `content` (CSV or XLSX). Each pass adds a
**content revision**: fixing a CSV and running again keeps the earlier pass, its report and its rows. The diff between
two passes is a query.

## Events
`DocumentSchema.Defined`, `DocumentSchema.Retired`; `DerivedDocument.Defined`, `.ContentRecorded`, `.Validated`,
`.Published`, `.PublicationCompensated`; `ProcessingJob.Defined`, `.Started`, `.Succeeded`, `.Failed`, `.Cancelled`. Payloads:
`schema/modules/documents/derivation_events.yaml` and the generated event catalog.

## Document schemas
A schema is a JSON Schema (draft 2020-12) for one row, a `key_column`, a sample, and optionally a **publish mapping**:
data that says which column becomes the tag number, class, service, pset values (tags) or document number, title, type
(documents). Versions are semver and only go up; a retired version stays readable. A project sees its own schemas and the
company's. Registering and retiring are admin acts. The mapping is checked when the schema is registered: every mapped
column is a property of the row schema and the key column is mapped to the key.

## Validation
Cells arrive as text (or empty). A cell is read as the property declares (`integer`, `number`, `boolean`, `string`
with `format`), then the row is checked. The report lists file-level problems (`missing_column`, `unknown_column`,
`no_rows`, `duplicate_key`), each extractor problem, and each row or field error with its row and column. At most 1 000
issues are listed; the counts are exact.

## Publication (create only)
`PublishDerivedTags` (admin) and `PublishDerivedDocuments` (controller) run one unit of work with one correlation id and
the source `import:derived-<id>`. They write through module commands only (`RecordTag` and the pset commands;
`RegisterDocument`), so numbering, code lists, limits and allow-lists hold. Each created record carries the pset value
`provenance.source = src.doc.<number>@<revision>`, `provenance.derived_document`, and a `derived_from` link to the derived
document. A row whose key exists is not written: the preview says `exists` and `differs`, and `skip_existing` publishes the
rest. **Phase 1 limit: a publication creates records; changes to existing tags go through `tl tag import --apply`.**
`CompensatePublication` (admin) reverses exactly the records and links the `Published` event recorded (`record_ids`, `link_ids`),
never "the events with this correlation id", and appends reversing events under a correlation id of its own, all or nothing; a record that can no longer be reversed (superseded, has revisions) is listed and stops it. The original
events stay. A compensated key is not reusable (ADR-0010).

## Who can do what
| Act | Access |
|---|---|
| Read schemas, derived documents, jobs, rows, reports, diffs, previews | any signed-in person; agents too |
| Open a derived document, start an extraction, validate again, cancel a queued job | any signed-in person |
| Void a derived document | document controller (or admin) |
| Register or retire a schema | admin |
| Publish into tags, compensate | admin |
| Publish into documents | document controller (or admin) |
| An agent | proposes only: `start_extraction`, `propose_import_tags`, `propose_import_documents` |

**Accepting a proposal needs the access of the proposed command** (ADR-0014 section 8): a user cannot accept an agent's
publish proposal into tags; the API answers 403 `proposal_access` and the proposal stays pending.

## Surfaces
| Surface | What |
|---|---|
| API reads | `/projects/{p}/document-schemas[/{ref}]`, `derived-documents[/{ref}]`, `processing-jobs[/{id}]`, `derived-rows/{ref}`, `derived-reports/{ref}`, `derived-diffs/{ref}`, `derived-publish-previews/{ref}`, `derived-compensation-previews/{ref}` (`{ref}` is an id or a key; keys hold `/` and `@`) |
| API commands | `POST /commands/<Name>` for the ten commands of the table above |
| MCP | `list_derived_documents`, `get_derived_document`, `validate_against_schema` (read only: the stored report); `start_extraction`, `propose_import` (proposals) |
| Clients | `tl_api.client.ApiClient`, the TUI `ClientInterface` (embedded and remote), `FakeClient` |
| Worker | `tl_mod_documents.derivation.worker.build_worker` (the CLI and the demo use it) |

## Extractors
The pipeline finds extractors through the entry-point group `throughline.extractors`. A plugin runs in a child process
with a wall-clock limit (60 s) and a memory limit; its output is checked against the contract
(`tl_core.derivation.types`: 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell). A plugin that fails
to load stops the process loudly. PDF and OCR extractors read metadata only (ADR-0008 decision 8).

## Security properties
- Every extractor and every validation runs in a child process with a scrubbed environment, `RLIMIT_AS` and `RLIMIT_CPU`, a wall
  clock and `SIGKILL`; nothing from the child is unpickled; a breach is the fixed `extraction_limit` or `validation_limit`. Rlimits do
  not confine the filesystem or the network (a sandbox is a follow-up). See ADR-0014, Consequences (hardening).
- A client cannot set a correlation id, causation id or source that looks like a publication (`derive:`, `import:derived-`,
  `compensation:`), and compensation does not read correlation ids.
- Trusted provenance is the event source `import:derived-<id>`, the `Published` event and the `import` link; the `provenance` pset is
  writable by anyone who can write psets on the record.
- No HTTP route or MCP tool applies a JSON Schema to rows on a request.
