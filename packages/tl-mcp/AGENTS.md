# AGENTS.md — tl-mcp

Read the root `AGENTS.md` first. These rules add to it.

- No business logic here. Tool and resource bodies call `tl_core` services through `ctx.factory(True)`; no SQL, no ledger access.
- `server.py` owns tool names, schemas and descriptions (the text an agent reads); `tools.py` and `resources.py` own the bodies. Every body runs inside `guarded(...)`, which checks the identifier parts, calls the authorise hook with a quoted resource name, and turns expected failures into `ToolError` or `ResourceError`.
- `lake_query` only forwards to `tl_lake.LakeQueryService`, which owns the guard, limits and audit log; never widen what it accepts here, and keep the answer cap below the service's own. `GuardError` becomes `refused: ...`, any other `LakeError` a `ToolError`.
- Phase 0 has no write tools. A write tool is propose-only and is added in P0-I6 with its own ticket and the `source=mcp:<agent>` tag. Never add one here.
- Bound every new string input with `Field(max_length=...)`; the query text limit is the parser's (`MAX_QUERY_LENGTH`).
- `mcp` is 2.x: `MCPServer` (not `FastMCP`), `mcp.Client(server)` for an in-memory client. Tests call `server.call_tool` and `server.read_resource` in process; no async plugin, use `asyncio.run`.
