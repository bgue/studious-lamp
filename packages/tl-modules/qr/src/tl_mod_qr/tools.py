"""The agent tools of the QR module (ADR-0029): none. A scan code is a bearer path a person prints,
so no tool issues or reads one."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from tl_mcp.context import McpContext


def register_tools(server: MCPServer, ctx: McpContext) -> None:
    """Register no tool."""
    del server, ctx
