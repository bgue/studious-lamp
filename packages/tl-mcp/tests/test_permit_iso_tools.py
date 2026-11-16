"""The isolation and gas test MCP reads (P2-PTW T08b): ``list_isolations`` and ``list_gas_tests``,
over a ledger built by the permits module's own commands (``permit_world.py``, loaded by path), as
``test_permit_tools.py`` (T08) does. The tools are reads only; no tool applies, verifies, removes,
links, unlinks or records."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from mcp_types import CallToolResult
from tl_adapters.db import DbTarget
from tl_api.auth import Forbidden
from tl_core.auth.provider import AGENT_ACTIONS, agent_may
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.server import build_server
from tl_mod_permits.tools import PERMIT_MCP_ACTIONS

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
AGENT = "agent:triage"
READERS = (AGENT, "user:uma", "user:vera", "user:rob", "user:dora")
NEW_TOOLS = frozenset({"list_isolations", "list_gas_tests"})
NEW_ACTIONS = frozenset({"mcp.list_isolations", "mcp.list_gas_tests"})
FIELDS = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}


def load_world() -> ModuleType:
    """The ``permit_world`` helper of the permits tests, loaded by path."""
    name = "permit_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "permits" / "tests" / "permit_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env(tmp_path: Path, db: DbTarget) -> Iterator[McpHarness]:
    built = McpHarness.build(tmp_path, target=db)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def world(env: McpHarness) -> Any:
    made = load_world().World(env.db)
    made.people()
    return made


def call(env: McpHarness, tool: str, **arguments: Any) -> Any:
    return env.structured(tool, **arguments)


def refused(env: McpHarness, tool: str, **arguments: Any) -> str:
    try:
        asyncio.run(env.server.call_tool(tool, arguments))
    except ToolError as exc:
        return str(exc).removeprefix(f"Error executing tool {tool}: ")
    raise AssertionError(f"{tool} should have been refused")


def as_reader(env: McpHarness, actor: str, tool: str, **arguments: Any) -> Any:
    """The structured content of one call made as ``actor`` (a refusal raises ``ToolError``)."""
    server = build_server(env.factory, actor=actor)
    result = asyncio.run(server.call_tool(tool, arguments))
    assert isinstance(result, CallToolResult)
    assert not result.is_error
    return result.structured_content


def refused_as(env: McpHarness, actor: str, tool: str, **arguments: Any) -> str:
    server = build_server(env.factory, actor=actor)
    try:
        asyncio.run(server.call_tool(tool, arguments))
    except ToolError as exc:
        return str(exc).removeprefix(f"Error executing tool {tool}: ")
    raise AssertionError(f"{actor} should have been refused {tool}")


def test_five_readers_see_the_same_isolations_and_a_hidden_one_is_absent(
    env: McpHarness, world: Any
) -> None:
    permit = world.active("general", area="A1")
    world.isolation(permit)
    world.call("dora", "ApplyIsolation", **FIELDS, point_record_id=world.hidden_record())
    for reader in READERS:
        listing = as_reader(env, reader, "list_isolations", project=PROJECT, limit=50)
        assert listing["total"] == 1
        assert [r["key"] for r in listing["rows"]] == ["P123-ISL-0001"]
        assert "id" not in listing["rows"][0]


def test_five_readers_get_a_hidden_permits_tests_as_the_missing_key_error(
    env: McpHarness, world: Any
) -> None:
    visible = world.active("general", area="A1")
    world.gas_test(visible)
    hidden = world.request("dora", area="A2", for_record_id=world.hidden_record())
    world.gas_test(hidden)
    hidden_key = "P123-PTW-0002"
    unknown_key = "P123-PTW-9999"
    for reader in READERS:
        tests = as_reader(
            env, reader, "list_gas_tests", project=PROJECT, permit_key="P123-PTW-0001", limit=50
        )
        assert [t["key"] for t in tests["result"]] == ["P123-GAS-0001"]
        hidden_error = refused_as(
            env, reader, "list_gas_tests", project=PROJECT, permit_key=hidden_key, limit=50
        )
        unknown_error = refused_as(
            env, reader, "list_gas_tests", project=PROJECT, permit_key=unknown_key, limit=50
        )
        assert hidden_error == f"no permit {hidden_key}"
        assert unknown_error == f"no permit {unknown_key}"


def test_an_agent_with_no_allow_row_is_refused_both_reads(tmp_path: Path, db: DbTarget) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    env = McpHarness.build(tmp_path, target=db, authorize_hook=authorizer)
    try:
        world = load_world().World(env.db)
        world.people()
        permit = world.active("general")
        world.isolation(permit)
        world.gas_test(permit)
        for tool, arguments in (
            ("list_isolations", {"project": PROJECT, "limit": 50}),
            (
                "list_gas_tests",
                {"project": PROJECT, "permit_key": "P123-PTW-0001", "limit": 50},
            ),
        ):
            with pytest.raises(ToolError, match="not allowed"):
                env.call(tool, **arguments)
        allowed.update(NEW_ACTIONS)
        assert call(env, "list_isolations", project=PROJECT, limit=50)["total"] == 1
        tests = call(env, "list_gas_tests", project=PROJECT, permit_key="P123-PTW-0001", limit=50)
        assert len(tests["result"]) == 1
    finally:
        env.close()


def test_no_isolation_or_gas_tool_applies_verifies_removes_links_unlinks_or_records(
    env: McpHarness,
) -> None:
    names = {tool.name for tool in asyncio.run(env.server.list_tools())}
    assert {n for n in names if "isolation" in n or "gas" in n} == NEW_TOOLS
    for verb in ("apply", "verify", "remove", "link", "unlink", "record"):
        assert not any(verb in name for name in names if "isolation" in name or "gas" in name)


def test_a_failing_gas_test_shows_fail_and_a_permit_without_tests_answers_empty(
    env: McpHarness, world: Any
) -> None:
    tested = world.active("general", area="A1")
    world.gas_test(tested, result="fail")
    world.request("rob", area="A2")
    tests = call(env, "list_gas_tests", project=PROJECT, permit_key="P123-PTW-0001", limit=50)
    assert [t["result"] for t in tests["result"]] == ["fail"]
    empty = call(env, "list_gas_tests", project=PROJECT, permit_key="P123-PTW-0002", limit=50)
    assert empty["result"] == []


def test_the_two_actions_are_registered_and_closed_to_agents_until_allowed() -> None:
    for action in NEW_ACTIONS:
        assert action in MCP_ACTIONS
        assert action in PERMIT_MCP_ACTIONS
        assert not agent_may(action, AGENT_ACTIONS)
