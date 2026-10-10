# Runbook — Run the API, the event stream and the MCP server on the dev ledger

Purpose: start the REST API with an SSE stream and the MCP read server against the SQLite dev ledger, create a dev token, and recover from the usual first-run problems. Brief: §4, §11, §18. Identity is the dev-only stub of ADR-0005.

## When to use
- Trigger: a developer or demo needs the HTTP API, a remote TUI, a script or an AI agent to read or write the dev ledger.

## Before you start
- Access needed: the repository, `uv` and `just`.
- Safe to run during business hours: yes, but only on loopback. The Phase 0 API has no real authentication and no permission model. Never expose it.

## Steps
1. Create the ledger and a token:
   ```
   uv run tl init
   uv run tl dev token add user:alice          # prints the token; stored in ./dev/data/tokens.json (mode 0600)
   ```
   Expected: `initialised ./dev/data/tl.db`, a token on stdout and `added token for user:alice` on stderr. Tokens are for `user:<id>` or `agent:<id>`.
2. Start the API:
   ```
   just serve                                   # 127.0.0.1:8765
   export TOKEN=<the token>
   curl -s localhost:8765/health
   curl -s -H "Authorization: Bearer $TOKEN" 'localhost:8765/records?scope=project:P123&q=status:open'
   ```
   Expected: `{"status":"ok"}`, then a JSON list. Use `just serve --port 9000` for another port.
3. Follow changes (SSE). Writes from the CLI or an embedded TUI on the same file arrive within about a second:
   ```
   curl -sN -H "Authorization: Bearer $TOKEN" localhost:8765/stream
   curl -sN -H "Authorization: Bearer $TOKEN" -H 'Last-Event-ID: 41' localhost:8765/stream   # resume after seq 41
   ```
   Expected: `id:`, `event:` and `data:` lines; `: keep-alive` when idle.
4. Start the MCP server for an agent (stdio; the client launches it):
   ```
   uv run python -m tl_mcp --actor agent:triage
   ```
   Expected: it waits on stdin. An MCP client config runs this command; the tools are `search_records`, `get_record`, `get_links` and `trace`.
5. Python client:
   ```
   from tl_api.client import ApiClient
   api = ApiClient("http://127.0.0.1:8765", token)
   api.query_records("project:P123", "status:open")
   ```

## Give an agent `lake_query`
The MCP server also exposes `lake_query`, a read-only SQL tool over the DuckLake copy of the ledger (see `docs/runbooks/lake-sync.md`). It is a tool in addition to the ones listed in step 4. Every call is logged. In Phase 0 the actor is fixed per server by `--actor`, every actor may call the tool, and there is no permission model yet (ADR-0005 dev stub). The server opens the lake on each call, so sync the lake first (step 2).

1. Start the MCP server with the lake (stdio; the MCP client launches it):
   ```
   uv run python -m tl_mcp --actor agent:analyst --lake-dir ./dev/data/lake
   ```
   Expected: the process waits on stdin. The server is read-only. `--lake-dir` defaults to `TL_LAKE_DIR`, else `./dev/data/lake`. The lake directory may not exist yet. `--actor` is written as `caller` in the audit log.

2. Fill the lake:
   ```
   uv run tl lake sync
   ```
   Expected: the sync reports the seq range it copied, or that the lake is up to date (see `docs/runbooks/lake-sync.md`, step 2). Before the first sync, `lake_query` answers with a tool error that tells you to run `tl lake sync`.

3. Call the tool from the agent's MCP client. Arguments are `sql` (required, 1 to 20 000 characters) and `limit` (optional, 1 to 1000, default 100):
   ```
   lake_query  {"sql": "SELECT * FROM cur_core_record", "limit": 20}
   ```
   The `sql` must be one SELECT (or WITH ... SELECT) over `events`, `cur_core_record`, `links`, `pset_values` and `_tl_sync`. The agent can read the tables and columns from the resource `tl://lake/schema` (JSON).
   Expected: a JSON answer with `columns`, `rows`, `row_count`, `truncated`, `truncated_by`, `limit`, `as_of_seq`, `snapshot_id` and `as_of`. `truncated_by` is `limit` when more rows existed, or `bytes` when the answer reached 1 MiB. `as_of_seq` is the ledger seq the lake reflects; the lake can be behind the ledger until the next sync. Time travel uses the snapshot ids in `_tl_sync`:
   ```
   lake_query  {"sql": "SELECT * FROM cur_core_record AT (VERSION => <snapshot_id>)", "limit": 20}
   ```
   A query that runs longer than 30 s is interrupted.

4. Read a refusal. The tool refuses statements that are not a single read-only SELECT. A refused call returns a tool error whose text starts with `refused:`:
   ```
   lake_query  {"sql": "DELETE FROM events"}
   ```
   Expected: an error starting with `refused:`, and no change to the lake or the ledger. Refused by design: DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET, EXPLAIN, stacked statements, the file functions `read_csv`, `read_parquet`, `read_text` and `glob`, table names that look like paths, and other catalogs. A statement that is allowed but fails in DuckDB returns a tool error with the DuckDB error class and a short message. Fix the SQL to one SELECT over the tables in step 3 and call again.

5. Read the audit log. Every call, accepted or refused, appends one JSON line (replace the path if you pass another `--lake-dir`):
   ```
   tail -n 20 ./dev/data/lake/lake_query.log.jsonl
   ```
   Expected: one line per call with `ts`, `caller` (the `--actor`), `sql`, `limit`, `outcome` (`ok`, `refused` or `error`), `detail`, `error_class`, `rows`, `truncated`, `as_of_seq`, `snapshot_id` and `elapsed_ms`. The refused call from step 4 has `outcome` `refused`.

## Verify
- `just demo P0-I4-C` runs all of the above on a temporary ledger and fails on any unmet expectation.
- `uv run python -m tl_api.openapi --check` is silent when `docs/reference/openapi.json` matches the routes.

## Roll back
- Stop the server (Ctrl+C). Events are never deleted. To revoke a token, delete its line from `dev/data/tokens.json` (it is re-read on change). To start over delete `dev/data/tl.db` and run `uv run tl init`.

## Troubleshooting
- `error: no ledger at ...; run tl init first`: create the ledger (step 1) or set `TL_DB`.
- `has mode 0644 ... chmod 600`: the token file is readable by others; run `chmod 600 dev/data/tokens.json`.
- `refusing to bind '0.0.0.0'`: only loopback is allowed. `--insecure-dev` accepts a public bind, logs a warning on every request, and is for a throwaway container, not a network.
- 401 on every request: the token is missing, unknown, or from another token file (`TL_TOKENS`).
- File routes answer 503: no object store is configured; set `TL_ENV=dev` or `TL_OBJECT_SECRET` (and `TL_OBJECT_ROOT`).
- 503 `unavailable` on `/stream`: 32 streams are open; close idle ones.

## Related
- ADR-0005 (dev-only identity), `docs/tickets/P0-I4/README-C.md` (contracts), `docs/reference/openapi.json`, `docs/runbooks/tui-dev.md`, `docs/runbooks/object-store-reconciliation.md`.
