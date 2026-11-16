"""The agent tools of the permits module: none yet (a later ticket registers them here).

A tool that reads a record runs under `tl_mcp.errors.guarded`, which sets the lowest clearance,
so a hidden record answers as a missing one. It stays closed to agents until an allow row names it.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from tl_mcp.context import McpContext


def register_tools(server: MCPServer, ctx: McpContext) -> None:
    """Register no tool (S2 stub)."""
    del server, ctx
