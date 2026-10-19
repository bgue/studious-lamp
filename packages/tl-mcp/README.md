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
| tool `get_settings(key=None, prefix=None, project=None, modified_only=False)` | tool | Read-only: each setting with its definition and effective state for a project, one by `key` or a list narrowed by `prefix` and `modified_only` (not both) |
| tool `propose_setting_change(key, layer, value=None, reset=False, reason=None, applies_at=None, summary=None)` | tool | **Propose** a setting change (`ChangeSetting`); a person accepts, giving `accept_risk` for a dangerous key. The tool takes no risk acceptance: an argument it does not declare is ignored |
| tool `post_feed(scope, body, importance="normal")` | tool | **Post directly** to a project feed, labelled `agent:<id>` (source `mcp:<id>`); a `#<record key>` tag only suggests a `references` link |
| `python -m tl_mcp --tool-mode TOOL=propose` | option | `propose` is the only mode; `write` exits 2 with the human-gate message |
| tool `lake_query(sql, limit=100)` | tool | Read-only SQL over the DuckLake copy (`tl-lake`): one SELECT, row limit (at most 1000), 1 MiB answer cap, 30 s timeout, one audit line per call with the acting agent; returns `{columns, rows, row_count, truncated, truncated_by, limit, as_of_seq, snapshot_id, as_of}`; a refusal is a `ToolError` starting `refused:` |
| resource `tl://lake/schema` | resource | JSON: the lake's tables and columns |
| resource `tl://record/{scope}/{key}` | resource | JSON: the record and its links |
| resource `tl://schema/{scope}/{record_type}` | resource | JSON: the form metadata (fields and psets) of a type |
| resource `tl://relations` | resource | JSON: the relation vocabulary |
| tool `list_code_values(code_list, project=None, include_all=False)`, `list_tag_classes(include_closed=False)`, `get_tag(project, number)` | tools | Engineering data (`tl_mcp.engineering_tools`, P1-I1): the values of a code list as a scope sees them (a project value names the company value it stands for), the tag classes with the property sets each requires, and one tag with its segments, class, state and what it lacks. Read-only; the models are the API's (`CodeValueOut`, `TagClassOut`, `TagDetail`). Changing any of it stays a person's work: a tag change is a proposal, the registry is admin-only |
| tools `list_documents`, `get_document`, `get_document_diff`, `list_stale_links`, `list_overdue_reviews`, `list_transmittals`, `get_transmittal` | tools | Document control reads (`tl_mcp.document_tools`, P1-I2): the register, one document with its revisions and links (`pin_state` `stale` follows the class-aware rule, ADR-0012), the diff of two revisions, stale links, overdue reviews and transmittals. Read-only (`document.read`); the models are the module's views. Changing any of it stays a person's work. Confidentiality is recorded but not enforced in Phase 1: an agent reads every document and transmittal of a project, recipient emails included |
| tool `list_record_types(status=None)`, `get_record_type(type_ref)`, `get_record_body(record, scope=None)` | tools | Extension record types (`tl_mcp.type_tools`, brief 31): the registered versions, one version with its generated form, and the verified body of an object-backed record. Read-only. `create_record` with a type name proposes a managed instance; an object-backed type is refused (a proposal carries no body) |
| resources `tl://types`, `tl://types/{type_ref}` | resources | JSON: the registered versions; one version with its form |
| `TL_AGENT_TOKEN=... python -m tl_mcp [--db TARGET] [--lake-dir DIR]` | command | Serve on stdio as the agent the token belongs to |
| `tl_mcp.identity` (`token_from_env`, `resolve_agent`, `token_authorizer`) | module | Reads the agent token, finds its agent, and builds the hook that checks the token and the agent's allowance on every call (P1-I0, ADR-0009) |
| `tl_mcp.context.McpContext` | class | What every tool and resource needs: a unit-of-work factory, the actor and the authorise hook |
| `tl_mcp.errors.guarded` | function | Authorises, then turns the failures a tool or resource can meet into `ToolError` or `ResourceError` |
| `tl_mcp.models` | module | The structured results of the tools (the schema agents see) |
| `python -m tl_mcp.dev [--db TARGET]` | command | The dev MCP server (below), stdio only, dev data only |
| tools `list_derived_documents`, `get_derived_document`, `validate_against_schema` (read only) and `start_extraction`, `propose_import` (proposals) | tools | Derivation (`tl_mcp.derivation_tools`, P1-I3, ADR-0014). `validate_against_schema` returns the report a job stored and never runs a JSON Schema; the two proposing tools file a pending proposal (tools `start_extraction`, `propose_import_tags`, `propose_import_documents`) and accepting one needs the access of the proposed command (admin for tags, controller for documents). Five `MCP_ACTIONS` entries. `build_server(files=...)` is the file service the report reads use |

The read tools are annotated read-only; the five write tools are not (and none is destructive). Inputs are bounded and checked before the authorise hook runs: query 2000 characters, scope and ids 128, title 500, description and post body 10 000, summary 300, note and reason 1 000, `order_by` 256; `psets` and `values` are bounded as JSON text (64 000 characters). A test fails if any string in a tool schema has no limit. Everything done for the agent carries `source=mcp:<id>`; each agent may file `TL_AGENT_DAILY_PROPOSALS` proposals per UTC day (default 500), after which the tool says so. There is no tool that accepts or rejects: a person does that (`tl proposal`, `POST /proposals/{id}/accept`). `lake_query` is read-only and calls the hook as `mcp.lake_query` on `lake:main`; its SQL is bounded at 20 000 characters.

A call the authorise hook refuses never reaches the lake service, so it writes no `lake_query.log.jsonl` line; the hook owns the record of denials. Accepted, refused and failed statements are all logged, with the acting agent. Lake failures reach the agent as fixed sentences (`the lake has not been synced yet: run `tl lake sync``, `the lake is busy`) or, for a failing statement, a short message with the DuckDB error class; the lake directory and other server paths are never returned.

## Dev MCP server (`tl_mcp.dev`)
A separate entry point for coding agents (brief 25.3), not the product server: no actor, no record tools, and a guard (`tl_mcp.dev.guard`) that refuses anything but dev data (SQLite under `dev/` or a temp directory; a local `tl_test*`/`tl_dev*` Postgres; `TL_ENV` unset, dev, test or ci). Runbook: `docs/runbooks/dev-mcp.md`.

| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mcp.dev.server.build_dev_server(ctx)` | function | The `throughline-dev` server over a `DevContext` (repository root, the one database, audit file) |
| tools `run_tests`, `gen`, `query_db`, `rebuild_projections`, `seed`, `send_test_webhook`, `render_screen` | tools | One module each, `tl_mcp/dev/tool_*.py`; `query_db` is read-only SQLite (`sqlguard.py`, `query.py`) |
| resources `tl://dev/schema-graph`, `event-catalog`, `event-sample/{type}`, `adrs`, `runbooks`, `test-reports` (and `adr/{name}`, `runbook/{name}`, `test-report/{name}`) | resources | `resources_schema.py`, `resources_docs.py` |
| `tl_mcp.dev.guard` | module | Database target rule, pytest allow-lists, loopback URL check, plain-name document lookup, `redact_url` |

Every tool call writes one audit line to `dev/data/dev-mcp.log.jsonl`. Postgres is refused by `query_db` (deviation C4, follow-up: a non-superuser reader role and a function allow-list).

## Depends on / used by
- Depends on: `tl_lake` (the guarded query service), `tl_core`, `tl_schema`, `tl_adapters`, `tl_api` (the `authorize` hook, `check_actor`, and `build_spec` so `q` and `order_by` mean what they mean in the API), `mcp` 2.x.
- Used by: agents (stdio), `just demo P0-I4-C`, the P0-I4 demo (WS-D).
- The dev server also uses `tl_tui` (`render_screen`) and `tl_schema` (`gen`, the catalog); the product server does not import `tl_mcp.dev`.

## Commands
```
TL_AGENT_TOKEN="$(uv run tl admin token issue triage --label mcp)" \
  uv run python -m tl_mcp                          # stdio server on TL_DB, as agent:triage
uv run python -m tl_mcp.dev                        # the dev server on TL_DB (dev data only)
just test packages/tl-mcp
```
Runbook: `docs/runbooks/api-and-mcp-dev.md`.

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` / `--db` | `./dev/data/tl.db` | A SQLite file or a `postgresql://` URL (prefer the variable). Each call opens its own short transaction, so the server can run beside the API or the TUI |
| `TL_AGENT_DAILY_PROPOSALS` | `500` | Proposals one agent may file per UTC day; `0` refuses every proposal |
| `TL_LAKE_DIR` / `--lake-dir` | `./dev/data/lake` | The lake `lake_query` reads; it is opened per call and may not exist yet (the tool then says to run `tl lake sync`) |
| `TL_AGENT_TOKEN` | required | An agent token from `tl admin token issue <agent> --label <what for>`. It names the actor for the life of the server and is checked again on every call: a revoked or expired token, or a disabled agent, stops at the next call. A person's session token is refused. Never pass it as an argument. `--actor` was removed |

### Record threads (P1-I7 WS-B)
Tools `read_thread`, `post_thread_message` (direct, never dispatches) and `propose_dispatch` (files a proposal that a
person previews and accepts; `threads.agents.can_dispatch`). Visibility is the record's.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
P1-I2: the seven document read tools (each an explicit `MCP_ACTIONS` entry). P1-I1: the three engineering read tools (`mcp.list_code_values`, `mcp.list_tag_classes`, `mcp.get_tag` in `MCP_ACTIONS`). Introduced in P0-I4 (workstream C); `get_settings` and `propose_setting_change` added in P0-I8 workstream A; the dev server (`tl_mcp.dev`) was added in P0-I8 workstream C; write tools added in P0-I6 workstream B (decisions B1 to B14: `docs/tickets/P0-I6/README-B.md`). Per-role tool permissions and a direct-write mode are the permission model, a human gate, and are not built. Resource-change notifications through the change feed (brief 11.3) are a follow-up. Type tools added in P0-I8 workstream B (`docs/tickets/P0-I8/README-B.md`).
