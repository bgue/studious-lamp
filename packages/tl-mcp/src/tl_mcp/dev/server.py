"""``build_dev_server``: the dev MCP server over one guarded dev database (brief 25.3, D12).

The tools and resources live in sibling modules, one per concern, each with a ``register(server,
ctx)`` function. This module only names them, so a tool is added or changed in one file.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tl_mcp.dev import (
    resources_docs,
    resources_schema,
    tool_gen,
    tool_query_db,
    tool_rebuild,
    tool_render_screen,
    tool_run_tests,
    tool_seed,
    tool_webhook,
)
from tl_mcp.dev.runtime import DevContext

MODULES = (
    tool_query_db,
    tool_run_tests,
    tool_gen,
    tool_rebuild,
    tool_seed,
    tool_webhook,
    tool_render_screen,
    resources_schema,
    resources_docs,
)

INSTRUCTIONS = (
    "Development tools for the Throughline repository. They work on dev data only: one SQLite "
    "file under dev/ or a temp directory, or a local tl_test*/tl_dev* Postgres database; anything "
    "else is refused. Use `run_tests` (filtered pytest), `gen` (codegen drift report), "
    "`query_db` (read-only SQL), `render_screen` (a TUI screen as SVG), `rebuild_projections`, "
    "`seed` and `send_test_webhook` (loopback receivers only). Resources describe the schema "
    "graph, the event catalog, the ADRs, the runbooks and the test reports."
)


def build_dev_server(ctx: DevContext) -> MCPServer:
    """An MCP server named ``throughline-dev`` over ``ctx`` (stdio only; the caller runs it)."""
    server = MCPServer("throughline-dev", instructions=INSTRUCTIONS)
    for module in MODULES:
        module.register(server, ctx)
    return server
