# Increment plan — P0-I8 workstream C: agent-dev baseline

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §25.1 to §25.4 (agent affordances, scaffolding CLI, dev MCP server, gates); build spec `04-gates.md` §1
Branch: `p0/i8c` (base `p0/i8`); ticket ids `P0-I8-T40` to `T59`, supervisor pieces `P0-I8-S4n`

## Objective
Coding agents can inspect the running system and scaffold new work without breaking the gates. This workstream builds the dev MCP server (`python -m tl_mcp.dev`, stdio, dev data only) with its tools and resources, the `tl new module|record-type|projector` scaffolders, an audit of every package's README.md and AGENTS.md against the code, a review of the CI workflow against `04-gates.md` §1, and a runbook for the dev server. Settings (workstream A) and extension types (workstream B) are built in parallel and are not touched.

## Demo
`just demo P0-I8-C` (script `dev/demos/P0-I8-C.sh`):
1. creates a temporary ledger and a few records;
2. starts `python -m tl_mcp.dev` and talks MCP to it over stdio: lists the tools, runs `query_db`, `gen`, `rebuild_projections`, `render_screen`, `send_test_webhook` (to a loopback receiver the demo starts), reads a resource, and shows a refusal for a database outside `dev/` and a non-SELECT statement;
3. runs `tl new module`, `tl new record-type` and `tl new projector` into a temporary tree and shows that ruff and the generated tests pass.

## Decisions taken in this workstream
| # | Decision | Why |
|---|---|---|
| C1 | `tl new module <name>` creates `packages/tl-mod-<name>` (import `tl_mod_<name>`), not `packages/tl-modules/<name>` as `03-repo-and-toolchain.md` §1 sketches. | The uv workspace member glob is `packages/*`; a `packages/tl-modules/` directory without a `pyproject.toml` would make `uv sync` fail. Flagged to the orchestrator as a layout deviation; the module name still maps to `schema/modules/<name>/` and `docs/modules/<name>/`. |
| C2 | `tl new projector` scaffolds a derived table `proj_<module>_<name>`, never a `cur_*` table. | Root rule 4: current-state DDL is generated. A record type's `cur_<module>_<class>` table comes from `tl new record-type` plus `just gen`, which does not read `schema/modules/` yet (Phase 1). |
| C3 | The dev-data guard is stricter than D12 in three places: a Postgres host must be this machine; a Postgres URL may carry only the `options=-csearch_path=<schema>` parameter; `TL_ENV` must be unset, `dev`, `test` or `ci`. | A `tl_dev` database on a remote host, or a URL parameter that redirects the connection, is still not dev data. |
| C4 | `query_db` on Postgres parses with DuckDB's parser (`json_serialize_sql`, parse only), the approach of the lake guard (L-P0-I7-B4, B7). `tl-mcp` declares `duckdb==1.5.5` (MIT, already locked for `tl-lake`). | The DuckDB grammar derives from Postgres's; no new package. The raw-text screen and the READ ONLY transaction are the other layers. |
| C5 | `wh_secret` (webhook signing secrets) cannot be read through `query_db` on either dialect. | Secrets never enter the ledger or tool output; the table is the one place they live. |
| C6 | The audit of AGENTS.md and README.md is a repeatable tool (`dev/tools/audit_docs.py`) plus a supervisor read of each rule against the code it names. | A mechanical check finds dead references; only a read finds a rule that no longer describes the code. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S41 | Dev MCP server core: `tl_mcp/dev/` guard, SQL guard, `query_db`, runtime, server, entry point, tests | Security guard for what agents may touch (Sonnet-authored, auth-adjacent); orchestrator relay review in fresh context, security focus | fresh reviewer, then orchestrator | built |
| S42 | `tl new` scaffold engine and `tl new module` | Shared engine two tickets build on; writes files into the repository | reviewer | built |
| S43 | Docs audit tool and the AGENTS.md audit | Cross-package read | self | tool built; audit in progress |
| S44 | CI workflow review against `04-gates.md` §1 | Gates policy | self | planned |
| S45 | Runbook `docs/runbooks/dev-mcp.md`, package READMEs and AGENTS.md for `tl-mcp` and `tl-cli`, learnings | Needs every tool merged | self | planned |
| S46 | Integration test, demo `dev/demos/P0-I8-C.sh`, report `docs/reports/P0-I8-C.md` | Closes the workstream | self | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T40 | `run_tests` tool | haiku | S41 | ready | |
| T41 | `gen` tool (drift report) | haiku | S41 | ready | |
| T42 | `rebuild_projections` tool | haiku | S41 | ready | |
| T43 | `seed` tool | haiku | S41 | draft | |
| T44 | `send_test_webhook` tool | haiku | S41 | draft | |
| T45 | `render_screen` tool | haiku | S41 | draft | |
| T46 | resources: schema graph and event catalog | haiku | S41 | draft | |
| T47 | resources: ADRs, runbooks, test reports | haiku | S41 | draft | |
| T48 | `tl new record-type` | haiku | S42 | draft | |
| T49 | `tl new projector` | haiku | S42 | draft | |
| T50 | docs: modules the audit found undocumented (tl-api, tl-lake, tl-sim, tl-cli) | haiku | S43 | draft | |

Batches (concurrency cap 3, disjoint *Allowed paths*, dependencies already merged): T40 + T41 + T42; then T43 + T44 + T45; then T46 + T47 + T48; then T49 + T50.

## Order of work
1. S41 and S42 (done), S43 tool (done), tickets T40 to T42, first relay (S41 goes to the security review at the same time).
2. While batch 1 runs: nothing (relay); on return merge, fix review findings on S41, write T43 to T45, run the AGENTS.md semantic audit.
3. Batches 2 to 4, S44 (CI), S45 (docs), S46 (integration, demo, report).

## Risks and escalation triggers
- The Postgres SQL guard is a second parser's view of the statement (DuckDB, not Postgres). A statement the two read differently could slip past the tree walk; the raw-text screen and the READ ONLY transaction limit the damage. Review focus.
- `render_screen` starts a Textual app headless inside the server process; if it cannot run without a terminal, the ticket is re-scoped to a subprocess (supervisor decision, recorded here).
- `tl new` writes into the repository; every run is all-or-nothing and never overwrites.
- Another workstream edits `packages/tl-cli/src/tl_cli/main.py` (A adds `config`, B adds `types`); the merge conflict is one import line and one `add_typer` line.
- GitHub Actions cannot be run here: the CI review is checked by running each job's commands locally, and the report says so.

## Blocked / Decision
(none)
