"""The reserved-identifier walk over the MCP thread tools (FANOUT D2, P1-I7 WS-B): no argument lets
an agent name a source, a correlation or causation id, a link source or an ``enrich.`` pset."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from tl_core.integration.contract import RESERVED_LINK_SOURCES

TOOLS = {"read_thread", "post_thread_message", "propose_dispatch"}

BASE: dict[str, dict[str, Any]] = {
    "read_thread": {"record": "P123-REC-0001", "scope": SCOPE},
    "post_thread_message": {"record": "P123-REC-0001", "scope": SCOPE, "body": "hello"},
    "propose_dispatch": {"record": "P123-REC-0001", "scope": SCOPE, "text": "/link P123-REC-0002"},
}

EXTRAS: list[dict[str, Any]] = [
    {"source": "rule:x@1/d0"},
    {"source": "thread:x"},
    {"source": "inbound:a/b"},
    {"correlation_id": "dispatch:x"},
    {"correlation_id": "rule:x"},
    {"causation_id": "action:x"},
    *({"link_source": name} for name in sorted(RESERVED_LINK_SOURCES)),
    {"psets": {"enrich.classifier": {"label": "x"}}},
    {"actor": "user:boss"},
    {"actor_roles": ["admin"]},
    {"holds": True},
]


def thread_tools(env: McpHarness) -> set[str]:
    listed = asyncio.run(env.server.list_tools())
    return {tool.name for tool in listed if "thread" in tool.name or "dispatch" in tool.name}


def test_the_walk_lists_the_thread_tools(env: McpHarness) -> None:
    assert thread_tools(env) == TOOLS
    assert len(EXTRAS) >= 15 and set(BASE) == TOOLS


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_no_thread_tool_takes_what_only_the_server_sets(env: McpHarness, tool: str) -> None:
    with env.factory(True) as uow:
        before = len(uow.ledger.read_after(0, limit=10_000))
    for extra in EXTRAS:
        with pytest.raises(ToolError):
            env.call(tool, **{**BASE[tool], **extra})
    with env.factory(True) as uow:
        assert len(uow.ledger.read_after(0, limit=10_000)) == before
