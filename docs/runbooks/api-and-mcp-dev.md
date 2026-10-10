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
