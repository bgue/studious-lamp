"""``McpCaller``: how the simulator's one agent reaches the suite's MCP server.

``McpClientCaller(target)`` opens an MCP client session per call with ``mcp.Client``. The target is
a ``StdioServerParameters`` (a real server process, ``python -m tl_mcp --actor agent:sim-assistant
--db <ledger>``) or an in-memory ``MCPServer`` (tests). A tool the server refuses (``ToolError``,
for example a duplicate link, an unknown record or an exhausted budget) is raised as
``ProposalRefusedError`` with the server's own message, so an actor can treat it like the suite
saying no, not as a crash.

The MCP server does not read ``X-TL-Effective-At`` (FANOUT D5 covers the API), so what an agent
does over MCP is stamped with real time; the proposal's effect, when a person accepts it, is too.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.server.mcpserver import MCPServer


class ProposalRefusedError(Exception):
    """The MCP server refused a tool call. The message is the server's, for the log."""


class McpClientCaller:
    """Calls one tool of an MCP server and returns its structured result."""

    def __init__(self, target: MCPServer | StdioServerParameters) -> None:
        self._target = target

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._call(name, arguments))

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with Client(self._target) as client:
            result = await client.call_tool(name, arguments)
        if result.is_error:
            text = " ".join(getattr(part, "text", "") for part in result.content).strip()
            raise ProposalRefusedError(text or f"{name} was refused")
        return dict(result.structured_content or {})


def stdio_caller(actor: str, db: Path) -> McpClientCaller:
    """A caller that starts ``python -m tl_mcp`` for ``actor`` on the ledger file ``db``."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp", "--actor", actor, "--db", str(db)],
    )
    return McpClientCaller(params)
