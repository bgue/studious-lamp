# Increment plan: P1-I0 workstream B, Postgres for the services

Status: in-progress
Supervisor session: 2026-10-11
Brief sections: §14 (storage), §16 Phase 1 and the Phase 0 audit (`docs/reports/PHASE-0-AUDIT.md` bullet 2), §24 (operations)
Branch: `p1/i0b` (worktree `/home/user/wt/p1-i0b`), based on `p1/i0`; fanout plan `docs/tickets/P1-I0/FANOUT.md`; owner decisions `docs/adr/0008-phase1-owner-decisions.md`

## Objective
The API server, the TUI and the operator commands run on Postgres as well as SQLite. One backend factory, `open_backend(target)`, takes a SQLite path or a `postgresql://` URL and returns the unit-of-work factory, the change feed (ledger and in-process bus), a read-only snapshot connection and `close()`. `tl serve`, `tl tui`, `tl webhook`, `tl lake`, `tl file` and every other `tl` command group take the database from the root `--db` / `TL_DB`, which now accepts either kind of target. Parity tests run each path on both adapters.

This closes the first gap of the Phase 0 audit (§5, "the server, TUI and operator commands run on SQLite only") and risk X7 in `docs/reports/RISKS.md`. It touches no authentication code: workstream A replaces `tl_api/auth.py`, `tl_api/tokens.py` and `tl_core/auth`, and merges first.

## Demo
Workstream B writes no demo (FANOUT: A writes `dev/demos/P1-I0.sh` after B merges so that the demo runs on Postgres). The commands that show B's work, from the repository root, with a scratch database:
```
export TL_DB='postgresql://postgres:postgres@localhost:5432/tl_p1i0b_demo?sslmode=disable'
uv run tl init                                   # initialised postgresql://postgres:***@localhost:5432/...
uv run tl record create --project P123 --key REC-1 --title "Pour slab"
uv run tl serve &                                # the API on Postgres; GET /records?scope=project:P123 lists REC-1
uv run tl tui                                    # the embedded TUI on Postgres; live marks when the API writes
uv run tl file put ./some.pdf --project P123 --record REC-1
uv run tl lake sync && uv run tl lake status
uv run tl webhook ls --project P123
```
The runbook `docs/runbooks/run-on-postgres.md` has the full procedure and what differs from SQLite.

## Decisions
| # | Decision |
|---|---|
| B1 | **One factory, in the adapters package.** `tl_adapters.backend.open_backend(target)` returns a `DatabaseBackend`. It lives beside `tl_adapters.db` because choosing an adapter is adapter code (AGENTS rule 5). `tl_api.backend.open_backend` re-exports it for the API; the `Backend` protocol of `tl_api` is unchanged and `DatabaseBackend` satisfies it. |
| B2 | **A target is a `DbTarget`.** `tl_adapters.db.as_target(text)` keeps `postgresql://` and `postgres://` text whole and turns anything else into a `Path`. Before it, the CLI did `Path(url)`, which collapses `//` and mangles the password. The root `tl` callback sets `ctx.obj` to a `DbTarget`; every command group reads it. |
| B3 | **The driver's `sslmode` mapping is unchanged** (P0-I8-D, L-P0-I8D-1). The URL reaches `postgres.engine.split_url` as written: `disable`, `require`, `verify-ca` and `verify-full` are mapped, any other value is a `ValueError` that the entry points turn into `error: ...`. Without `sslmode` the driver default (TLS) applies. The runbook tells an operator to put `?sslmode=disable` on a loopback URL and a verifying mode on a remote one. |
| B4 | **The password is never printed.** Output, errors and logs use `display_target(target)` (`postgresql://user:***@host/db`). `BackendUnavailableError` names the target without its password and the server's own message (`password authentication failed for user "x"`, `database "y" does not exist`), never the driver's text. The runbook recommends `TL_DB` over `--db`: a command line is visible in the process list, as for tokens. |
| B5 | **A missing ledger is not created by a read.** `ledger_exists(target)` is a file check for SQLite and `to_regclass('events')` for Postgres. `tl serve` and `tl lake` report `no ledger at ...: run tl init`; `tl init` is the only command that creates one. An unreachable server is a different message (`cannot reach the database ...`) and a different exit code path from "run tl init". |
| B6 | **Postgres uses a pooled engine in a server.** `open_backend` builds `make_engine(url, pooled=True)` (5 connections, 5 overflow, pre-ping). Short CLI commands keep opening one engine per unit of work (`tl_adapters.db.open_uow`, `NullPool`). |
| B7 | **The live feed on Postgres polls.** `FeedHub` (API) and `EmbeddedFeed` (TUI) already take any `Ledger` and `Bus`; they get them from the backend. Writes made by this process arrive at once through the bus; writes made by another process arrive by the 0.25 s poll. `NotifyListener` (LISTEN/NOTIFY wake-ups) is available but not wired: it would cut the cross-process delay from 250 ms to about 50 ms at the price of one more connection and a busy poll thread per process. Follow-up, not needed for the exit criteria. |
| B8 | **`tl backup sqlite` stays SQLite-only** and refuses a URL with a pointer to pgBackRest and `tl archive seal`. Moving data between the two databases is `tl archive seal` and `tl restore --from-archive` (the database-independent path); there is still no `tl migrate` (a human gate, filed as P0-I5-T99). |
| B9 | **Tests: the existing suites become the parity suites.** The env fixtures of the CLI test files, the TUI embedded-client tests and the API round-trip suite take their ledger from `new_db`, so each runs on SQLite by default and on both with `--adapters sqlite,postgres` (`just test-parity`). New tests cover the entry points: `packages/tl-adapters/tests/test_backend.py`, `tests/api/test_server_on_backend.py`, `packages/tl-cli/tests/test_cli_target.py`, `packages/tl-tui/tests/test_main_target.py`. Raw `sqlite3` helpers in CLI tests were rewritten with the adapter's unit of work, bound booleans and full ISO timestamps (the rules in `packages/tl-adapters/AGENTS.md`). |
| B10 | **`ApiSettings.db_path` keeps its name** and is typed `DbTarget`. A rename would touch every test and conflict with workstream A's edits to the same file; the field has a comment. |
| B11 | **Not in this increment:** the MCP server's `--db` and the simulator's ledger path (`tl_mcp/main.py`, `tl_sim`) are edited by workstream A for agent tokens and seeded accounts; B takes them after A merges (see *Order of work*). The dev MCP server's `query_db` and `render_screen` stay SQLite-only (decision C4). `just seed` and the demo scripts are A's. |
| B12 | **Review fixes (fresh-context review of S30 to S34).** `as_target` and `is_postgres` match the scheme in any letter case and accept `postgresql+pg8000://`; any other `scheme://` value, a URL without a user, and an unescaped `@` in the password raise `ValueError` without repeating the value. `display_target` drops `password` and `sslpassword` query parameters and shows `<invalid database URL>` for a URL it cannot parse safely. SQLite `read_tx` sets `PRAGMA query_only=ON` for the transaction (and OFF after), so `DatabaseBackend.read_connection` and the readonly unit of work refuse raw writes as Postgres does (25006). The root `tl` group (`TlGroup`) turns any connection failure (`connection_failure`: refused, wrong password, missing database) into one `error:` line with exit 1; `tl_tui.main.main` and `tl_api.main.main` do the same for a bad or unreachable target. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S30 | `tl_adapters.backend` (`open_backend`, `DatabaseBackend`, `ledger_exists`, `BackendUnavailableError`) and `tl_adapters.db.as_target`; `packages/tl-adapters/tests/test_backend.py` | Adapter boundary, new public interface of the adapters package | fresh-context review at the end of the workstream | done |
| S31 | The API server on `open_backend` (`tl_api/backend.py`, `settings.py`, `main.py`); `tests/api` made a parity suite; `tests/api/test_server_on_backend.py` | Wiring of a long-running service, change-feed behaviour | same | done |
| S32 | The root `tl` callback, `tl init`, `tl projections rebuild`, `tl serve`, `tl tui`; `EmbeddedClient.for_target`; `tl_tui.main`; parity conversion of the embedded-client tests | Entry points every command uses; conflicts with A in `tl_cli/main.py` | same | done |
| S33 | The provided tests of T30 to T38 (CLI env fixtures on `new_db`, adapter-based helpers) | Test specification for the tickets | n/a | done |
| S34 | `tl record` and `tl events` on `DbTarget` (`record.py`, `events.py`) | Every other group's provided tests call `tl record create`, so on Postgres nothing else could pass first (T30 folded in) | same | done |
| S35 | After A merges: `tl_mcp/main.py` and `tl_sim` on `open_backend`; the guard test that no command imports `tl_adapters.sqlite` (except `backup`) | Touches A's files | same | planned |
| S35a | Fixes of the review of S30 to S34 (B12) | Security-relevant handling of credentials in URLs | short re-review | done |
| S36 | Runbook `docs/runbooks/run-on-postgres.md` (written; MCP and simulator sections after S35); package READMEs and AGENTS.md; learnings; the report | Docs of the new operating mode | n/a | runbook written |

## Tickets
T31 to T38 swap one command group each from the SQLite-only `open_uow` and a `Path` to `tl_adapters.db.open_uow` and a `DbTarget`. Each is small (a few lines per file; the file count is above the checklist's five because the test files are provided and read-only). A scratch reference implementation of every ticket is kept on the branch `p1/i0b-ref` (not merged) as the takeover path (L-P0-I2-3).

| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T30 | `tl record`, `tl events` on either database | haiku | S30, S32, S33 | abandoned | Folded into the base as S34: every other group's tests call `tl record create` (L-P0-I6A-5) |
| T31 | `tl pset`, `tl wf` | haiku | S34 | ready | |
| T32 | `tl link`, `tl schema reload` | haiku | S34 | merged | pass on the first review, 616f452, merge af0f841; 40 tests on both adapters |
| T33 | `tl feed`, `tl proposal` | haiku | S34, T32 (its tests call `tl link`) | ready | |
| T34 | `tl config` | haiku | S34 | merged | pass on the first review, 89d7e2a, merge 9186ea3; 89 tests on both adapters; report miscounts one annotation (cosmetic) |
| T35 | `tl types`, `tl types quarantine` | haiku | S34, T34 (its settings test calls `tl config`) | ready | |
| T36 | `tl file` (put, get, ls, reconcile) | haiku | S34 | ready | |
| T37 | `tl webhook` | haiku | S34 | ready | |
| T38 | `tl lake`; `tl backup sqlite` refuses Postgres | haiku | S34 | ready | |
| T39 | Runbooks that say the ledger is a SQLite file | haiku | T31 to T38 | draft | |

**Haiku-ability checklist (`01-tiers.md` §6), all tickets.** (1) Files to read: the one or two source files, the root callback and the provided tests: more than six for T34 and T35 but each test file is only a fixture and call pattern the ticket does not ask to understand. (2) Every interface exists in the repo (`tl_adapters.db`, `make_uow_factory`). (3) The provided tests are the spec, with the pass count of the reference run. (4) The diff is 10 to 30 lines per ticket (the reference diff: 287 insertions and 212 deletions over all 45 files, tests included). (5) None of the Sonnet-authored rows (no engine, migration or auth). (6) No `schema/**`, migration, dependency or public-interface change. (7) A reviewer verifies it from the diff and the commands. The file counts are above five because the provided tests are read-only context, not part of the diff.

**Batches of two, with the dependency rule (L-P0-I6A-5).** B1 T32 + T34; B2 T33 + T35 (their tests call `tl link` and `tl config`, merged in B1); B3 T31 + T36; B4 T37 + T38; B5 T39.

## Order of work
1. S30 to S33 on the base (done), then `just check` before the first relay (L-P0-I8C-6).
2. Batches of two tickets (usage limits, L-P0-I8-O1): T32+T34, T33+T35, T31+T36, T37+T38, T39. Each ticket: implementer, then a reviewer in a fresh context; merge on `pass` with a merge commit; remove the worktree.
3. After A merges into `p1/i0`: merge `p1/i0` into `p1/i0b`, resolve conflicts in `tl_api/main.py` and `tl_cli/main.py` keeping both sides' behaviour, then S34.
4. Gates: `just check`, `just test`, `just test-tui`, `just test-parity`, one at a time.
5. Docs, learnings, report `docs/reports/P1-I0-B.md`.

## Risks and escalation triggers
- A and B edit `tl_api/main.py` and `tl_cli/main.py`. The conflict is B's to resolve; both behaviours stay.
- A provided test that fails on Postgres after the swap means a real adapter or service defect. The reference run had none after the SQL helpers were rewritten, but the full `just test-parity` has not run on the converted files yet.
- The pooled engine (10 connections) bounds concurrent requests of the API on Postgres. A burst of long-running reads queues; the pool timeout is 30 s. Not measured under load (the Phase 0 benches ran the library, not the server).

## Blocked / Decision
(none yet)
