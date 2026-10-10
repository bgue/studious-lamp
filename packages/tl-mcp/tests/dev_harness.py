"""Test harness for the dev MCP server: a real SQLite ledger in a temp directory, the server in
process, and call helpers. Nothing is mocked.

``call`` runs a tool through the server's dispatcher (the path a client's ``tools/call`` takes,
minus the transport); a refusal raises ``ToolError`` as the SDK does before the transport.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult
from tl_adapters.sqlite.uow import create_schema
from tl_mcp.dev.guard import DevTarget, find_repo_root, resolve_target
from tl_mcp.dev.runtime import DevContext
from tl_mcp.dev.server import build_dev_server


@dataclass
class DevHarness:
    ctx: DevContext
    server: MCPServer
    db: Path

    @staticmethod
    def build(
        root: Path,
        *,
        repo_root: Path | None = None,
        target: DevTarget | None = None,
        create: bool = True,
    ) -> DevHarness:
        """A server over ``root / "tl.db"`` (a temp directory, so the guard accepts it).

        ``repo_root`` defaults to the real repository (tools such as ``gen`` and ``run_tests`` need
        it); tools that write below it (reports, snapshots) must be given a copy or a temp tree.
        The audit file is ``root / "audit.jsonl"``.
        """
        db = root / "tl.db"
        if create and target is None:
            create_schema(db)
        repo = repo_root if repo_root is not None else find_repo_root()
        chosen = target if target is not None else resolve_target(db, repo_root=repo)
        ctx = DevContext(repo_root=repo, target=chosen, audit_path=root / "audit.jsonl")
        return DevHarness(ctx, build_dev_server(ctx), db)

    def create_record(self, key: str, title: str = "A record", scope: str = "project:P123") -> str:
        """Append a ``core.Record`` to the ledger (as ``user:seed``); returns the stream id."""
        from tl_adapters.sqlite.uow import open_uow
        from tl_core.services.commands import CreateRecord
        from tl_core.services.records import handle_create_record

        with open_uow(self.db) as uow:
            result = handle_create_record(
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
        return result.stream_id

    def call(self, tool: str, **arguments: Any) -> CallToolResult:
        result = asyncio.run(self.server.call_tool(tool, arguments))
        assert isinstance(result, CallToolResult)
        return result

    def structured(self, tool: str, **arguments: Any) -> Any:
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

    def tool_names(self) -> list[str]:
        return sorted(tool.name for tool in asyncio.run(self.server.list_tools()))

    def resource_uris(self) -> list[str]:
        listed = asyncio.run(self.server.list_resources())
        templates = asyncio.run(self.server.list_resource_templates())
        return sorted([str(r.uri) for r in listed] + [str(t.uri_template) for t in templates])

    def audit_lines(self) -> list[dict[str, Any]]:
        path = self.ctx.audit_path
        assert path is not None
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]
