"""Dev resources (stub: ticket P0-I8-T46 replaces this body; see docs/tickets/P0-I8/)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tl_mcp.dev.runtime import DevContext


def register(server: MCPServer, ctx: DevContext) -> None:
    """Register the resources on `server`. Not built yet."""
    del server, ctx
