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
from tl_api.auth import Forbidden
from tl_api.errors import ApiError
from tl_sim import api, mcp_server
from tl_sim.scenario_loader import ScenarioError, load_bundled_scenario, load_scenario
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
    assert by_name["sim_create"] == (
        (ENV, "north-unit-small"),
        {"run_id": "rx", "bundled_only": True},
    )
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

    monkeypatch.setattr(
        mcp_server, "build_server", lambda env, actor: (seen.append(env), Stub())[1]
    )
    monkeypatch.setenv("TL_SIM_DIR", "/e/sim")
    monkeypatch.setenv("TL_API_URL", "http://e:9")
    monkeypatch.setenv("TL_TOKENS", "/e/t.json")
    assert mcp_server.main([]) == 0
    assert seen == [api.SimEnv(Path("/e/sim"), "http://e:9", Path("/e/t.json"))]


# --- the door is narrower than the CLI's: bundled scenario names only ---------------------------


@pytest.fixture
def seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A seed directory with one bundled scenario, and a YAML file outside it."""
    (tmp_path / "seed" / "scenarios").mkdir(parents=True)
    (tmp_path / "seed" / "templates").mkdir()
    (tmp_path / "seed" / "scenarios" / "tiny.yaml").write_text(
        "scenario: tiny\nseed: 5\nstart: 2026-11-02\n"
    )
    (tmp_path / "outside.yaml").write_text("scenario: outside\nseed: 1\nstart: 2026-11-02\n")
    (tmp_path / "seed" / "scenarios" / "evil.yaml").symlink_to(tmp_path / "outside.yaml")
    monkeypatch.setenv("TL_SEED_DIR", str(tmp_path / "seed"))
    return tmp_path


@pytest.mark.parametrize(
    "name",
    [
        "/etc/hostname",
        "/etc/hostname.yaml",
        "../outside",
        "../outside.yaml",
        "../../etc/passwd",
        "seed/scenarios/tiny.yaml",
        "evil/../tiny",
        "TINY",
        "",
        "a" * 65,
    ],
)
def test_a_path_or_a_bad_name_never_reaches_the_loader_through_mcp(
    seed: Path, server: MCPServer, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached: list[str] = []
    monkeypatch.setattr(api, "load_bundled_scenario", lambda n: reached.append(n))
    with pytest.raises(ToolError):
        call(server, "sim_create", scenario=name)
    assert reached == []  # the schema refuses it before the tool body runs


@pytest.mark.parametrize("name", ["tiny.yaml", "tiny.yml", "evil", "nope", ".", ".."])
def test_a_name_the_pattern_allows_but_no_bundled_file_matches_is_unknown(
    seed: Path, server: MCPServer, name: str
) -> None:
    """Dots are allowed in a name, so ``tiny.yaml`` is a name; it finds no ``tiny.yaml.yaml``."""
    with pytest.raises(ToolError, match="unknown scenario; bundled scenarios: .*tiny"):
        call(server, "sim_create", scenario=name)


def test_the_api_door_for_mcp_refuses_everything_but_a_bundled_name(seed: Path) -> None:
    for name in ("/etc/hostname", "../outside", "tiny.yaml", "evil", "nope", "a/b"):
        with pytest.raises(ScenarioError) as raised:
            api.sim_create(ENV, name, bundled_only=True)
        assert str(seed) not in raised.value.public and "hostname" not in raised.value.public
        assert "tiny" in raised.value.public  # it lists what is bundled


def test_a_symlink_that_leaves_the_scenarios_directory_is_refused(seed: Path) -> None:
    with pytest.raises(ScenarioError) as raised:
        load_bundled_scenario("evil")
    assert "outside" not in raised.value.public
    assert load_bundled_scenario("tiny").scenario == "tiny"


def test_error_text_shown_to_a_remote_caller_holds_no_path_or_file_content(
    seed: Path, server: MCPServer
) -> None:
    (seed / "seed" / "scenarios" / "broken.yaml").write_text(
        "scenario: [secret-token-in-the-file\n"
    )
    (seed / "seed" / "scenarios" / "badtype.yaml").write_text(
        "scenario: ok\nseed: hunter2\nstart: 2026-11-02\n"
    )
    for name in ("broken", "badtype", "ghost"):
        with pytest.raises(ToolError) as raised:
            call(server, "sim_create", scenario=name)
        text = str(raised.value)
        assert str(seed) not in text and "/" not in text.replace("sim_", "")
        assert "secret-token" not in text and "hunter2" not in text


def test_the_cli_still_reads_a_path_and_its_errors_still_name_the_file(seed: Path) -> None:
    with pytest.raises(ScenarioError) as raised:
        load_scenario(seed / "outside.yaml")
        load_scenario(seed / "missing.yaml")
    assert "missing.yaml" in str(raised.value) and "missing.yaml" not in raised.value.public


def test_a_run_error_does_not_name_a_directory(seed: Path, server: MCPServer) -> None:
    with pytest.raises(ToolError) as raised:
        call(server, "sim_status", run_id="rnone")
    assert "/" not in str(raised.value)


# --- the authorise hook is the first call of every tool -------------------------------------------


def deny_all(actor: str, action: str, resource: str) -> None:
    raise Forbidden(f"{actor} may not {action}")


def test_a_deny_all_hook_stops_every_tool_before_anything_runs(fakes: Fakes) -> None:
    server = mcp_server.build_server(ENV, authorize_hook=deny_all)
    attempts = [
        ("sim_create", {"scenario": "north-unit-small"}),
        ("sim_advance", {}),
        ("sim_inject", {"event": "post"}),
        ("sim_status", {}),
        ("sim_assert", {}),
    ]
    for tool, arguments in attempts:
        with pytest.raises(ToolError, match="not allowed"):
            call(server, tool, **arguments)
    assert fakes.log == []


def test_the_hook_sees_the_actor_the_action_and_a_quoted_resource(fakes: Fakes) -> None:
    seen: list[tuple[str, str, str]] = []
    server = mcp_server.build_server(
        ENV, actor="agent:sim-assistant", authorize_hook=lambda a, b, c: seen.append((a, b, c))
    )
    call(server, "sim_create", scenario="north-unit-small")
    call(server, "sim_advance", run_id="rx")
    call(server, "sim_inject", event="post", args={"actor": "crew", "body": "x"})
    call(server, "sim_status")
    call(server, "sim_assert", run_id="rx")
    assert seen == [
        ("agent:sim-assistant", "sim.create", "scenario:north-unit-small"),
        ("agent:sim-assistant", "sim.advance", "run:rx"),
        ("agent:sim-assistant", "sim.inject", "run:-"),
        ("agent:sim-assistant", "sim.status", "run:-"),
        ("agent:sim-assistant", "sim.assert", "run:rx"),
    ]


def test_the_actor_must_be_a_user_or_an_agent() -> None:
    for bad in ("sim", "svc:x", "agent:", "root"):
        with pytest.raises(ValueError):
            mcp_server.build_server(ENV, actor=bad)


def test_injection_arguments_over_the_cap_are_refused_through_mcp(
    fakes: Fakes, server: MCPServer
) -> None:
    api_inject = api.sim_inject
    del api_inject  # the fakes stand in; the cap is InjectSpec's and is tested in test_scenario
    with pytest.raises(ToolError):
        call(server, "sim_inject", event="post", args={f"k{n}": n for n in range(17)})
