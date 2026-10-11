# Report — P1-I0 workstream B: Postgres for the services

Branch `p1/i0b` (base `p1/i0`), supervisor session 2026-10-11. Plan and decisions: `docs/tickets/P1-I0/README-B.md` (B1 to B14). Operations: `docs/runbooks/run-on-postgres.md`.

## Outcome
Objective met: yes. The API server, the embedded TUI, the MCP server, the simulator and every `tl` command group take a SQLite path or a `postgresql://` URL from `--db` / `TL_DB`, through one factory, `tl_adapters.backend.open_backend`, and a test pins that no entry point imports the SQLite adapter directly. Parity tests cover each path on both adapters. This closes bullet 2 of `docs/reports/PHASE-0-AUDIT.md` (gap 1 of its section 5) and risk X7.

Demo path: `just demo P1-I0` is workstream A's (it runs on Postgres after this merge). The commands that show B's work are in README-B ("Demo") and in the runbook. Checked by hand on a scratch Postgres database (dropped afterwards):
- `just seed xs` with `TL_DB` a URL: `tl init --dev` creates `demo`/`demo`, `tl serve` starts, the simulator plays three days, `ok: 530 checks`;
- `demo`/`demo` signs in with `tl login` and creates a record as `user:demo`;
- the `north-unit-small` scenario's assistant wrote 4 events as `agent:sim-assistant` through the MCP child process, which got `TL_DB` and `TL_AGENT_TOKEN` in its environment.

## What was built
| Piece | Where |
|---|---|
| `open_backend(target)` -> `DatabaseBackend` (unit-of-work factory, ledger, bus, read-only snapshot connection, `close()`), `ledger_exists`, `connection_failure`, `BackendUnavailableError` | `packages/tl-adapters/src/tl_adapters/backend.py` |
| `as_target`, `is_postgres` (any letter case, `postgresql+pg8000://`), `display_target`, `target_key` | `packages/tl-adapters/src/tl_adapters/db.py` |
| SQLite `read_tx` refuses writes (`PRAGMA query_only`) | `packages/tl-adapters/src/tl_adapters/sqlite/engine.py` |
| API server on `open_backend`; `ApiSettings.db_path` is a `DbTarget` | `packages/tl-api/src/tl_api/{backend,main,settings}.py` |
| Root `tl --db`, `TlGroup` (one `error:` line for a failed connection), `tl init`, `tl projections rebuild`, `tl serve`, `tl tui` | `packages/tl-cli/src/tl_cli/{main,serve,tui}.py` |
| `EmbeddedClient.for_target`, `EmbeddedAuthenticator.for_target`, `target_uow_factory`; sign-in screen names the ledger without a password | `packages/tl-tui/src/tl_tui/{embedded,main}.py` |
| A's CLI session on any target: `target_key`, `ledger_exists`, no `is_local_target` | `packages/tl-cli/src/tl_cli/{session,login,admin,actor_hook,sim_agent}.py` |
| MCP server and simulator on a `DbTarget` | `packages/tl-mcp/src/tl_mcp/main.py`, `packages/tl-sim/src/tl_sim/{target,api,connector,cli,mcp_caller}.py` |
| Guard test: no import of `tl_adapters.sqlite` in `tl-api`, `tl-cli`, `tl-mcp`, `tl-sim`, `tl-tui` except `tl_cli/backup.py` | `tests/tools/test_no_sqlite_imports.py` |

## Supervisor commits (for the fresh-context review)
| Id | Commit | What |
|---|---|---|
| S30 | 815e5d2 | `open_backend`, `as_target`, `ledger_exists` |
| S31 | dfee372 | API server on `open_backend`; `tests/api` and a live-server SSE test on both adapters |
| S32 | fb34b6b | root `tl`, `tl serve`, `tl tui`, embedded client and its live feed on Postgres |
| S33 | db8b3e4 | provided parity tests: the CLI env fixtures take `new_db` |
| S34 | 24a5b71, 12d1475 | `record.py`, `events.py`; plan, tickets, runbook; learnings |
| S35a | a86108b, 75c5934 | review fixes: URL spellings, read-only SQLite snapshot, one error line, TLS pin test |
| S35b | d8e8eb6 | `sslmode` validated in `as_target` |
| S35c | e661bee | import guard test |
| S35 | 03f1f40, 649f828 | merge of `p1/i0` (A) with conflict resolution; MCP, simulator and CLI session on a target; parity tests for sign-in, actor rules, API and MCP |
| S36 | docs commit and this report | READMEs, AGENTS.md, runbooks, B13 and B14, learnings |

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T30 `tl record`, `tl events` | abandoned, folded into S34 | n/a | every other group's tests call `tl record create` (L-P0-I6A-5) |
| T31 `tl pset`, `tl wf` | merged (907699f, merge 90cc73f) | 1 | 63 tests on both adapters |
| T32 `tl link`, `tl schema reload` | merged (616f452, merge af0f841) | 1 | 40 |
| T33 `tl feed`, `tl proposal` | merged (82ee184, merge 9c3ded0) | 1 | 56 |
| T34 `tl config` | merged (89d7e2a, merge 9186ea3) | 1 | 89; the report miscounts one annotation (cosmetic) |
| T35 `tl types`, `tl types quarantine` | merged (238c64b, merge 3069327) | 1 | 66 |
| T36 `tl file` | merged (ac5151d, merge ccd9d49) | 1 | 32 |
| T37 `tl webhook` | merged (e974aa2, merge 178756a) | 1 | 36 |
| T38 `tl lake`; `tl backup sqlite` refuses Postgres | merged (b4683b7, merge f00ac86) | 1 | 48; the provided `pgbackrest` assertion matched only a path, now `use pgBackRest (` |
| T39 runbooks | merged (4aa4131, 4ee772c, merge cadfeff) | 1 (after a block) | blocked once on an acceptance `grep` the steps did not satisfy; ruling: add the Related link to two runbooks |

No ticket was taken over. A reference implementation of T31 to T38 (branch `p1/i0b-ref`, worktree `/home/user/wt/p1-i0b-ref`) was never needed and is not merged.

## Gates
| Gate | Result |
|---|---|
| `just check` | GATE_CHECK |
| `just test` | GATE_TEST |
| `just test-tui` | GATE_TUI |
| `just test-parity` | GATE_PARITY |
| Fresh-context reviews | S30 to S34: changes requested (no blockers), fixed in S35a and S35b, re-review pass. S35 (the merge and the session on a target): requested with this report |

## Deviations from plan
- T30 folded into S34; the MCP and simulator work waited for A (planned), and the import guard was added in two steps (S35c, then S35).
- The provided CLI tests are the existing test files converted to `new_db` (B9), not new tests. Only the entry points got new tests.
- The simulator may not import `tl_adapters` (brief 29.1; its boundary test failed in the first full run), so it carries the ledger as an opaque `LedgerTarget` (`tl_sim/target.py`) and only checks that a ledger *file* exists; the MCP child validates a URL. No dependency changed.
- `SQLite read_tx` became read-only (a behaviour change found by the review): 2317 tests that exercise it still pass.

## Escalations and decisions
- B13: the session of a Postgres ledger is keyed `pg:user@host:port/database[?options]`. ADR-0009 section 4 names only the file key; **the orchestrator should add the `pg:` key to the ADR** (an addendum, not a change of rule: a server target always needs a session and `--actor` is honoured only for the session's own actor, as A decided).
- Nothing else was escalated; no `schema/**` change (nothing to list under SCHEMA_APPROVALS); no new external dependency.

## Learnings
`L-P1-I0B-1` to `L-P1-I0B-6` (tests, process, security, tooling). Implementer proposals declined: none.

## Docs
- New: `docs/runbooks/run-on-postgres.md` (indexed in `docs/runbooks/README.md`); the plan `docs/tickets/P1-I0/README-B.md`; tickets T30 to T39; ticket reports `docs/reports/P1-I0/P1-I0-T31.md` to `T39.md`.
- Updated: `AGENTS.md` (rule 5); READMEs of tl-adapters, tl-api, tl-tui, tl-cli, tl-mcp, tl-sim; AGENTS.md of tl-adapters, tl-api, tl-tui, tl-cli, tl-mcp, tl-sim; runbooks `rebuild-projections`, `webhook-operations`, `lake-sync`, `object-store-reconciliation`, `postgres-local-setup` (T39), `tui-dev`, `api-and-mcp-dev`, `simulator`, `accounts-and-access`.

## Follow-ups filed
- `NotifyListener` (LISTEN/NOTIFY) is not wired into the API feed or the embedded feed: a write from another process arrives by the 0.25 s poll on both databases. Wiring it would cut that to about 50 ms at the cost of a connection and a polling thread per process.
- The API's Postgres pool is 5 connections plus 5 overflow; not measured under load (the Phase 0 benches ran the library, not the server).
- `tl migrate` (SQLite to Postgres) is still the human-gated P0-I5-T99; the supported route is `tl archive seal` and `tl restore --from-archive`.
- `query_db` and `render_screen` of the dev MCP server stay SQLite only (decision C4).
- A's demo `dev/demos/P1-I0.sh` and the increment report `docs/reports/P1-I0.md` follow this merge (A).

## Cost notes
Nine tickets in five batches of two (one was folded into the base), each one implementer run and one review run; one block (T39) and no retry. Supervisor time went to the factory, the review fixes and the merge with A.
