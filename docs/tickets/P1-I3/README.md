# Increment plan — P1-I3 workstream A: derivation pipeline and schema-validated derived documents

Status: in-progress
Supervisor session: 2026-10-17
Brief sections: §9 M1 (record types, schema-validated derivation pipeline), §24.5 (compensation by correlation id), §16 Phase 1 exit, §9 M2 (bulk import with provenance), §20 (file slots), §11.3 (propose-only agents)
Branch: `p1/i3a` (base: `p1/i3`, which holds the fanout plan and the frozen contract). Workstream B (extractors, package `tl-extract`) is `p1/i3b`.
Fanout plan: [FANOUT.md](FANOUT.md) (decisions D1 to D9 are binding). Decisions: ADR-0008 (decision 8, stubs only), ADR-0009, ADR-0010 (+ addenda), ADR-0011, ADR-0013, and the new [ADR-0014](../../adr/0014-derivation-pipeline.md).

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
| S4 | Derivation commands: `RegisterDocumentSchema`, `RetireDocumentSchema`, `StartExtraction`, `ValidateDerived`, `CancelJob`, the `extract` and `validate` job kinds, server-written files (`by_module` on the file service), validation (T04) and diff (T06) | Ledger writes, files, access | reviewer, orchestrator | done (8361c4d) |
| S5 (T05) | Publish: mapping model, preview, one correlated apply through module commands, provenance, compensation by correlation; `PublishDerivedTags`, `PublishDerivedDocuments`, `CompensatePublication`; access check when a proposal is accepted (7eb46e2) | Permissions, correlated import, compensation (§24.5) | reviewer, orchestrator | done (8361c4d, 7eb46e2) |
| S6 | Client interface: the reads (`derivation/views.py`), the HTTP routes, the `ApiClient`, `EmbeddedClient` and `FakeClient` methods, the MCP tools (T08a and T08b), `build_worker`, the `tl derive` reference group and the TUI `derive_text` and screens (references for T07 and T14) | Interfaces first (L-P1-I0A-11) | reviewer | done (1f0d86a, 2ee0d18) |
| S7 | Demo, docs (module page, runbook, READMEs), report | Wiring and docs | orchestrator | done (module page, runbook, READMEs, demo, report: S31 and later) |
| S12 | Accepting a proposal needs the access of the proposed command (core, API, CLI, MCP modes; fail closed) | Permissions | orchestrator | done (7eb46e2) |
| S15 | Resource envelope for extractors, FANOUT D9: child process, `RLIMIT_AS` and `RLIMIT_CPU`, wall clock with `SIGKILL`, fixed `extraction_limit`, `MAX_CELLS` checked twice | Security | orchestrator | done (52db1b1) |

## Tickets
Ticket numbers T09 to T13 belong to workstream B. The CLI tickets, which the plan did not list, are numbered from T14.
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | LinkML: `DocumentSchema`, `DerivedDocument`, `ProcessingJob`; derived workflow (see S2) | S | — | merged (supervisor) | built on `p1/i3a` |
| T02 | Job runner v1 (see S3) | S | T01 | merged (supervisor) | built on `p1/i3a`; awaits the orchestrator's review |
| T03 | Extractor registry (`load_extractors`, `choose`, fail loud) and `run_extraction`, the guard around a plugin call. The ledger-facing half of "job wiring" is the `extract` job kind of S4 | H | contract | merged | 357c607 (reference ad63051, stub fc049b5; reviewer pass); registry hardened in 069860c |
| T04 | Validation: JSON Schema over extracted rows with typed reading of cells; row- and field-level report model | H | T01, T03 | built by supervisor | In S4 (8361c4d). The `validate` and `extract` job kinds and the pipeline tests cannot run without it, so it was built with them and tested in full (`test_derivation_validation.py`); a stub plus held tests would have held back every pipeline test. No Haiku dispatch. |
| T05 | Publish (see S5) | S | T04 | built by supervisor | In S5 (`derivation/publish.py`); a permissions piece. Compensation reverses recorded ids since 0c2fdc8. |
| T06 | Diff of two row sets by key column | H | T04 | built by supervisor | In S4 (`diff.py`, `test_derivation_diff.py`), used by S6's `derived_diff`; no Haiku dispatch, for the reason given at T04. |
| T07a | TUI job monitor | H | S6 | done | merged 5b767d4 (reviewer pass) |
| T07b | TUI derived documents and validation report viewer (F11) | H | S6 | done | merged 85aa786 (reviewer pass) |
| T07c | TUI publish preview and approve | H | S5, S6 | done | merged 3080f42 (50380c8; 7 tests) |
| T08a | API reads and routes for jobs, derived documents, reports, schemas | H | S4, S5 | built by supervisor | In S6 (1f0d86a): routes are a security-reviewed piece and the clients need them. `test_api_derivation_reads.py`, `test_client_derivation.py`. |
| T08b | MCP: `start_extraction` (proposal), `validate_against_schema` (read only), `propose_import` (proposal), plus two reads | H | S4, S5 | built by supervisor | In S6 (1f0d86a): an agent action (security review). `test_mcp_derivation_tools.py`. |
| T14a | CLI `tl derive schema` (register, ls, show, retire) | H | S4 | done | merged 6f27ecb (reviewer pass) |
| T14b | CLI `tl derive open`, `start`, `ls`, `jobs`, `cancel` (`content` and `worker` are finished in the stub) | H | S4 | done | merged 15f4527 (post-merge reruns; fresh reviewer passed) |
| T14c | CLI `tl derive show`, `report`, `rows`, `diff`, `check`, `validate` | H | T14b | done | merged 53d9567 (31b2795); diff notice S38 |
| T14d | CLI `tl derive publish` (preview, apply), `compensate` | H | S5, T14a, T14b | done | merged 4bbea71, review-only pass pending (0ec96fc plus S35/S36 fixes; reruns 15 pass 3 skip on both adapters) |

D8 held for the supervisor-built pieces; the orchestrator told me (2026-10-17) to go on with T04 to T08 before B is in, so the tickets
that do not need B's extractors are ready now. The extractor is a fake in tests until `p1/i3b` is merged. Batches (disjoint paths):
1. T14a, T14b, T07a, T07b; 2. T07c, T14c, T14d (the last two use T14a and T14b in their test setup).

## Order of work
1. ADR-0014 and the plan, then T01 (everything imports its names and tables), then T02.
2. T03 stub with provided tests; dispatch (the only ticket that needs no merged workstream B).
3. S4, S5 and S6 against the fake extractor (T04, T06, T08a and T08b are built inside them), the resource envelope (D9), then the stubs, provided tests and tickets of T07 and T14.
4. T07 and T14 in two batches; after B is in, merge `p1/i3`, run the real extractors through the demo, gates, docs and the report.

## Risks and escalation triggers
- **Agent writes.** Agents are propose-only (B15). `start_extraction` and `propose_import` are proposals; `validate_against_schema` reads and writes nothing. A direct "stage" mode for agents would change the permission model: not built; recorded in ADR-0014 as a follow-up the orchestrator may take up.
- **Core contract touches.** `PROPOSABLE_TOOLS` and the proposal command table (core, frozen in P0-I6) gain entries; the file service gains a Python-only `by_module` keyword. Neither changes a 03 §7 interface. Both are listed for security review.
- **Provenance pset.** `provenance` must exist in the company's effective schema for the target types. The sample company package gains it (fixture, SCHEMA_APPROVALS); publish refuses with a clear message when the pset is missing.
- **Large inputs.** Rows live in files (slot `extracted`), never in events; the extractor bounds of the contract hold (50 MiB, 20 000 rows, 200 columns, 10 000 characters per cell).
- Stop and escalate if: a cross-workstream contract must change; publishing needs a permission the roles cannot express; the queue needs a change to a 03 §7 interface.

## Blocked / Decision
None yet.
