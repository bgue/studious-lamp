# Runbook — run the API, the TUI and the operator commands on Postgres

Purpose: point `tl serve`, `tl tui`, `tl webhook`, `tl lake`, `tl file` and every other `tl` command at a Postgres database instead of a SQLite file, and know what is different. Brief: §14, §24. Decisions: `docs/tickets/P1-I0/README-B.md` (B1 to B11).

## When to use
- Trigger: a developer, a demo or a deployment wants the server, the TUI or a worker on Postgres.
- Trigger: a command printed `cannot reach the database ...` or `no ledger at ...: run tl init`.

## Before you start
- Access needed: a Postgres 16 database and a role that may create tables in it. For a local one see `docs/runbooks/postgres-local-setup.md` (native cluster, user `postgres`, password `postgres`, port 5432).
- Use a database of your own. `tl_test` belongs to the parity suite and `tl_pytest_*` databases to a running test session; do not point a ledger at them.
- Python dependencies: `uv sync --all-packages`. The driver is `pg8000` (BSD-3-Clause).
- Safe to run during business hours: yes. `tl init` is idempotent. Every command below is a read or an ordinary write of the ledger.

## Steps
1. Create the database once. Locally:
   ```
   sudo -u postgres psql -c "CREATE DATABASE tl_dev"
   ```
   Expected: `CREATE DATABASE`.
2. Name it in `TL_DB`. A URL carries the password, and a command line is visible in the process list, so prefer the variable to `--db`:
   ```
   export TL_DB='postgresql://postgres:postgres@localhost:5432/tl_dev?sslmode=disable'
   ```
   - `sslmode` is read by the adapter (`postgres.engine.split_url`): `disable` (no TLS; use it on a loopback link, where TLS costs about a quarter of every statement), `require` (TLS, certificate not checked), `verify-ca`, `verify-full` (use one of these for a remote server). `allow` and `prefer` are refused with `unsupported sslmode`, because they can fall back to plain text. With no `sslmode` the driver default applies, which tries TLS.
   - A password with special characters is percent-encoded (`@` is `%40`); an unescaped `@` is refused. A `?password=` query parameter is not read by the adapter and is hidden in every message.
   - To keep several ledgers in one database, give each its own schema: `psql -c "CREATE SCHEMA tl_demo"` and add `&options=-csearch_path%3Dtl_demo` to the URL (`tl_adapters.postgres.admin.schema_url` builds it).
3. Create the schema (the events table, the triggers, the projection tables):
   ```
   uv run tl init
   ```
   Expected: `initialised postgresql://postgres:***@localhost:5432/tl_dev?sslmode=disable`. Running it again prints the same line. The password is never printed; every command shows `***`.
4. Check it:
   ```
   uv run tl record create --project P123 --key REC-1 --title "Pour slab"
   uv run tl ledger verify
   ```
   Expected: `created <id>`, `key REC-1`, `version 1`, then `verified ledger postgresql://postgres:***@...: 1 events, hash chains intact`.
5. Run the services and workers on it. All of them read `TL_DB`:

   | Command | What it does on Postgres |
   |---|---|
   | `uv run tl serve` (or `just serve`) | The REST API and the SSE stream. One pooled engine (5 connections, 5 more under load). Writes made by another process, such as the CLI, reach `GET /stream` within the 0.25 s poll |
   | `uv run tl tui` (or `just tui`) | The embedded TUI: its own engine and in-process bus, live marks for its own writes at once and for other processes' within 0.25 s |
   | `uv run tl webhook run` | The webhook dispatcher and delivery worker. Other `tl webhook` commands manage subscriptions |
   | `uv run tl lake sync` (`--watch`) | Reads the ledger in one `REPEATABLE READ READ ONLY` snapshot per sync |
   | `uv run tl file put\|get\|ls\|reconcile` | File rows in the ledger; the bytes stay in the object store (`TL_OBJECT_ROOT` or S3) |
   | `uv run tl projections rebuild` | Replays the ledger in one transaction. On Postgres this is statement-bound: about 160 events a second (`docs/reports/P0-I8-perf.md`), so 100k records take about 40 minutes |
   | `uv run tl archive seal\|verify`, `tl restore`, `tl ledger verify` | Take a URL with `--db` or the root `TL_DB` |

6. Take a backup. `tl backup sqlite` refuses a Postgres ledger and says so (`error: tl backup sqlite takes a SQLite ledger; ...`). Use pgBackRest (`docs/runbooks/pgbackrest-restore.md`) for the database and `tl archive seal` (`docs/runbooks/ledger-archive-and-verify.md`) for the portable, signed copy.
7. Move a ledger from SQLite to Postgres, or back. There is no `tl migrate` (a human gate, `docs/tickets/P0-I5/T99-migrate-sqlite-to-postgres.md`). Seal the archive from the source and restore it into an empty target:
   ```
   uv run tl --db ./dev/data/tl.db archive seal
   uv run tl restore --from-archive ./dev/data/archive --db "$TL_DB"
   ```
   See `docs/runbooks/restore-from-archive.md` for the keys and the checks it makes.

## Verify
- `uv run tl ledger verify` prints `hash chains intact`.
- `curl -s localhost:8765/health` prints `{"status":"ok"}` with `tl serve` running; `GET /records?scope=project:P123` with a token lists `REC-1`.
- `psql "$TL_DB" -c "SELECT count(*) FROM events"` equals the event count `tl ledger verify` printed.

## Roll back
- Stop the service. Point `TL_DB` back at a SQLite path (`./dev/data/tl.db`); nothing else changes, because the two ledgers are independent files and databases.
- To start the Postgres ledger over, drop the database (`sudo -u postgres psql -c "DROP DATABASE tl_dev"`) and run `tl init` again. Events are immutable: there is no command that deletes some of them.

## What is different from SQLite
| Topic | SQLite | Postgres |
|---|---|---|
| Writers | One at a time (`BEGIN IMMEDIATE`, busy timeout) | One at a time (an advisory lock); a writer that waits longer than 10 s gets `LockTimeoutError` and can retry; readers never wait |
| `tl init` | Creates the file and its parent directory, then the tables | Creates the tables only. The database (and a schema, if the URL names one) must already exist: `cannot reach the database ...: database "x" does not exist` otherwise |
| "Is there a ledger?" (`ledger_exists`, used by `tl serve`, `tl lake`, `tl tui` and the extension-type attach) | The path is a file. Any file counts, even an empty one | The connection's schema has an `events` table (looked up through `search_path`). A server that cannot be reached is an error, never "no ledger" |
| Missing ledger | `tl serve` and `tl lake` say `no ledger at <path>: run tl init`; a read never creates the file | The same message when the schema has no `events` table; an unreachable server, a wrong password or a missing database is `cannot reach the database <url without password>: <server message>` (one `error:` line, exit 1, from every command) |
| Accepted `TL_DB` values | A file path | A path, or a URL starting `postgresql://`, `postgres://` or `postgresql+pg8000://` (any letter case) with a user name. Any other `scheme://` value, an unescaped `@` in the password and a URL without a user are refused (`error: ...`, exit 2) with no echo of the value; nothing is created |
| Connections | One engine per process, one connection per transaction | Servers and the embedded TUI keep a pool of up to 10; each `tl` command opens its own and closes it |
| Live updates between processes | Poll of the file, 0.25 s | Poll of the ledger, 0.25 s. `NotifyListener` (LISTEN/NOTIFY) exists in `tl_adapters.postgres.notify` but is not wired, so the delay is the poll interval |
| Dev tools | `query_db` and `render_screen` of the dev MCP server work on a copy of the file | Both refuse a Postgres target (`docs/runbooks/dev-mcp.md`, decision C4) |
| Timestamps and booleans in hand-written SQL | Text and 0/1 are accepted | Use full ISO timestamps and `TRUE`/`FALSE` or bound values (`packages/tl-adapters/AGENTS.md`) |

## Related
- `docs/runbooks/postgres-local-setup.md` (start the cluster, the parity suite, scratch schemas).
- `docs/runbooks/api-and-mcp-dev.md`, `docs/runbooks/tui-dev.md`, `docs/runbooks/webhook-operations.md`, `docs/runbooks/lake-sync.md`.
- `docs/adr/0002-build-environment-constraints.md` (native Postgres 16, no Docker daemon).
- `packages/tl-adapters/README.md` (`open_backend`, `as_target`, `ledger_exists`).
