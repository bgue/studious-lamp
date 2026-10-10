# AGENTS.md — tl-mcp

Read the root `AGENTS.md` first. These rules add to it.

- No business logic here. Tool and resource bodies call `tl_core` services through `ctx.factory(True)`; no SQL, no ledger access.
- `server.py` owns tool names, schemas and descriptions (the text an agent reads); `tools.py` and `resources.py` own the bodies. Every body runs inside `guarded(...)`, which checks the identifier parts, calls the authorise hook with a quoted resource name, and turns expected failures into `ToolError` or `ResourceError`.
- Record-changing tools are propose-only (`write_tools.py`): they build the command, call `proposals.submit` and return the pending proposal. Never call a record handler from a tool, never add a tool that accepts, rejects or fails a proposal, and never add a direct-write mode (the REST API refuses record-changing commands from `agent:` tokens too, B15): who may write directly is the permission model, a human gate (ADR-0005). `modes.py` refuses `write` with the human-gate message. `post_feed` is the one direct write (a post is a message); it carries the agent's actor and `source=mcp:<id>`.
- Every write tool runs inside `guarded`, takes the actor from the server (never from an argument), and tags `source` through `proposals.source_for`. A new write tool needs a hook test, a bounds test and a source test in `tests/test_mcp_write_tools.py`.
- Bound every new string input with `Field(max_length=...)`; the query text limit is the parser's (`MAX_QUERY_LENGTH`). Free-form JSON is bounded as text with `check_json`. `test_every_string_the_tools_accept_has_a_length_limit` fails on a string without a limit.
- `mcp` is 2.x: `MCPServer` (not `FastMCP`), `mcp.Client(server)` for an in-memory client. Tests call `server.call_tool` and `server.read_resource` in process; no async plugin, use `asyncio.run`.
