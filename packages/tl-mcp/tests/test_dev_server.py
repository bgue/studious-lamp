"""The dev MCP server: its entry point, its stdio transport and the shape of its tools."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from dev_harness import DevHarness
from mcp import Client, StdioServerParameters
from tl_mcp.dev import main as dev_main
from tl_mcp.dev.guard import find_repo_root

REPO = find_repo_root()


def test_the_server_is_separate_from_the_product_server(dev_env: DevHarness) -> None:
    names = dev_env.tool_names()
    assert "query_db" in names
    for product_tool in ("search_records", "create_record", "post_feed", "lake_query"):
        assert product_tool not in names
    assert dev_env.server.name == "throughline-dev"


def test_every_string_the_dev_tools_accept_has_a_length_limit(dev_env: DevHarness) -> None:
    def strings(node: Any, path: str) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            if node.get("type") == "string" and "maxLength" not in node and "enum" not in node:
                found.append(path)
            for key, value in node.items():
                found.extend(strings(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found.extend(strings(value, f"{path}[{index}]"))
        return found

    unbounded: list[str] = []
    for tool in asyncio.run(dev_env.server.list_tools()):
        unbounded += strings(tool.input_schema, tool.name)
    assert unbounded == []


def test_a_bad_database_stops_the_entry_point(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_ENV", raising=False)
    assert dev_main.main(["--db", "/etc/passwd"]) == 2
    assert "refused" in capsys.readouterr().err
    assert dev_main.main(["--db", "postgresql://u:p@db.example.com/tl_test"]) == 2
    assert dev_main.main(["--db", "postgresql://u:p@localhost/production"]) == 2


def test_a_real_environment_stops_the_entry_point(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TL_ENV", "production")
    assert dev_main.main(["--db", str(tmp_path / "x.db")]) == 2
    assert "TL_ENV" in capsys.readouterr().err


def test_the_server_speaks_mcp_over_stdio_and_refuses_what_the_guard_refuses(
    tmp_path: Path,
) -> None:
    env = DevHarness.build(tmp_path)
    child_env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "VIRTUAL_ENV")}
    child_env["TL_ENV"] = "dev"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp.dev", "--db", str(env.db)],
        env=child_env,
        cwd=REPO,
    )

    async def session() -> tuple[list[str], dict[str, Any] | None, bool]:
        async with Client(params) as client:
            tools = [t.name for t in (await client.list_tools()).tools]
            ok = await client.call_tool("query_db", {"sql": "SELECT count(*) AS n FROM events"})
            bad = await client.call_tool("query_db", {"sql": "DROP TABLE events"})
            return tools, ok.structured_content, bool(bad.is_error)

    tools, structured, refused = asyncio.run(session())
    assert "query_db" in tools
    assert structured is not None and structured["rows"] == [[0]]
    assert refused is True
