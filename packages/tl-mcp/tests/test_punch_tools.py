"""The punch MCP tools (P2-PUNCH-T05): two reads and propose_punch_item, over a ledger built by the
quality module's own commands (``punch_world.py``, loaded by path)."""

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
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.auth.module_roles import holder_for_actor
from tl_core.auth.provider import AGENT_ACTIONS, agent_may
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.punch_tools import PUNCH_MCP_ACTIONS
from tl_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
AGENT = "agent:triage"


def load_world() -> ModuleType:
    """The ``punch_world`` helper of the quality tests, loaded by path."""
    name = "punch_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / "punch_world.py"
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


def accept(env: McpHarness, made: dict[str, Any], who: str) -> Any:
    with open_uow(env.db) as uow:
        return proposals.accept_proposal(
            uow,
            proposal_id=made["proposal_id"],
            by=f"user:{who}",
            holds=lambda level: level == "user",
            holder=holder_for_actor(uow.conn(), f"user:{who}"),
        )


def punch_rows(env: McpHarness) -> list[tuple[str, str]]:
    with open_uow(env.db, readonly=True) as uow:
        found = uow.conn().execute(
            text(
                "SELECT r.key, t.raised_by FROM cur_core_record r "
                "JOIN cur_quality_punch_item t ON t.id = r.id ORDER BY r.key"
            )
        )
        return [(str(k), str(by)) for k, by in found]


def punch_id(env: McpHarness, key: str) -> str:
    with open_uow(env.db, readonly=True) as uow:
        return str(
            uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE key = :k"), {"k": key})
            .scalar_one()
        )


def key_of(env: McpHarness, record: str) -> str:
    with open_uow(env.db, readonly=True) as uow:
        return str(
            uow.conn()
            .execute(text("SELECT key FROM cur_core_record WHERE id = :i"), {"i": record})
            .scalar_one()
        )


def test_the_reads_return_rows_and_the_page_total(env: McpHarness, world: Any) -> None:
    world.raise_item("uma", "Guard missing", area="L1")
    world.raise_item("uma", "Door loose", area="L2")
    page = call(env, "list_punch_items", project=PROJECT)
    assert page["total"] == 2
    assert [r["key"] for r in page["rows"]] == ["P123-PUN-0001", "P123-PUN-0002"]
    only = call(env, "list_punch_items", project=PROJECT, area="L1")
    assert only["total"] == 1
    assert only["rows"][0]["subject"] == "Guard missing"
    assert call(env, "list_punch_items", project=PROJECT, state="Cleared")["total"] == 0
    detail = call(env, "get_punch_item", project=PROJECT, key="P123-PUN-0001")
    assert detail["row"]["subject"] == "Guard missing"
    assert detail["row"]["state"] == "Open"
    assert refused(env, "get_punch_item", project=PROJECT, key="P123-PUN-9") == (
        "no punch item P123-PUN-9"
    )


def test_a_missing_key_and_a_key_of_another_project_give_one_text(
    env: McpHarness, world: Any
) -> None:
    world.raise_item("uma", "Guard missing")
    missing = refused(env, "get_punch_item", project=PROJECT, key="P123-PUN-9999")
    other = refused(env, "get_punch_item", project="P999", key="P123-PUN-0001")
    assert missing == "no punch item P123-PUN-9999"
    assert other == "no punch item P123-PUN-0001"


def test_propose_files_a_pending_proposal_and_a_person_accepts_it(
    env: McpHarness, world: Any
) -> None:
    made = call(env, "propose_punch_item", project=PROJECT, subject="Gap at door", area="L1")[
        "proposal"
    ]
    assert made["status"] == "pending"
    assert made["summary"] == "Raise punch item: Gap at door"
    assert punch_rows(env) == []
    with pytest.raises(ProposalAccessError):
        accept(env, made, "vera")  # a viewer may not raise punch items
    assert punch_rows(env) == []
    assert accept(env, made, "uma").status == "accepted"
    assert punch_rows(env) == [("P123-PUN-0001", "user:uma")]  # raised by the person, not the agent


def test_propose_from_an_iwp_key_links_the_item_after_accept(env: McpHarness, world: Any) -> None:
    iwp = world.record("awp.IWP", "P123-IWP-0001")
    made = call(
        env,
        "propose_punch_item",
        project=PROJECT,
        subject="Gap at IWP",
        from_key="P123-IWP-0001",
        category="A",
    )["proposal"]
    assert accept(env, made, "uma").status == "accepted"
    links = world.links_from(punch_id(env, "P123-PUN-0001"))
    assert any(ln["relation"] == "raised_against" and ln["to_id"] == iwp for ln in links)


def test_an_unknown_or_hidden_from_key_is_refused_with_one_text(
    env: McpHarness, world: Any
) -> None:
    secret = world.hidden_record()
    secret_key = key_of(env, secret)
    unknown = "P123-NOPE-0001"
    for key in (unknown, secret_key):
        message = refused(env, "propose_punch_item", project=PROJECT, subject="x", from_key=key)
        assert message == "no record with that key"
    assert punch_rows(env) == []


def test_an_item_raised_from_a_restricted_record_is_absent_for_the_agent(
    env: McpHarness, world: Any
) -> None:
    secret = world.hidden_record()
    world.raise_item("uma", "Open one")
    world.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret)
    hidden_key = "P123-PUN-0002"
    assert world.scalar("SELECT count(*) FROM cur_quality_punch_item") == 2
    page = call(env, "list_punch_items", project=PROJECT)
    assert page["total"] == 1
    assert [r["subject"] for r in page["rows"]] == ["Open one"]
    assert refused(env, "get_punch_item", project=PROJECT, key=hidden_key) == (
        f"no punch item {hidden_key}"
    )


@pytest.mark.parametrize(
    "actor", ["agent:triage", "user:uma", "user:sue", "user:dora", "user:vera"]
)
def test_five_kinds_of_reader_see_the_same_punch_list(
    env: McpHarness, world: Any, actor: str
) -> None:
    secret = world.hidden_record()
    world.raise_item("uma", "Open one")
    world.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret)
    listed = as_reader(env, actor, "list_punch_items", project=PROJECT)
    assert listed["total"] == 1
    assert [r["subject"] for r in listed["rows"]] == ["Open one"]
    with pytest.raises(ToolError, match="no punch item P123-PUN-0002"):
        as_reader(env, actor, "get_punch_item", project=PROJECT, key="P123-PUN-0002")


def test_clear_and_verify_are_neither_tools_nor_open_to_agents() -> None:
    assert PUNCH_MCP_ACTIONS == {
        "mcp.list_punch_items",
        "mcp.get_punch_item",
        "mcp.propose_punch_item",
    }
    assert PUNCH_MCP_ACTIONS <= MCP_ACTIONS
    for action in ("mcp.clear_punch_item", "mcp.verify_punch_item"):
        assert action not in MCP_ACTIONS
        assert not agent_may(action, AGENT_ACTIONS | MCP_ACTIONS)
    for action in PUNCH_MCP_ACTIONS:
        assert agent_may(action, AGENT_ACTIONS | MCP_ACTIONS)


def test_the_punch_tools_are_listed_and_the_reads_are_read_only(env: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    for name in ("clear_punch_item", "verify_punch_item"):
        assert name not in tools
    for name in ("list_punch_items", "get_punch_item"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
    annotations = tools["propose_punch_item"].annotations
    assert annotations is not None
    assert annotations.read_only_hint is not True
    assert annotations.destructive_hint is False
