"""Schedule and cost read tools: schedules, snapshots, comparison, look-ahead, cost codes (T13).

STUB (P1-I4-T13): `register_schedule_read_tools` is the one function the server calls; the tools
are added by the ticket. Nothing is registered yet.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tl_mcp.context import McpContext


def register_schedule_read_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the read tools to ``server``."""
