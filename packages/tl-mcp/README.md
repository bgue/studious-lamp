# tl-mcp (`tl_mcp`)

The MCP server for AI agents: read tools and resources over the same query language and services as the API, four tools that only *propose* a record change for a person to accept, and `post_feed`, the one direct write, labelled with the agent (§11.3, §18.1, §18.12, §21.3).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mcp.server.build_server(factory, *, actor, authorize_hook=authorize, tool_modes=None, lake_dir=None)` | function | An `MCPServer` named `throughline` over a unit-of-work factory (`SqliteUowFactory` has the shape). `tool_modes={"create_record": "write"}` raises `ToolModeError` (human gate); `lake_dir` is the DuckLake directory `lake_query` reads |
| tool `search_records(scope, q="", limit=50, offset=0, order_by=None)` | tool | The query language (same text as `GET /records?q=`); returns `{records, total, limit, offset}`; a syntax error names its position |
| tool `get_record(record, scope=None)` | tool | One record envelope; `record` is an id, or a key with `scope` |
| tool `get_links(record, scope=None, include_retracted=False)` | tool | Both directions of the record's links with labels |
| tool `trace(record, scope=None, depth=2, direction="both")` | tool | The n-hop link tree |
| tool `create_record(scope, title, record_type="core.Record", description=None, key=None, psets=None, numbering=None, summary=None)` | tool | **Propose** a record. Returns `{proposal, message}` with the pending proposal; nothing exists until a person accepts. Refused now with the handler's own error (duplicate key, unknown pset ...) if it could not be applied |
| tool `update_psets(record, pset, values, scope=None, layer="standard", expected_version=None, summary=None)` | tool | **Propose** property values; `expected_version` defaults to the version now, and a stale proposal fails on acceptance |
| tool `link_records(from_record, to_record, scope=None, relation=None, note=None, summary=None)` | tool | **Propose** a link |
| tool `transition_workflow(record, transition, scope=None, expected_version=None, reason=None, summary=None)` | tool | **Propose** a transition; guards other than role guards are checked now, role guards for the person who accepts |
| tool `post_feed(scope, body, importance="normal")` | tool | **Post directly** to a project feed, labelled `agent:<id>` (source `mcp:<id>`); a `#<record key>` tag only suggests a `references` link |
| `python -m tl_mcp --tool-mode TOOL=propose` | option | `propose` is the only mode; `write` exits 2 with the human-gate message |
| tool `lake_query(sql, limit=100)` | tool | Read-only SQL over the DuckLake copy (`tl-lake`): one SELECT, row limit (at most 1000), 1 MiB answer cap, 30 s timeout, one audit line per call with the acting agent; returns `{columns, rows, row_count, truncated, truncated_by, limit, as_of_seq, snapshot_id, as_of}`; a refusal is a `ToolError` starting `refused:` |
| resource `tl://lake/schema` | resource | JSON: the lake's tables and columns |
| resource `tl://record/{scope}/{key}` | resource | JSON: the record and its links |
| resource `tl://schema/{scope}/{record_type}` | resource | JSON: the form metadata (fields and psets) of a type |
| resource `tl://relations` | resource | JSON: the relation vocabulary |
| `python -m tl_mcp --actor agent:<id> [--db PATH] [--lake-dir DIR]` | command | Serve on stdio |

The read tools are annotated read-only; the five write tools are not (and none is destructive). Inputs are bounded and checked before the authorise hook runs: query 2000 characters, scope and ids 128, title 500, description and post body 10 000, summary 300, note and reason 1 000, `order_by` 256; `psets` and `values` are bounded as JSON text (64 000 characters). A test fails if any string in a tool schema has no limit. Everything done for the agent carries `source=mcp:<id>`; each agent may file `TL_AGENT_DAILY_PROPOSALS` proposals per UTC day (default 500), after which the tool says so. There is no tool that accepts or rejects: a person does that (`tl proposal`, `POST /proposals/{id}/accept`). `lake_query` is read-only and calls the hook as `mcp.lake_query` on `lake:main`; its SQL is bounded at 20 000 characters.

A call the authorise hook refuses never reaches the lake service, so it writes no `lake_query.log.jsonl` line; the hook owns the record of denials. Accepted, refused and failed statements are all logged, with the acting agent. Lake failures reach the agent as fixed sentences (`the lake has not been synced yet: run `tl lake sync``, `the lake is busy`) or, for a failing statement, a short message with the DuckDB error class; the lake directory and other server paths are never returned.

## Depends on / used by
- Depends on: `tl_lake` (the guarded query service), `tl_core`, `tl_schema`, `tl_adapters`, `tl_api` (the `authorize` hook, `check_actor`, and `build_spec` so `q` and `order_by` mean what they mean in the API), `mcp` 2.x.
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
| `TL_DB` / `--db` | `./dev/data/tl.db` | Each call opens its own short transaction, so the server can run beside the API or the TUI |
| `TL_AGENT_DAILY_PROPOSALS` | `500` | Proposals one agent may file per UTC day; `0` refuses every proposal |
| `TL_LAKE_DIR` / `--lake-dir` | `./dev/data/lake` | The lake `lake_query` reads; it is opened per call and may not exist yet (the tool then says to run `tl lake sync`) |
| `--actor` | required | `agent:<id>` or `user:<id>`; fixed for the life of the server (ADR-0005) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I4 (workstream C); write tools added in P0-I6 workstream B (decisions B1 to B14: `docs/tickets/P0-I6/README-B.md`). Per-role tool permissions and a direct-write mode are the permission model, a human gate, and are not built. Resource-change notifications through the change feed (brief 11.3) are a follow-up.
