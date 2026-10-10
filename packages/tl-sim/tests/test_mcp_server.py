"""The simulation MCP server: five tools over ``tl_sim.api``, with the five operations faked."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult
from tl_api.errors import ApiError
from tl_sim import api, mcp_server
from tl_sim.scenario_loader import ScenarioError
from tl_sim.state import RunError

ENV = api.SimEnv(Path("/x/sim"), "http://h:1", Path("/x/t.json"))
TOOLS = {"sim_create", "sim_advance", "sim_inject", "sim_status", "sim_assert"}


class Fakes:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.log: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.fail: Exception | None = None
        for name in TOOLS:
            monkeypatch.setattr(api, name, self._make(name))

    def _make(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.log.append((name, args, kwargs))
            if self.fail is not None:
                raise self.fail
            return {"called": name, "run_id": "r1"}

        return call


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    return Fakes(monkeypatch)


@pytest.fixture
def server() -> MCPServer:
    return mcp_server.build_server(ENV)


def call(server: MCPServer, tool: str, **arguments: Any) -> CallToolResult:
    result = asyncio.run(server.call_tool(tool, arguments))
    assert isinstance(result, CallToolResult)
    return result


def test_the_surface_is_the_five_operations(server: MCPServer) -> None:
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == TOOLS
    for tool in tools.values():
        assert tool.description and tool.annotations is not None
        assert tool.annotations.destructive_hint is False
    assert tools["sim_status"].annotations.read_only_hint is True  # type: ignore[union-attr]
    assert tools["sim_assert"].annotations.read_only_hint is True  # type: ignore[union-attr]
    assert tools["sim_advance"].annotations.read_only_hint is False  # type: ignore[union-attr]
    assert tools["sim_create"].input_schema["required"] == ["scenario"]
    assert tools["sim_inject"].input_schema["required"] == ["event"]
    advance = tools["sim_advance"].input_schema["properties"]["days"]
    assert (advance["minimum"], advance["maximum"]) == (1, 366)


def test_each_tool_calls_its_operation_with_the_environment_it_was_built_with(
    fakes: Fakes, server: MCPServer
) -> None:
    call(server, "sim_create", scenario="north-unit-small", run_id="rx")
    call(server, "sim_advance", run_id="rx", days=3)
    call(server, "sim_inject", event="post", args={"actor": "crew", "body": "hi"}, run_id="rx")
    call(server, "sim_status")
    call(server, "sim_assert", run_id="rx")
    assert [name for name, _, _ in fakes.log] == [
        "sim_create",
        "sim_advance",
        "sim_inject",
        "sim_status",
        "sim_assert",
    ]
    assert all(args[0] == ENV for _, args, _ in fakes.log)
    by_name = {name: (args, kwargs) for name, args, kwargs in fakes.log}
    assert by_name["sim_create"] == ((ENV, "north-unit-small"), {"run_id": "rx"})
    assert by_name["sim_advance"] == ((ENV, "rx"), {"days": 3})
    assert by_name["sim_inject"][0] == (ENV, "rx", "post", {"actor": "crew", "body": "hi"})
    assert by_name["sim_status"][0] == (ENV, None)


def test_a_result_is_returned_as_structured_content(fakes: Fakes, server: MCPServer) -> None:
    result = call(server, "sim_status")
    assert not result.is_error
    assert result.structured_content == {"called": "sim_status", "run_id": "r1"}


@pytest.mark.parametrize(
    "error",
    [
        RunError("no run 'r9' in /x/sim (runs: none)"),
        ScenarioError("/x/s.yaml: seed: Field required"),
        ApiError(503, "unavailable", "the API is down"),
        ValueError("post needs: actor, body"),
    ],
)
def test_a_known_failure_is_a_tool_error_with_its_message(
    fakes: Fakes, server: MCPServer, error: Exception
) -> None:
    fakes.fail = error
    with pytest.raises(ToolError) as raised:
        call(server, "sim_advance")
    assert str(error) in str(raised.value) or getattr(error, "message", "") in str(raised.value)


def test_a_bug_is_not_turned_into_a_known_failure_message(fakes: Fakes, server: MCPServer) -> None:
    """The SDK reports an unexpected exception generically; the server must not add its text."""
    fakes.fail = ZeroDivisionError("secret detail")
    with pytest.raises(ToolError) as raised:
        call(server, "sim_status")
    assert type(raised.value).__name__ == "UnexpectedToolError"
    assert "secret detail" not in str(raised.value)


def test_arguments_are_checked_before_the_operation_runs(fakes: Fakes, server: MCPServer) -> None:
    for tool, bad in (
        ("sim_advance", {"days": 0}),
        ("sim_advance", {"days": 1000}),
        ("sim_create", {"scenario": ""}),
        ("sim_inject", {}),
    ):
        with pytest.raises(ToolError):
            call(server, tool, **bad)
    assert fakes.log == []


def test_it_works_through_the_protocol_too(fakes: Fakes, server: MCPServer) -> None:
    async def run() -> CallToolResult:
        async with Client(server) as client:
            return await client.call_tool("sim_status", {})

    result = asyncio.run(run())
    assert not result.is_error and result.structured_content == {
        "called": "sim_status",
        "run_id": "r1",
    }


def test_the_environment_comes_from_the_variables_when_run_as_a_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[api.SimEnv] = []

    class Stub:
        def run(self, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setattr(mcp_server, "build_server", lambda env: (seen.append(env), Stub())[1])
    monkeypatch.setenv("TL_SIM_DIR", "/e/sim")
    monkeypatch.setenv("TL_API_URL", "http://e:9")
    monkeypatch.setenv("TL_TOKENS", "/e/t.json")
    assert mcp_server.main([]) == 0
    assert seen == [api.SimEnv(Path("/e/sim"), "http://e:9", Path("/e/t.json"))]
