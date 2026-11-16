"""The permit MCP tools (P2-PTW T08): three reads and propose_permit, over a ledger built by the
permits module's own commands (``permit_world.py``, loaded by path), as ``test_punch_tools.py``."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from mcp_types import CallToolResult
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_api.auth import Forbidden
from tl_core.auth.module_roles import holder_for_actor
from tl_core.auth.provider import AGENT_ACTIONS, agent_may
from tl_core.services import proposals
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.server import build_server
from tl_mod_permits import tools as permit_tools
from tl_mod_permits.names import PERMIT_TABLE
from tl_mod_permits.tools import PERMIT_MCP_ACTIONS

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
AGENT = "agent:triage"
READERS = (AGENT, "user:uma", "user:vera", "user:rob", "user:dora")
PERMIT_TOOLS = frozenset({"list_permits", "get_permit", "permit_board", "propose_permit"})
PROPOSAL = {
    "permit_type": "general",
    "area": "A1",
    "location_text": "Pump room",
    "work_description": "Weld repair, rack 12",
    "holder": "Rob",
    "needed_from": "2026-12-01",
    "needed_until": "2026-12-31",
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


def propose(env: McpHarness, **more: Any) -> Any:
    return call(env, "propose_permit", project=PROJECT, **{**PROPOSAL, **more})


def accept(env: McpHarness, proposal_id: str, who: str) -> Any:
    with open_uow(env.db) as uow:
        return proposals.accept_proposal(
            uow,
            proposal_id=proposal_id,
            by=f"user:{who}",
            holds=lambda level: level == "user",
            holder=holder_for_actor(uow.conn(), f"user:{who}"),
        )


def permit_count(env: McpHarness) -> int:
    with open_uow(env.db, readonly=True) as uow:
        return int(uow.conn().execute(text(f"SELECT count(*) FROM {PERMIT_TABLE}")).scalar_one())


def test_the_reads_return_rows_and_totals(env: McpHarness, world: Any) -> None:
    world.request("rob", area="A1")
    world.request("rob", area="A2", permit_type="hot_work")
    page = call(env, "list_permits", project=PROJECT)
    assert page["total"] == 2
    assert [r["key"] for r in page["rows"]] == ["P123-PTW-0001", "P123-PTW-0002"]
    only = call(env, "list_permits", project=PROJECT, area="A2")
    assert only["total"] == 1
    assert only["rows"][0]["permit_type"] == "hot_work"
    assert call(env, "list_permits", project=PROJECT, state="Active")["total"] == 0
    assert call(env, "list_permits", project=PROJECT, limit=1)["total"] == 2
    detail = call(env, "get_permit", project=PROJECT, key="P123-PTW-0001")
    assert detail["row"]["state"] == "Requested"
    assert refused(env, "get_permit", project=PROJECT, key="P123-PTW-9") == ("no permit P123-PTW-9")


def test_five_readers_see_the_same_permits_and_a_restricted_one_is_absent(
    env: McpHarness, world: Any
) -> None:
    world.active("general", area="A1")
    world.request("dora", area="A2", for_record_id=world.hidden_record())
    for reader in READERS:
        page = as_reader(env, reader, "list_permits", project=PROJECT)
        board = as_reader(env, reader, "permit_board", project=PROJECT)
        assert page["total"] == 1
        assert [r["key"] for r in page["rows"]] == ["P123-PTW-0001"]
        assert board["counts"]["Active"] == 1
        assert [r["key"] for a in board["areas"] for r in a["rows"]] == ["P123-PTW-0001"]
        assert refused_as(env, reader, "get_permit", project=PROJECT, key="P123-PTW-0002") == (
            "no permit P123-PTW-0002"
        )


def test_an_agent_with_no_allow_row_is_refused_every_tool(tmp_path: Path, db: DbTarget) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    env = McpHarness.build(tmp_path, target=db, authorize_hook=authorizer)
    try:
        world = load_world().World(env.db)
        world.people()
        permit = world.request("rob")
        for tool, arguments in (
            ("list_permits", {"project": PROJECT}),
            ("get_permit", {"project": PROJECT, "key": "P123-PTW-0001"}),
            ("permit_board", {"project": PROJECT}),
            ("propose_permit", {"project": PROJECT, **PROPOSAL}),
        ):
            with pytest.raises(ToolError, match="not allowed"):
                env.call(tool, **arguments)
        allowed.update(PERMIT_MCP_ACTIONS)
        assert call(env, "list_permits", project=PROJECT)["total"] == 1
        assert call(env, "get_permit", project=PROJECT, key="P123-PTW-0001")["row"]["id"] == (
            permit
        )
        filed = propose(env, area="A9")
        assert filed["proposal"]["status"] == "pending"
        assert filed["proposal"]["command_type"] == "RequestPermit"
        assert permit_count(env) == 1
    finally:
        env.close()


def test_propose_files_a_pending_proposal_that_creates_no_permit(
    env: McpHarness, world: Any
) -> None:
    filed = propose(env, area="A3")
    assert filed["proposal"]["status"] == "pending"
    assert filed["proposal"]["tool"] == "propose_permit"
    assert permit_count(env) == 0


def test_a_person_with_the_request_word_accepts_and_is_the_requester(
    env: McpHarness, world: Any
) -> None:
    filed = propose(env, area="A4")
    accept(env, filed["proposal"]["proposal_id"], "rob")
    page = call(env, "list_permits", project=PROJECT)
    assert page["total"] == 1
    detail = call(env, "get_permit", project=PROJECT, key=page["rows"][0]["key"])
    assert detail["requested_by"] == "user:rob"


def test_a_person_without_the_request_word_cannot_accept(env: McpHarness, world: Any) -> None:
    filed = propose(env, area="A5")
    with pytest.raises(Exception, match="access word"):
        accept(env, filed["proposal"]["proposal_id"], "vera")
    assert permit_count(env) == 0


def test_for_key_resolves_to_the_record_the_permit_is_for(env: McpHarness, world: Any) -> None:
    world.record("awp.IWP", "P123-IWP-0001")
    filed = propose(env, area="A6", for_key="P123-IWP-0001")
    assert filed["proposal"]["status"] == "pending"
    unknown = {**PROPOSAL, "for_key": "P123-IWP-9999"}
    assert refused(env, "propose_permit", project=PROJECT, **unknown) == ("no record with that key")


def test_no_tool_approves_issues_suspends_resumes_hands_back_closes_or_cancels(
    env: McpHarness,
) -> None:
    names = {tool.name for tool in asyncio.run(env.server.list_tools())}
    assert {n for n in names if "permit" in n} == PERMIT_TOOLS
    for verb in ("approve", "issue", "suspend", "resume", "hand_back", "close", "cancel"):
        assert not any(verb in name for name in names if "permit" in name)


def test_a_lapsed_permit_shows_lapsed_in_every_read(
    env: McpHarness, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.active("general")
    later = datetime(2026, 12, 2, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(permit_tools, "utcnow", lambda: later)
    listed = call(env, "list_permits", project=PROJECT, state="Lapsed")
    assert listed["total"] == 1
    assert listed["rows"][0]["state"] == "Lapsed"
    assert call(env, "get_permit", project=PROJECT, key="P123-PTW-0001")["row"]["state"] == (
        "Lapsed"
    )
    board = call(env, "permit_board", project=PROJECT)
    assert board["counts"]["Lapsed"] == 1
    assert board["areas"][0]["rows"][0]["state"] == "Lapsed"


def test_the_permit_tools_are_closed_to_agents_until_listed() -> None:
    for action in PERMIT_MCP_ACTIONS:
        assert action in MCP_ACTIONS
        assert not agent_may(action, AGENT_ACTIONS)
