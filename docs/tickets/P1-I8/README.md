# Increment plan — P1-I8 Schema workbench, legacy loaders, lake marts, Phase 1 exit

Status: in-progress
Supervisor session: 2026-10-20
Brief sections: §27 (schema and semantic model management), §28 (lakehouse), §29.6 (legacy loading), §24.5 (compensation), §6.3 (conformance modes and waivers), §10.6 (workbench sketch 8), §16 Phase 1 exit
Branch: `p1/i8`

The orchestrator asked for one supervisor to run both workstreams of the plan on one branch. The contract between the tracks, the exit criteria and the decisions (D1 to D12) are in [FANOUT.md](FANOUT.md); this file is the plan and the board. Plan rows: `docs/build-spec/07-phase1-plan.md`, Increment 8.

## Objective
A schema steward drafts a package, sees its classification and impact, has it reviewed and published, and a project pins a version, with a waiver as the time-limited escape hatch (track A). An admin loads a legacy file through extract, bronze, profile, map, dry run, load and reconcile, and takes a bad load back (track B). The lake carries a documents mart and a schedule-history mart that never hold a row the lowest reader may not read. The Phase 1 exit chain (PDF to derived to published to feed to webhook receiver) runs as one demo.

## Demo
`just demo P1-I8` (SQLite and Postgres). The exact commands are fixed when the CLI lands (T09) and are copied from `dev/demos/P1-I8.sh` into the report.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `tl_schema.classify` and `classify_linkml` (T02) | Schema semantics: the class of every change decides what a project must do | orchestrator review (core engine) | done (2023370) |
| S2 | Module `schemareg` (T01): `SchemaPackage` lifecycle, `Adoption`, `Waiver`, the registry source, provider changes (`RegistryState`, `attach_registry`, `trial`), `PackageRegistry` origins and pins, `compose` waivers, `ModuleSpec.schema_source` | Effective-schema compiler and conformance rules; publish and adopt path; waivers | security pass + orchestrator review | done (0404c94) |
| S3 | T03 stub, provided test, ticket; T08 stubs, provided tests, ticket | Ticket scaffolding | — | done |
| S4 | Silver for documents and revisions in `tl lake sync`; the readable-set rule for children of a reclassified record; the walking test with a restricted document; the marts wired in; `tl lake mart ls\|show` | Sync engine, rebuild equality, confidentiality | security pass + orchestrator review | done (3d007e5) |
| S5 | Plumbing for track A: views, API routes and client methods, error rows, CLI base (`tl schema package` review commands), TUI client interface and fakes | Public interfaces, access table | security pass | done (72559cd) |
| S6 | T06: module `legacy` (`LoadRun`), the stage framework (extract in the envelope, bronze, profile, plan, load, reconcile, compensate), `tl load`, the reserved `legacy:` and `load:` prefixes | Untrusted files, bulk writes, compensation | security pass + orchestrator review | done (c65c7ab) |
| S7 | References, stubs, provided tests and tickets, batch by batch (T05a1, T07a first) | Ticket scaffolding | — | in-progress |
| S8 | Demo wiring, docs, runbooks, report | — | — | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | `SchemaPackage` record, lifecycle, `SchemaPackage.Published`, adoption with pins (plus `Waiver`, the plan's T05 record) | S | — | done (S2) | built by supervisor |
| T02 | Classification report (`tl_schema.classify`, `classify_linkml`) | S | T01 | done (S1) | built by supervisor |
| T03 | Impact report: records, columns, views, mappings, reports, MCP schemas | H | S1, S2 | merged (07c7bb7) | passed first review; dotted pset names fixed after (see report) |
| T04a | Workbench TUI: package tree, property table, lint, diff | H | S5 | draft | |
| T04b | Workbench TUI: impact, test on sample, review and publish | H | S5, T03, T04a | draft | |
| T05a1 | `tl schema package diff\|classify\|impact\|test` | H | S5, T03 | ready | |
| T05a2 | `tl schema package publish\|deprecate\|retire` and `tl schema adopt\|adoptions\|drift` | H | S5, T05a1 | ready (after T05a1 merges) | |
| T05a3 | `tl schema waiver request\|approve\|revoke\|ls` | H | S5 | draft | |
| T05a4 | `tl schema crosswalk\|export-git\|import-git` | H | S5 | draft | |
| T05b | Conformance dashboard (report function, `tl schema conformance`) | H | S5 | draft | |
| T06 | Loader framework: `legacy.LoadRun` and the stages | S | — | done (S6) | built by supervisor |
| T07a | Loader `dms-register`: document register CSV or workbook | H | S6 | ready | the reconciliation report stays a file of the run (see Risks) |
| T07b | Loaders `instrument-index` (workbook or CSV) and `equipment-list` (workbook) | H | S6, T07a | ready (after T07a merges) | line list: see Risks |
| T08 | Lake marts: documents (status, turnaround, issues) and schedule history | H | S1, S2 | merged (3fb9c0a) | passed first review; empty snapshots are skipped as the snapshot before (decision, test added) |
| T09 | Phase-exit demo script: PDF, derived, published, feed, webhook receiver; `just demo P1-I8` | H | all | draft | |
| T10 | Phase report, risk register, ADRs | O | T09 | orchestrator | not written here |

## Order of work
1. Done: S1 to S6, batch 1 (T03, T08).
2. Batch 2: T05a1 and T07a. Then, as each pair merges: T07b and T05a2; T05a3 and T05b; T05a4 and T04a; T04b; T09; the gates, the demo, the report.

## Risks and escalation triggers
- **Effective-hash churn.** Every change under `schema/core` moves the core digest and so every effective schema hash; tests that pin a hash or the list of generated files move with it. Run the shards after each schema change.
- **Provider semantics.** A project without a pin never sees a ledger-only company version (FANOUT D3). If the owner wants "latest on publish" the default flips in `PackageRegistry.adopted`; that is a decision for the orchestrator, not a quiet change.
- **Roles.** Stewards and data managers do not exist as roles (ADR-0013): admins hold their acts. A role is a decision for the owner.
- **The reconciliation report is a file, not a document (T07a).** A controlled document needs a document type for reports in the company's standards and a rendering to PDF. The report is kept in the slot `report` of the run (`tl load show RUN --report`); registering it as a document is a follow-up.
- **The line list (T07b).** Piping lines are not a tag class of the company standards; a line list needs a class and a mnemonic there, which is an owner decision. T07b loads the equipment list instead; every column of a line list would be kept in the source layer once a class exists.
- **`promote` and the MCP schema tools** (brief 27.8) are not in the Increment 8 rows and are not built (FANOUT D12).

## Blocked / Decision
none
