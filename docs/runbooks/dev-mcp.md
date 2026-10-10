# Runbook — Run the dev MCP server for coding agents

Purpose: start `python -m tl_mcp.dev`, connect a coding agent to it, use its tools and resources, and understand what it refuses. Brief: §25.3. It works on dev data only (FANOUT P0-I8 decision D12) and is not the product MCP server (`docs/runbooks/api-and-mcp-dev.md`).

## When to use
- Trigger: a coding agent should inspect the running system (test results, codegen drift, the dev ledger, a TUI screen) and not only the source.

## Before you start
- Access needed: the repository, `uv` and `just` (the SessionStart hook installs both). Native Postgres is only needed for tests marked `parity`.
- Safe to run during business hours: yes. It reads and writes the dev ledger only, and is stdio only (no port).
- It refuses to start when `TL_ENV` is anything but unset, `dev`, `test` or `ci`, and for any database that is not dev data:
  | Target | Allowed |
  |---|---|
  | SQLite file | Under the repository's `dev/` directory or a temporary directory (symlinks are resolved first) |
  | Postgres URL | Host on this machine, database name starting `tl_test` or `tl_dev`, no URL parameters except `options=-csearch_path=<schema>` |

## Steps
1. Create a dev ledger if there is none (`dev/data/tl.db`, git-ignored):
   ```
   uv run tl init
   ```
2. Start the server (an MCP client config runs this command; it waits on stdin):
   ```
   uv run python -m tl_mcp.dev                      # database from TL_DB, default dev/data/tl.db
   uv run python -m tl_mcp.dev --db /tmp/scratch.db # another dev file
   ```
   Expected: no output. A refused database prints `error: refused: ...` and exits 2.
3. Use the tools (all arguments are bounded; refusals start with `refused:`):
   | Tool | Does | Notes |
   |---|---|---|
   | `run_tests` | One filtered pytest in a child process, no shell | `paths` under `packages/<pkg>/tests` or `tests`, `marker` `parity` or `requires_postgres`, `keyword`, `adapters`; at least one filter; the full output is stored in `dev/data/test-reports/` |
   | `gen` | Runs the generators in memory and reports drift (`missing`, `differs`, `stale`) with a short diff | `apply=true` regenerates (what `just gen` does); the answer then describes the state after the write |
   | `query_db` | One read-only SELECT or WITH on the dev SQLite ledger | At most 1000 rows, 1 MiB, 10 s; `wh_secret` cannot be read; a Postgres target is refused (follow-up, deviation C4) |
   | `rebuild_projections` | Resets the named projectors (default all) and replays the ledger | SQLite or a dev Postgres; one transaction; the ledger is never changed |
   | `seed` | Runs `dev/seed/seed.sh` (the simulator through a short-lived API) | `scale` `xs` (about 15 s), `s`, `m`; adds one more simulated project per call; SQLite only |
   | `send_test_webhook` | Sends one signed catalog sample to a receiver on this machine | Loopback only (`localhost`, `127.x.x.x`, `::1`), no redirects, proxy variables ignored; without `secret` a fresh one is returned |
   | `render_screen` | Runs the TUI headless on a copy of the ledger and returns an SVG and the screen text | Keys never write to the real ledger; SQLite only; the SVG is also saved in `dev/data/snapshots/` |
4. Read the resources:
   | URI | Content |
   |---|---|
   | `tl://dev/schema-graph` | Classes, enums and their edges of the core LinkML schema (JSON) |
   | `tl://dev/event-catalog`, `tl://dev/event-catalog/index`, `tl://dev/event-sample/{event_type}` | The generated event catalog page, its index and one sample per event type |
   | `tl://dev/adrs`, `tl://dev/adr/{name}` | Index and text of the ADRs (`name` is the file name without `.md`) |
   | `tl://dev/runbooks`, `tl://dev/runbook/{name}` | Index and text of the runbooks |
   | `tl://dev/test-reports`, `tl://dev/test-report/{name}` | Index (newest first) and text of the reports `run_tests` stored |
5. Read the audit file after a session:
   ```
   tail -n 20 dev/data/dev-mcp.log.jsonl
   ```
   Expected: one JSON line per call with `tool`, `outcome` (`ok`, `refused`, `error`, `failed`) and the arguments (long values cut; URL passwords shown as `***@`). A secret is never written.

## Verify
- `uv run pytest packages/tl-mcp/tests/test_dev_server.py -q` starts the server over stdio and calls `query_db`.
- `just demo P0-I8-C` drives the server over stdio and shows the refusals.

## Roll back
- The tools that write (`seed`, `rebuild_projections`, `gen` with `apply`) change dev data and generated files only. Delete `dev/data/tl.db` and run `uv run tl init` to start the ledger over; `git checkout packages/tl-schema/src/tl_schema/generated` undoes a `gen` with `apply`.

## Troubleshooting
- `error: refused: a SQLite file must be under the repository's dev/ directory or a temporary directory`: the `--db` path (after symlinks) is elsewhere. Copy the file under `dev/data/`.
- `error: TL_ENV='production'`: unset it. The dev server never runs against a real environment.
- `refused: query_db reads SQLite dev databases only in Phase 0`: the target is Postgres. Use `rebuild_projections` or `run_tests` for Postgres, or point the server at a SQLite file. A Postgres reader needs a non-superuser role and a function allow-list (follow-up).
- `run_tests` says to name a filter: the whole suite is `just test`.
- `seed` returns `timed_out`: raise `timeout_s` (up to 1800); the API it started is stopped.

## Related
- `packages/tl-mcp/README.md` (the dev server section), `docs/tickets/P0-I8/README-C.md` (decisions C1 to C6), `docs/runbooks/api-and-mcp-dev.md`, `docs/runbooks/rebuild-projections.md`, `docs/runbooks/simulator.md`.
