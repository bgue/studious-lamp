# Report — P0-I8 workstream C: agent-dev baseline

Branch: `p0/i8c` (base `p0/i8`, `p0/i8` merged in once). Plan: `docs/tickets/P0-I8/README-C.md`. Demo: `just demo P0-I8-C`. Runbook: `docs/runbooks/dev-mcp.md`.

## Outcome
Objective met: yes. A coding agent can run the dev MCP server (`python -m tl_mcp.dev`, stdio, dev data only), use its seven tools and its resources, and scaffold a module, a record type and a projector whose output passes `just check` and its own tests. Every package's README.md and AGENTS.md was audited against the code. The CI workflow was reviewed against `04-gates.md` §1.

Two decisions differ from the fanout plan and need the orchestrator's note in the phase report: `query_db` is SQLite only (C4, after the security review), and the dev guard is stricter than D12 (C3).

Demo verified (`just demo P0-I8-C`, "DEMO OK"): the server over stdio lists its seven tools, answers `query_db`, `gen`, `rebuild_projections`, `render_screen`, `send_test_webhook`, `run_tests` and the resources, refuses a delete, a `wh_secret` read, stacked statements, a non-loopback webhook target, a path outside the test allow-list, a path in a document name, a file outside dev data, `TL_ENV=production` and a remote Postgres; then `tl new module`, `record-type` and `projector` into a temporary tree, ruff clean, the 6 generated tests pass, and a second run refuses to overwrite.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T40 `run_tests` | merged | 1 | 15 tests. Schema-level rejections (a marker outside the Literal, a 21st path) are not audited |
| T41 `gen` | merged | 1 | 8 tests. With `apply=true` the report describes the state after the write |
| T42 `rebuild_projections` | merged | 1 | 7 tests. Postgres test reads tables directly (C4) |
| T43 `seed` | merged | 1 | 7 tests. Supervisor added the API cleanup after a kill |
| T44 `send_test_webhook` | merged | 1 | 20 tests. Supervisor added userinfo redaction and IPv6 brackets |
| T45 `render_screen` | merged | 1 | 28 tests. Deviations accepted: `Path.as_uri`, a key-name check, `svg_truncated` default |
| T46 resources: schema graph, event catalog | merged | 1 | 17 tests |
| T47 resources: ADRs, runbooks, test reports | merged | 1 | 37 tests |
| T48 `tl new record-type` | merged | 1 | 16 provided tests pass (acceptance scoped, L-P0-I8C-7) |
| T49 `tl new projector` | merged | 1 | 15 provided tests pass |
| T50 docs for undocumented modules | merged | 1 | audit: 0 findings for tl-api, tl-lake, tl-sim |

Taken over: none. Abandoned: none. Supervisor pieces: S41 dev server core and guard (security-reviewed twice, see below), S42 scaffold engine and `tl new module`, S43 audit tool and the rules read, S44 CI review, S45 runbook, READMEs, AGENTS.md and learnings, S46 demo.

## Security review of S41
The first review found a HIGH full bypass of the Postgres guard: `ts_stat(text)` and `ts_rewrite` run a SQL string server-side, so a denied function name split with `||` read files, the role password hashes, `data_directory` and `wh_secret` through the superuser URL. READ ONLY does not help (all of those are reads). Also `loread`/`lowrite` (MEDIUM) and the `txid_*` family (LOW) passed the deny-list. Ruling and fix (commit 9a7b92d): `query_db` is SQLite only; a Postgres target is refused before any parsing; the DuckDB guard, the Postgres executor and the `duckdb` dependency were deleted; regression tests cover the three reviewer payloads, `ts_rewrite`, `loread`, `lowrite` and `txid_current_snapshot`. The re-review passed. Lesson: a function deny-list cannot cover Postgres (L-P0-I8C-1).
Review notes on T46 to T50 (LOW): the name and guard patterns used `match` with a trailing `$`, so `Weld.Created\n` passed; they use `fullmatch` now (commit 6fbb9b1) with tests that fail on the old code. The test for repository-relative SQLite paths failed when the checkout lives under `/tmp`; it now uses a repository root that is not under a temporary directory.

## Gates (on `p0/i8c` after merging `p0/i8`)
| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright, codegen drift, OpenAPI drift, licences) | green |
| `just test` | 4291 passed, 1 skipped, 2 failed in one 12-minute run on a loaded container; both failures were looked at and neither is a defect of this workstream (below) |
| `just test-tui` | green: 480 passed, 24 snapshots passed |
| `just test-parity` | not run: no adapter, ledger or projection code changed (`git diff p0/i8...p0/i8c` touches no `tl-adapters` file; `tl-core` and `tl-schema` changed only by one AGENTS.md line) |
| Demo `just demo P0-I8-C` | DEMO OK |
| CI workflow | not run: GitHub Actions cannot run in the build container. Each job's commands were run locally (`just check`, `just test`, `just test-tui`, `just test tests/property -k projection` 2 passed, `just test tests/contract` 6 passed, `just scan-secrets` 0 findings, `just audit-deps` no known vulnerabilities) and the YAML was parsed |

The two failures in the full `just test` run:
- `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog`: the base `p0/i8` gained the contract-only exemption (commit 5ca27ee) after this branch was cut. After merging `p0/i8` into `p0/i8c` the test passes.
- `packages/tl-api/tests/test_client_events.py::test_stream_events_without_a_cursor_is_live_only`: a live SSE test that starts a 0.5 s timer and waits; it timed out in a 12-minute run with several agents sharing the container. It passes alone (4 of 4 runs). No `tl-api` code changed. Treat it as load-sensitive.

## CI review (`.github/workflows/ci.yml` against `04-gates.md` §1)
| Gate | Before | Now |
|---|---|---|
| Lint, format, types; codegen drift | `check-and-test` job | same, with `--locked` sync |
| Unit and integration tests | `check-and-test` | same |
| Parity | `parity` job with a Postgres service | same, always runs, 30 min budget (L-P0-I5-A9); nightly schedule added |
| Projection determinism | only inside `just test` | own job `projection-determinism` |
| TUI snapshots | only inside `just test` | own job `test-tui` |
| Contract tests | only inside `just test` | own job `contract` |
| Schema classification | missing | still missing: `tl schema classify --base origin/main` has no command (Phase 1) |
| Security scan | licence check inside `just check` only | job `security`: `just scan-secrets` (new tripwire) and `just audit-deps` (`pip-audit` through `uvx`, Apache-2.0, not a project dependency) |
Also added: read-only permissions, `concurrency` cancel, per-job timeouts, `TL_ENV`. Path-conditional gating ("merge when adapters changed") is not expressed: every job runs on every PR, which is stricter.

## Deviations from the plan
- C1: modules are `packages/tl-modules/<name>` as the spec says; the root workspace needs `members` to add `packages/tl-modules/*` and `exclude = ["packages/tl-modules"]` (uv rejects the bare directory otherwise). Proved in the repository with `uv sync` and `just check`.
- C3: guard stricter than D12 (local Postgres host only; only the `options=-csearch_path=` URL parameter; `TL_ENV` unset, dev, test or ci). Accepted by the orchestrator.
- C4: `query_db` SQLite only (see the security review).
- Names are limited (module 20, record type class 30, projector name 40) so scaffolded lines stay within 100 columns for every accepted name.
- `tl new projector` scaffolds a derived `proj_<module>_<name>` table, never a `cur_*` table (C2).
- `tl-mcp` depends on the workspace package `tl-tui` (for `render_screen`); no third-party package entered the lock.

## Escalations and decisions
Orchestrator rulings applied: option (b) for the Postgres guard, the spec layout for modules, schema-level rejections not audited, `gen apply` semantics, seed API cleanup, webhook userinfo redaction and IPv6 brackets. Decisions C1 to C6 are in the plan.

## Learnings
Appended: L-P0-I8C-1 to L-P0-I8C-9 (Postgres deny-lists, seed.sh `setsid`, uv nested workspace, format-stable scaffolds, Textual/asyncio/sqlite URI traps, run `just check` before relaying a base, acceptance scoping across sibling tickets, `fullmatch`, audit tool exit status). Implementer proposals not recorded as entries: T41/T42 notes about test fixture names and a shadowed function name (ticket-specific); `xxd` missing (use `od -c`).

## Docs
Created: `docs/runbooks/dev-mcp.md` (listed in `docs/runbooks/README.md`), `docs/tickets/P0-I8/README-C.md` and tickets T40 to T50, ticket reports `docs/reports/P0-I8/P0-I8-T40.md` to `T50.md`. Updated: `packages/tl-mcp/README.md` and `AGENTS.md` (dev server), `packages/tl-cli/README.md` and `AGENTS.md` (`tl new`, scaffold), `packages/tl-api`, `tl-lake`, `tl-sim` READMEs (T50), `packages/tl-core/AGENTS.md` and `packages/tl-tui/AGENTS.md` (stale lines), root `AGENTS.md` (commands and paths). The audit tool `dev/tools/audit_docs.py` reports 0 findings for every package except `tl_core.settings` and `tl_core.extypes`, which belong to workstreams A and B.

## Follow-ups filed
- Postgres `query_db`: a non-superuser reader role (`tl_dev_reader`, no `wh_secret`, checked after connecting) and a function allow-list; then the guard may parse Postgres again. (LOW residual: `run_tests` and `seed` still pass the superuser `TL_PG_URL` to their children, by design.)
- `tl schema classify --base origin/main` and its CI job.
- `tl new` kinds not built: correspondence-domain, action, rule, enricher, connector, report, extractor; and an automatic edit of `module.yaml` imports when a record type is added (today a printed next step).
- Resources listed in brief 25.3 that are not served: module specs (`docs/modules/`), TUI screen snapshot listing, sample payloads beyond the event catalog. Tools not built: LinkML change validation (`linkml diff`), workflow and clock simulation, the extraction evaluation suite.
- `just seed` scales `s` and `m` have no measured cost; a timed-out seed is audited as `ok` (the result says `timed_out`).
- `render_screen` for a Postgres ledger (the embedded TUI client is SQLite only).
- The `test_stream_events_without_a_cursor_is_live_only` timing (widen the margin or poll for the first event).
- Docs tooling: `audit_docs.py --strict` in CI once WS-A and WS-B document their modules.

## Cost notes
Eleven implementer tickets, all passing review on the first round (one batch came back BLOCKED because of a supervisor lint error on the base, L-P0-I8C-6, and was re-reviewed after a base merge). One security review round with a HIGH finding and one re-review.
