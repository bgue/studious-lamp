# tl-mcp (`tl_mcp`)

The MCP server for AI agents: read tools and resources over the same query language and services as the API (§11.3, §18.1). Phase 0 has no write tools (they arrive propose-only in P0-I6).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mcp.server.build_server(factory, *, actor, authorize_hook=authorize)` | function | An `MCPServer` named `throughline` over a unit-of-work factory (`SqliteUowFactory` has the shape) |
| tool `search_records(scope, q="", limit=50, offset=0, order_by=None)` | tool | The query language (same text as `GET /records?q=`); returns `{records, total, limit, offset}`; a syntax error names its position |
| tool `get_record(record, scope=None)` | tool | One record envelope; `record` is an id, or a key with `scope` |
| tool `get_links(record, scope=None, include_retracted=False)` | tool | Both directions of the record's links with labels |
| tool `trace(record, scope=None, depth=2, direction="both")` | tool | The n-hop link tree |
| resource `tl://record/{scope}/{key}` | resource | JSON: the record and its links |
| resource `tl://schema/{scope}/{record_type}` | resource | JSON: the form metadata (fields and psets) of a type |
| resource `tl://relations` | resource | JSON: the relation vocabulary |
| `python -m tl_mcp --actor agent:<id> [--db PATH]` | command | Serve on stdio |

All tools are annotated read-only. Inputs are bounded (query 2000 characters, scope and ids 128, `order_by` 256) and checked before the authorise hook runs.

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`, `tl_api` (the `authorize` hook, `check_actor`, and `build_spec` so `q` and `order_by` mean what they mean in the API), `mcp` 2.x.
- Used by: agents (stdio), `just demo P0-I4-C`, the P0-I4 demo (WS-D).

## Commands
```
uv run python -m tl_mcp --actor agent:triage       # stdio server on TL_DB
just test packages/tl-mcp
```
Runbook: `docs/runbooks/api-and-mcp-dev.md`.

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` / `--db` | `./dev/data/tl.db` | The ledger is opened read-only per call, so the server can run beside the API or the TUI |
| `--actor` | required | `agent:<id>` or `user:<id>`; fixed for the life of the server (ADR-0005) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I4 (workstream C). Resource-change notifications through the change feed (brief 11.3) are a follow-up.
