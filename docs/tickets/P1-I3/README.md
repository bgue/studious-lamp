# Increment plan — P1-I3 workstream A: derivation pipeline and schema-validated derived documents

Status: in-progress
Supervisor session: 2026-10-17
Brief sections: §9 M1 (record types, schema-validated derivation pipeline), §24.5 (compensation by correlation id), §16 Phase 1 exit, §9 M2 (bulk import with provenance), §20 (file slots), §11.3 (propose-only agents)
Branch: `p1/i3a` (base: `p1/i3`, which holds the fanout plan and the frozen contract). Workstream B (extractors, package `tl-extract`) is `p1/i3b`.
Fanout plan: [FANOUT.md](FANOUT.md) (decisions D1 to D8 are binding). Decisions: ADR-0008 (decision 8, stubs only), ADR-0009, ADR-0010 (+ addenda), ADR-0011, ADR-0013, and the new [ADR-0014](../../adr/0014-derivation-pipeline.md).

## Objective
Build the §9 M1 pipeline around the frozen extractor contract (`tl_core/derivation/types.py`): a document revision's rendition (or a
CSV or XLSX a person attaches) is read by an extractor plugin as a **job**, the result is validated against a versioned
`DocumentSchema`, and a valid `DerivedDocument` is published into target records as **one correlated, compensable import** with
provenance back to the source revision. A person approves publication; an agent can only propose it.

## Where the records live (decision, ADR-0014)
`documents.DocumentSchema`, `documents.DerivedDocument` and `documents.ProcessingJob` are record types of the **documents module**
(ADR-0010 seam), not a new module. Reasons: the brief lists them in M1; they point at documents, revisions and renditions that the
module already owns; publishing into documents is a call into the same package; and publishing into tags reaches the engineering
module through the dependency the documents package already has. The code is a sub-package, `tl_mod_documents.derivation`, so the
module does not grow flat. The queue that decides which worker runs a job next is generic and lives in core: the operational table
`job_queue` (`schema/core/jobs.yaml`), `tl_core.jobs`, and one adapter class per database in `tl_adapters.queue`.

## Demo
`just demo P1-I3` (SQLite and Postgres; `dev/demos/P1-I3.sh`, driver `dev/demos/p1_i3_demo.py`), one PASS line per clause of the
FANOUT demo:
1. register an instrument-index PDF and run the PDF extractor: metadata recorded, content stubbed (status `metadata_only`, ADR-0008 decision 8);
2. attach the derived CSV; validation fails on one row (the report names the row and the field);
3. fix the CSV and run again: a second content revision, valid; the diff against the first shows the one changed row;
4. publish (admin): 40 tags created, each with `provenance.source = src.doc.ISD-001@A` and a `derived from` link to the derived document;
5. compensation (admin) rolls the batch back by its correlation id; the originals stay in the ledger;
6. a plain user and an agent cannot publish; the agent's `propose_import` waits for a person;
7. the TUI job monitor, validation report and publish preview show the same state as the API and the MCP tools.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | ADR-0014 and this plan | Contract and permission decisions | orchestrator | done (ADR proposed) |
| S2 (T01) | LinkML for the three records and the derivation events, the derived workflow and file slots (fixtures), `job_queue`, projectors, readers, module spec, provenance pset, tests | Schema (human-gated; listed under SCHEMA_APPROVALS) | reviewer, orchestrator | done (4016789) |
| S3 (T02) | Job queue: core types and portable SQL, `FOR UPDATE SKIP LOCKED` claim on Postgres, runner loop, leases, idempotent completion, job events (the `reconcile` of orphan jobs comes with S4, it reads the module table) | Concurrency and a job claim (security review) | reviewer, orchestrator | done (c46b4c8) |
| S4 | Derivation commands: `RegisterDocumentSchema`, `RetireDocumentSchema`, `StartExtraction`, `ValidateDerived`, `CancelJob`, the `extract` and `validate` job kinds, server-written files (`by_module` on the file service) | Ledger writes, files, access | reviewer, orchestrator | todo |
| S5 (T05) | Publish: mapping model, preview, one correlated apply through module commands, provenance, compensation by correlation; `PublishDerivedTags`, `PublishDerivedDocuments`, `CompensatePublication`; access check when a proposal is accepted | Permissions, correlated import, compensation (§24.5) | reviewer, orchestrator | todo |
| S6 | Client interface: derivation methods on the API client, the embedded client, the fake, and the MCP context (the tickets T07, T08 and T14 call them) | Interfaces first (L-P1-I0A-11) | reviewer | todo |
| S7 | Demo, docs (module page, runbook, READMEs), report | Wiring and docs | orchestrator | todo |

## Tickets
Ticket numbers T09 to T13 belong to workstream B. The CLI tickets, which the plan did not list, are numbered from T14.
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | LinkML: `DocumentSchema`, `DerivedDocument`, `ProcessingJob`; derived workflow (see S2) | S | — | merged (supervisor) | built on `p1/i3a` |
| T02 | Job runner v1 (see S3) | S | T01 | merged (supervisor) | built on `p1/i3a`; awaits the orchestrator's review |
| T03 | Extractor registry (`load_extractors`, `choose`, fail loud) and `run_extraction`, the guard around a plugin call. The ledger-facing half of "job wiring" is the `extract` job kind of S4 | H | contract | ready | reference ad63051, stub fc049b5 |
| T04 | Validation: JSON Schema over extracted rows with typed reading of cells; row- and field-level report model | H | T01, T03 | todo | |
| T05 | Publish (see S5) | S | T04 | todo | |
| T06 | Diff of two row sets by key column | H | T04 | todo | |
| T07a | TUI job monitor | H | S6 | todo | |
| T07b | TUI validation report viewer | H | S6 | todo | |
| T07c | TUI publish preview and approve | H | S5, S6 | todo | |
| T08a | API reads and routes for jobs, derived documents, reports, schemas | H | S4, S5 | todo | |
| T08b | MCP: `start_extraction` (staged), `validate_against_schema` (read only), `propose_import` (staged) | H | S4, S5 | todo | |
| T14a | CLI `tl derive schema` (register, ls, show, retire) | H | S4 | todo | |
| T14b | CLI `tl derive start`, `content`, `jobs`, `worker` | H | S4 | todo | |
| T14c | CLI `tl derive show`, `report`, `diff`, `validate` | H | T04, T06 | todo | |
| T14d | CLI `tl derive publish` (preview, apply), `compensate` | H | S5 | todo | |

D8 holds: T04 to T08 and T14 are dispatched after the orchestrator tells me workstream B is merged into `p1/i3` and I have merged
`p1/i3` into `p1/i3a`. Until then the extractor is a fake registered through an entry point in tests.

## Order of work
1. ADR-0014 and the plan, then T01 (everything imports its names and tables), then T02.
2. T03 stub with provided tests; dispatch (the only ticket that needs no merged workstream B).
3. While waiting for workstream B: S4, S5 and S6 against the fake extractor, T04/T06 stubs and provided tests prepared but not dispatched.
4. After the merge: T04, T06, then T07, T08, T14 in batches of two to four with disjoint paths; the demo; gates; the report.

## Risks and escalation triggers
- **Agent writes.** Agents are propose-only (B15). `start_extraction` and `propose_import` are proposals; `validate_against_schema` reads and writes nothing. A direct "stage" mode for agents would change the permission model: not built; recorded in ADR-0014 as a follow-up the orchestrator may take up.
- **Core contract touches.** `PROPOSABLE_TOOLS` and the proposal command table (core, frozen in P0-I6) gain entries; the file service gains a Python-only `by_module` keyword. Neither changes a 03 §7 interface. Both are listed for security review.
- **Provenance pset.** `provenance` must exist in the company's effective schema for the target types. The sample company package gains it (fixture, SCHEMA_APPROVALS); publish refuses with a clear message when the pset is missing.
- **Large inputs.** Rows live in files (slot `extracted`), never in events; the extractor bounds of the contract hold (50 MiB, 20 000 rows, 200 columns, 10 000 characters per cell).
- Stop and escalate if: a cross-workstream contract must change; publishing needs a permission the roles cannot express; the queue needs a change to a 03 §7 interface.

## Blocked / Decision
None yet.
