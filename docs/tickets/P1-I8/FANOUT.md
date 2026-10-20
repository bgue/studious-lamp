# Fanout plan: P1-I8 (schema workbench, legacy loaders, lake marts, Phase 1 exit)

Status: active. The plan asks for two supervisors; the orchestrator asked for one supervisor to run both tracks
on `p1/i8` to save capacity. This file is the contract the tracks share. Plan: `docs/build-spec/07-phase1-plan.md`
Increment 8. Briefs: §27 (schema management), §28 (lakehouse), §29.6 (legacy loading), §24.5 (compensation),
§16 Phase 1 exit. Decisions this file builds on: ADR-0010 (module storage), ADR-0014 (derivation pipeline),
ADR-0015 (snapshots and lake passes), ADR-0016 (confidentiality), ADR-0017 (integration).

## Objective
A schema steward can draft a package, see what the change is (classification) and what it touches (impact), have it
reviewed, publish it, and have a project adopt a pinned version, with a time-limited waiver as the escape hatch.
An admin can load a legacy file (document register CSV, tag list XLSX, line list XLSX) through extract, bronze,
profile, map, dry-run, load and reconcile, and take a bad load back. The lake carries a documents mart and a
schedule-history mart that never hold a row the lowest reader may not read. The Phase 1 exit chain
(PDF to derived to published to feed to webhook receiver) runs as one demo.

## Exit criteria
- [ ] **Registry.** `SchemaPackage` is a ledgered record with the workflow Draft, InReview, Approved, Published,
  Deprecated, Retired; `SchemaPackage.Published` (feed card, webhooks) makes the version adoptable; a project pins
  a version through an `Adoption` record; the effective schema of a project follows its pins.
- [ ] **Classification and impact.** Every package version carries a classification report (additive, constraining,
  renaming, breaking, deprecation, forbidden; handling per class) and an impact report before review. Breaking and
  forbidden changes cannot be submitted.
- [ ] **Waivers.** `Waiver` is a record with approver, reason and expiry; an approved, unexpired waiver reaches the
  conformance evaluator through the effective schema; an expired or revoked one does not.
- [ ] **Surfaces.** TUI workbench (package tree, property editor, lint, diff, impact, test on sample, review and
  publish), conformance dashboard, and the complete `tl schema` command set.
- [ ] **Loaders.** One framework (`legacy.LoadRun`) with the stages extract, bronze, profile, map, dry-run, load,
  reconcile and compensate; three loaders; the reconciliation report is registered as a document.
- [ ] **Lake.** Marts for documents and schedule history, rebuilt equal to the incremental lake, with hidden rows
  absent (walking test with a restricted and a privileged document).
- [ ] **Demo.** `just demo P1-I8` clean on SQLite and Postgres.
- [ ] **Gates.** `just check`, `just test` (in parts), parity of the touched directories on both adapters.

## Tracks
| Track | Name | Pieces (supervisor builds in capitals; the rest are tickets) |
|---|---|---|
| A | Workbench and registry | T01 module `schemareg` (SchemaPackage lifecycle, Adoption, Waiver, the provider source); T02 classification engine; plumbing (API, client, CLI base, TUI client); T03 impact; T04a, T04b workbench TUI; T05a `tl schema` commands; T05b conformance dashboard |
| B | Loaders and lake | T06 module `legacy` (LoadRun) and the stage framework; T07a, T07b loaders; T08 lake marts |
| both | Exit | T09 the phase-exit demo and `just demo P1-I8`; T10 (phase report, risks, ADRs) is the orchestrator's and is not written here |

## Shared contract
The tracks touch each other in four places only. Both sit on one branch, so a change to any of them is a commit
that names it.
1. **Events.** `SchemaPackage.Published` (core catalog; payload gains `record_id`, `kind`, `classification`,
   `content_sha256`, all optional so the P0 payload still validates), `Schema.EffectiveChanged` (unchanged), and the
   module events `SchemaPackage.Drafted|Revised|Submitted|ChangesRequested|Approved|Deprecated|Retired`,
   `Adoption.Pinned`, `Waiver.Requested|Approved|Revoked`. Loaders do not write or read these.
2. **What loaders take from A.** The effective schema of the target project (`get_provider().effective(scope)`)
   and `tl_schema.conformance.evaluate` in `lenient` mode for the dry run. Nothing else: a loader never edits a
   package, a pin or a waiver. A loader whose mapping names a pset the project has not adopted gets a dry-run
   problem that names the pset and the package that would supply it.
3. **Shared files.** `packages/tl-api/src/tl_api/commands.py` and `routes/__init__.py`, the API client
   protocol (`client/*`, the embedded client, `FakeClient`), `docs/reference/openapi.json`, `tl_cli/main.py`,
   the pinned lists listed in L-P1-I7B-4, `uv.lock`. Edited only by supervisor pieces, never by two tickets of one
   batch.
4. **The lake.** A touches no lake file. B's T08 owns `tl_lake` silver and marts; the loaders write only
   `legacy_<system>_<table>` tables through the bronze writer of T06.

## Decisions
| # | Decision |
|---|---|
| D1 | **Packages are the constrained subset, not LinkML.** Company and project packages are `PackageDoc` YAML (`tl_schema.packages`), as in P0-I2. The plan's `linkml diff` has no counterpart in the installed linkml, so T02 classifies two ways with one report model: `classify_packages(old, new)` for package versions and `classify_linkml(old_view, new_view)` for repository schemas (`tl schema classify --base <git ref>`, the 04-gates row). |
| D2 | **Roles.** Phase 1 has `admin`, `user` and `document_controller` (ADR-0009, ADR-0013). Drafting, revising and submitting a package is any signed-in person; requesting changes, approving, publishing, deprecating, retiring, adopting and approving a waiver are `admin`. The submitter cannot approve their own package or waiver. A waiver is requested by any signed-in person. No new role is introduced; stewards and data managers are admins until the owner asks for roles (follow-up for the risk register). |
| D3 | **Ledger packages join the directory ones.** The package directory stays the base layer (fixtures, `TL_SCHEMA_DIR`). Published ledger packages enter the provider through a `RegistrySource` (the pattern of `ExtensionSource`). Company scope uses the highest version overall. A project uses, for each company package, the version it pins; without a pin it uses the highest *directory* version and never a ledger-only version; a project's own extension and project packages are in force from publication. A name@version that exists in the directory cannot be published. |
| D4 | **Gates in the lifecycle.** Submit computes the classification (against the highest published version of the name, or none) and refuses `breaking` and `forbidden`. Publish requires an Approved package whose classification is still the one approved. Adoption of anything but an additive version needs the SHA-256 of the project impact report the caller saw (the preview-token pattern, L-P1-I7B-3). Retire is refused while a project pins the version. |
| D5 | **Waivers reach the evaluator through the effective schema**, merged with the waivers of a project package. Approving or revoking one records a new effective hash. A waiver's path must name a property of the project's effective schema; expiry is a date no later than 366 days ahead. |
| D6 | **Loader runs are records.** `legacy.LoadRun` (key `<system>/<table>#<n>`) is the job record of a run, like a schedule snapshot. The source file is a file in the slot `source`; the extracted rows, the profile and the reconciliation report are files in the slots `extracted`, `profile` and `report`, written by the module only. The events carry counts and SHA-256, never rows. |
| D7 | **Loaders reuse, they do not rewrite.** Extraction runs in the D9/D10 envelope of ADR-0014 with the `tl_extract` readers and their bounds. Tag rows go through the engineering import (`plan_import`, `apply_plan`); document rows through the documents import. A loader's mapping is a template of the existing kind (`tl_mod_engineering.imports.mapping`, `tl_mod_documents.imports.mapping`), fed with the CSV text of the extracted grid. Writes are commands, source `legacy:<system>`, one correlation id, and the run records the ids it wrote so compensation reverses exactly those. |
| D8 | **Bronze is a copy.** `legacy_<system>_<table>` tables in the lake hold the verbatim cells (all VARCHAR) with `_run_id` and `_row_no`. They are not in the ledger, so a lake rebuild drops them; `tl load bronze RUN` writes a run's table again from its stored extract. System and table names match `[a-z][a-z0-9_]{0,30}`; column names are folded, de-duplicated and capped at 200. |
| D9 | **Access.** Opening, extracting, profiling, mapping and dry-running are open to a signed-in admin only, because a source file is an untrusted upload that costs CPU and the load writes in bulk; load and compensate are `admin`. An agent proposes nothing here. A run has a class (`internal` or `restricted`, from the loader or the administrator, ADR-0016): the run, its files, its events and the ids it records are hidden from those who may not read that class. Reads of a run (status, profile, report) are `tl load` commands for administrators only; no API route or MCP tool exposes a run. The reconciliation report is a file of the run (`tl load show RUN --report`); it is not registered as a document (decision of 2026-10-20, security review F8). Bronze is refused for a restricted run and needs `--include-confidential` for an internal one. |
| D10 | **Confidentiality of marts.** Silver and mart tables are built from rows the lowest viewer may read (`confidentiality.not_hidden` on the record id, as the existing silver tables). A reclassification moves `last_seq`, so the next sync deletes the row. The walking test uses a restricted and a privileged document and asserts they appear in no mart cell, count or aggregate. |
| D11 | **Security review list** (reported under `SECURITY_REVIEW:`): the `Waiver` record and its evaluator path; the publish and adopt path; the provider source; every parser of untrusted files (XLSX and CSV of the loaders, the profile queries over cell text); the bulk load; compensation; the silver and mart builders. |
| D12 | **Not built, by plan.** Brief §27.8 MCP tools (`get_effective_schema`, `propose_schema_change`, ...) and `tl schema promote` (needs read-time aliases in the effective schema, §27.5) are not in the Increment 8 rows. They go in the report as follow-ups; the orchestrator decides. |

## Merge order and conflict owner
One branch. Supervisor pieces first (T02, T01, plumbing, T06), tickets as their dependencies merge, T09 last.
Merge commits only. I own every conflict, including `uv.lock` (regenerate with `uv lock`, never by hand).

## Human gates
Delegated under ADR-0008 decision 6. Schema merges (`schema/core/events.yaml`, `schema/modules/schemareg/**`,
`schema/modules/legacy/**`, fixtures) are listed under SCHEMA_APPROVALS. Migration of existing data, copyleft
licences and spend still stop the run. No new PyPI dependency is planned: DuckDB, openpyxl and pypdf are locked.
