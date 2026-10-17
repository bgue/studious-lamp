# Fanout plan: P1-I3 (derivation pipeline and schema-validated derived documents)

Status: active. Both workstreams start now from `p1/i3`.
Orchestrator session: 2026-10-17
Plan: `docs/build-spec/07-phase1-plan.md` Increment 3. Brief: §9 M1 (derivation), §24.5 (correlated imports and
compensation), §16 Phase 1 exit. Owner decisions: ADR-0008 (decision 8: extraction is stubs only, no LLM, no spend).

## Objective
The §9 M1 pipeline: a document revision's rendition is registered as a source, an extractor runs as a job, the result
is validated against a versioned `DocumentSchema`, and a valid derived document is published into target records as
one correlated, compensable import with provenance back to the source revision.

## Exit criteria
- [ ] **Contract.** `tl_core/derivation/types.py` is implemented by both workstreams; every extractor passes
  `tests/contract/test_extractor_contract.py`.
- [ ] **Records.** `DocumentSchema` (JSON Schema + version + sample), `DerivedDocument` and `ProcessingJob` are module
  records on the ADR-0010 seam, with the derived workflow Pending → Processing → Invalid / Valid → Published.
- [ ] **Jobs.** A DB-backed job queue (SQLite table; Postgres `FOR UPDATE SKIP LOCKED`), a worker loop and job events;
  a job killed mid-run is retried or failed, never lost or run twice to completion.
- [ ] **Extractors.** Tabular (CSV and XLSX, with column profiling and header mapping), PDF (real metadata, content
  stubbed), image/OCR (real metadata, content stubbed), each a plugin found by entry point.
- [ ] **Validation.** JSON Schema over extracted rows with a row- and field-level report document.
- [ ] **Publish.** Declarative, LinkML-validated mapping from rows to module commands; one correlated import batch;
  compensation by correlation (§24.5); provenance `src.doc.<key>@<rev>` on each target and a `derived from` link to
  the derived document; a diff against the prior derived revision.
- [ ] **Surfaces.** TUI job monitor, validation report viewer, publish preview and approve; API and MCP
  `start_extraction`, `validate_against_schema`, `propose_import` (staged; a person approves).
- [ ] **Demo.** `just demo P1-I3` on SQLite and Postgres: register an instrument-index PDF and run the PDF extractor
  (metadata recorded, content stubbed); attach the derived CSV; validation fails on one row; fix the CSV; re-run;
  publish → 40 tags created, each with `src.doc.ISD-001@A` provenance and a `derived from` link; a compensation
  rolls the batch back.

## Workstreams
| WS | Name | Branch · worktree | Base | Supervisor builds | Tickets (summary) |
|---|---|---|---|---|---|
| A | Pipeline and schemas | `p1/i3a` · `/home/user/wt/p1-i3a` | `p1/i3` | T01 LinkML, T02 job runner, T05 publish | T03 registry and job wiring, T04 validation, T06 diff, T07 TUI, T08 API/MCP; demo and increment report |
| B | Extractors | `p1/i3b` · `/home/user/wt/p1-i3b` | `p1/i3` | the package skeleton and the shared reader limits | T09 tabular, T10 PDF (metadata), T11 OCR (metadata), T12 golden dataset, T13 document schema fixtures |

## Shared contracts
- `packages/tl-core/src/tl_core/derivation/types.py` and `tests/contract/test_extractor_contract.py` (orchestrator).
- B ships a new package `packages/tl-extract` (`tl_extract`) whose `pyproject.toml` registers each extractor under the
  entry-point group `throughline.extractors`. A never imports `tl_extract`; it finds extractors by entry point.
- T13 fixtures (`schema/fixtures/document-schemas/*`) are B's; A reads them by path in its tests and demo.

## Orchestrator decisions
| # | Decision |
|---|---|
| D1 | ADR-0008 decision 8 is applied as follows. PDF and OCR extractors read **real metadata** (page count, title, author, dates, producer; image size and format) and return `status="metadata_only"` with empty rows and a note naming the decision. A **CSV or XLSX** that a person attaches as the derived content is read deterministically and fills `rows`: that is data entry, not content extraction, and it is what the §16 exit ("derive validated CSV/XLSX, publish") needs. No LLM, no OCR engine, no network, no spend. |
| D2 | Dependencies: `openpyxl` (MIT, already locked) for XLSX; `pypdf` (BSD-3-Clause) for PDF metadata; Pillow only if already locked, otherwise read image headers by hand. No pdfplumber, Camelot or Tesseract in this increment: they would only serve the stubbed content path. Name every licence; the licence gate decides. |
| D3 | Jobs: `ProcessingJob` is a module record whose state changes are ledger events (attributable, replayable); the claim queue is an operational table (`job_queue`), like `wh_*` and the auth tables, not a projection. A claim has a lease; an expired lease is reclaimable; completion is idempotent on (job id, attempt). |
| D4 | Bounds (in the contract): 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell; bigger is refused with a problem, never truncated. Extractors are pure: no ledger, no unit of work, no network, no filesystem path from user input. |
| D5 | Publish writes only through module commands (ADR-0010), never generic `CreateRecord`, so module rules, limits and allow-lists hold. The mapping is data (LinkML-validated YAML), not code. Provenance is a pset value `provenance.source = "src.doc.<key>@<rev>"` plus a `derived from` link to the `DerivedDocument`; the import batch carries one correlation id; compensation appends reversing events for that correlation and is itself correlated. |
| D6 | Access: running an extraction, validating and previewing are open to any signed-in person. **Publishing** needs the access of the bulk import of the target type: tags → admin (as `tl tag import --apply`, P1-I1), documents → document controller (ADR-0013). Compensation needs admin. Agents use `propose_import`, which a person approves; agents never publish. |
| D7 | Every supervisor-built piece that adds or changes an HTTP route, an access level, an allow-list, an upload or download path, a job claim, or an agent action is listed under `SECURITY_REVIEW:` in the relay; the orchestrator runs a fresh-context security review before DONE. |
| D9 | **Resource envelope (security review of WS-B, 2026-10-17).** Readers of untrusted files cannot bound every cost from inside (decompression in pypdf, openpyxl row materialisation). The pipeline therefore runs every extractor in a separate process with `RLIMIT_AS` = `EXTRACT_MAX_MEMORY_BYTES` (1 GiB), `RLIMIT_CPU` and a wall-clock limit of `EXTRACT_MAX_SECONDS` (60 s); on breach the job fails with a fixed problem (`extraction_limit`), the child is killed, nothing is written. The readers still enforce their own bounds (defence in depth). `MAX_CELLS` (1 000 000 data cells) joins the contract bounds. |
| D8 | Merge order: A T01–T03 into `p1/i3a`; B into `p1/i3` when B is DONE; A merges `p1/i3` and does T04–T08, the demo and the report. Conflicts in `uv.lock` and the root `pyproject.toml` are resolved by regenerating with `uv lock`, never by hand. |

## Merge order and conflict owner
A (T01–T03) → B → A (T04–T08, demo, report). A owns conflicts. Merge commits only.

## Human gates
Delegated under ADR-0008 decision 6. Schema merges (`schema/modules/**`, fixtures) are listed under SCHEMA_APPROVALS
and approved by the orchestrator. Data migrations of existing data, copyleft licences and spend still stop the run.
