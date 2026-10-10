"""Test harness for the MCP server: a real ledger, the server in process, sync call helpers.

Nothing is mocked. ``call`` runs one tool through the server's own dispatcher (the same path a
client's ``tools/call`` takes, minus the transport); ``wire`` goes through ``mcp.Client`` over an
in-memory transport for the few tests that check the protocol surface.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import handle_create_record
from tl_mcp.server import build_server

SCOPE = "project:P123"
ACTOR = "agent:triage"


@dataclass
class McpHarness:
    db: Path
    factory: SqliteUowFactory
    server: MCPServer

    @staticmethod
    def build(
        root: Path, *, authorize_hook: Callable[[str, str, str], None] | None = None
    ) -> McpHarness:
        db = root / "tl.db"
        create_schema(db)
        factory = SqliteUowFactory(db)
        if authorize_hook is None:
            server = build_server(factory, actor=ACTOR)
        else:
            server = build_server(factory, actor=ACTOR, authorize_hook=authorize_hook)
        return McpHarness(db, factory, server)

    def close(self) -> None:
        self.factory.close()

    # --- seeding ---------------------------------------------------------------------------

    def create_record(
        self, key: str, title: str = "A record", *, scope: str = SCOPE
    ) -> CommandResult:
        with self.factory(False) as uow:
            return handle_create_record(
                uow,
                CreateRecord(
                    actor="user:seed",
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title=title,
                    key=key,
                ),
            )

    def link(self, a: str, b: str, relation: str = "requires") -> None:
        with self.factory(False) as uow:
            handle_add_link(
                uow,
                AddLink(
                    actor="user:seed",
                    source="test",
                    scope=SCOPE,
                    from_id=a,
                    to_id=b,
                    relation=relation,
                ),
            )

    # --- calling the server -----------------------------------------------------------------

    def call(self, tool: str, **arguments: Any) -> CallToolResult:
        """Run a tool. A refusal raises ``ToolError`` as the SDK does before the transport."""
        result = asyncio.run(self.server.call_tool(tool, arguments))
        assert isinstance(result, CallToolResult)
        return result

    def structured(self, tool: str, **arguments: Any) -> Any:
        """The structured content of a successful call (a list result sits under ``result``)."""
        result = self.call(tool, **arguments)
        assert not result.is_error
        assert result.structured_content is not None
        return result.structured_content

    def read(self, uri: str) -> str:
        contents: list[Any] = list(asyncio.run(self.server.read_resource(uri)))
        assert len(contents) == 1
        content = contents[0].content
        assert isinstance(content, str)
        return content

    def wire_call(self, tool: str, **arguments: Any) -> CallToolResult:
        """The same call through an in-memory MCP client, errors included as results."""

        async def run() -> CallToolResult:
            async with Client(self.server) as client:
                return await client.call_tool(tool, arguments)

        return asyncio.run(run())
