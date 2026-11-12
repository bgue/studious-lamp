"""The requisition MCP tools (T08b): four reads and propose_requisition.

The ledger is built through the requisitions ``req_world`` helper (loaded by path, as the awp tool
tests load ``awp_world``), so every row comes from a command, never from a projection write.
"""

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
from tl_adapters.db import DbTarget
from tl_core.services import proposals
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.requisition_tools import REQUISITION_MCP_ACTIONS
from tl_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
IWP = "awp.IWP"
ITEM = "materials.ProjectItem"
READS = {"list_requisitions", "get_requisition", "list_work_orders", "get_work_order"}
ACTORS = ["agent:triage", "user:bob", "user:uma", "user:sue", "user:ada"]
FAKE_KEY = "P123-REQ-LAB-9999"
LABOR_ARGS: dict[str, Any] = {
    "kind": "labor",
    "subject": "Six pipefitters",
    "craft": "Pipefitter",
    "headcount": 6,
    "start_date": "2026-11-02",
    "end_date": "2026-11-13",
}


def load_world() -> ModuleType:
    """The ``req_world`` helper of the requisitions tests, loaded by path."""
    name = "req_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "requisitions" / "tests" / "req_world.py"
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
    made.editions()
    made.record(IWP, "P123-IWP-0001")
    made.record(ITEM, "P123-ITEM-0001")
    return made


def refused(env: McpHarness, tool: str, **arguments: Any) -> str:
    try:
        asyncio.run(env.server.call_tool(tool, arguments))
    except ToolError as exc:
        return str(exc)
    raise AssertionError(f"{tool} should have been refused")


def text_of(server: Any, tool: str, args: dict[str, Any]) -> str:
    try:
        result = asyncio.run(server.call_tool(tool, args))
    except ToolError as exc:
        return f"ERROR {exc}"
    return result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)


def key_of(world: Any, record: str) -> str:
    return str(world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=record)[0]["key"])


def id_of(world: Any, key: str) -> str:
    return str(world.rows("SELECT id FROM cur_core_record WHERE key = :k", k=key)[0]["id"])


def accepted(env: McpHarness, out: dict[str, Any], by: str) -> None:
    assert out["proposal"]["status"] == "pending"
    result = proposals.accept_or_fail(
        env.factory, proposal_id=out["proposal"]["proposal_id"], by=by
    )
    assert result.status == "accepted"


def test_the_requisition_tools_are_listed_and_only_the_reads_are_read_only(env: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    assert READS | {"propose_requisition"} <= set(tools)
    for name in READS:
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
    annotations = tools["propose_requisition"].annotations
    assert annotations is not None
    assert annotations.read_only_hint is not True
    assert annotations.destructive_hint is False


def test_the_four_reads_return_rows(env: McpHarness, world: Any) -> None:
    rid, wid = world.approved("uma", "sue")
    pending = world.raise_labor("uma")
    approved_key = key_of(world, rid)
    wo_key = key_of(world, wid)
    assert key_of(world, pending) != approved_key

    listed = env.structured("list_requisitions", project=PROJECT, kind="labor")["result"]
    assert {r["key"] for r in listed} == {approved_key, key_of(world, pending)}
    assert [
        r["key"]
        for r in env.structured("list_requisitions", project=PROJECT, requester="user:sue")[
            "result"
        ]
    ] == []

    detail = env.structured("get_requisition", project=PROJECT, key=approved_key)
    assert detail["row"]["key"] == approved_key
    assert detail["work_order"]["key"] == wo_key

    orders = env.structured("list_work_orders", project=PROJECT)["result"]
    assert [o["key"] for o in orders] == [wo_key]

    order = env.structured("get_work_order", project=PROJECT, key=wo_key)
    assert order["requisition_key"] == approved_key


def test_a_missing_key_and_a_key_of_another_project_give_one_text(
    env: McpHarness, world: Any
) -> None:
    rid, wid = world.approved("uma", "sue")
    approved_key = key_of(world, rid)
    missing = refused(env, "get_requisition", project=PROJECT, key=FAKE_KEY)
    assert f"no requisition {FAKE_KEY!r} in project {PROJECT!r}" in missing
    other = refused(env, "get_requisition", project="P999", key=approved_key)
    assert other.replace(approved_key, FAKE_KEY).replace("P999", PROJECT) == missing

    wo_key = key_of(world, wid)
    missing_wo = refused(env, "get_work_order", project=PROJECT, key="P123-WO-9999")
    other_wo = refused(env, "get_work_order", project="P999", key=wo_key)
    assert other_wo.replace(wo_key, "P123-WO-9999").replace("P999", PROJECT) == missing_wo


@pytest.mark.parametrize("approver", ["user:uma", "user:sue"])
def test_a_labour_proposal_is_pending_until_a_person_accepts_it(
    env: McpHarness, world: Any, approver: str
) -> None:
    out = env.structured("propose_requisition", project=PROJECT, **LABOR_ARGS)
    assert out["message"].startswith("Proposal ")
    assert world.rows("SELECT key FROM cur_core_record WHERE key LIKE 'P123-REQ-%'") == []
    assert env.structured("list_requisitions", project=PROJECT)["result"] == []

    accepted(env, out, approver)
    key = "P123-REQ-LAB-0001"
    requisition = world.requisition(id_of(world, key))
    assert requisition["requester"] == approver
    assert requisition["requester"] != "agent:triage"


def test_a_proposal_for_an_iwp_names_it_and_the_accepting_person_requests(
    env: McpHarness, world: Any
) -> None:
    out = env.structured(
        "propose_requisition", project=PROJECT, for_key="P123-IWP-0001", **LABOR_ARGS
    )
    accepted(env, out, "user:uma")
    requisition = world.requisition(id_of(world, "P123-REQ-LAB-0001"))
    assert requisition["for_record_id"] == id_of(world, "P123-IWP-0001")
    assert requisition["requester"] == "user:uma"


def test_a_material_proposal_with_an_item_key_is_accepted_into_lines(
    env: McpHarness, world: Any
) -> None:
    out = env.structured(
        "propose_requisition",
        project=PROJECT,
        kind="material",
        subject="Pipe for level two",
        lines=[{"item": "P123-ITEM-0001", "qty": "4", "uom": "EA"}],
    )
    assert world.rows("SELECT key FROM cur_core_record WHERE key LIKE 'P123-REQ-%'") == []
    accepted(env, out, "user:uma")
    requisition = world.requisition(id_of(world, "P123-REQ-MAT-0001"))
    assert id_of(world, "P123-ITEM-0001") in str(requisition["lines_json"])


def test_an_unknown_for_key_or_item_key_is_refused_with_the_one_text(
    env: McpHarness, world: Any
) -> None:
    bad_for = refused(
        env, "propose_requisition", project=PROJECT, for_key="P123-IWP-9999", **LABOR_ARGS
    )
    assert bad_for.endswith("no record with that key")
    bad_item = refused(
        env,
        "propose_requisition",
        project=PROJECT,
        kind="material",
        subject="Pipe",
        lines=[{"item": "P123-ITEM-9999", "qty": "1", "uom": "EA"}],
    )
    assert bad_item.endswith("no record with that key")


def test_a_bad_kind_combination_is_refused_with_the_model_text(env: McpHarness, world: Any) -> None:
    message = refused(env, "propose_requisition", project=PROJECT, kind="labor", subject="Six")
    assert "craft" in message or "headcount" in message
    assert world.rows("SELECT key FROM cur_core_record WHERE key LIKE 'P123-REQ-%'") == []


def test_an_agent_cannot_approve_and_the_five_words_are_the_listed_ones(env: McpHarness) -> None:
    assert REQUISITION_MCP_ACTIONS == {
        "mcp.list_requisitions",
        "mcp.get_requisition",
        "mcp.list_work_orders",
        "mcp.get_work_order",
        "mcp.propose_requisition",
    }
    assert REQUISITION_MCP_ACTIONS <= MCP_ACTIONS
    assert "mcp.approve_requisition" not in MCP_ACTIONS
    names = {t.name for t in asyncio.run(env.server.list_tools())}
    assert "approve_requisition" not in names
    with pytest.raises(ToolError):
        asyncio.run(
            env.server.call_tool("approve_requisition", {"project": PROJECT, "key": FAKE_KEY})
        )


@pytest.mark.parametrize("actor", ACTORS)
def test_every_reader_sees_the_open_requisition_and_a_made_up_key_gets_one_text(
    tmp_path: Path, db: DbTarget, world: Any, actor: str
) -> None:
    rid, wid = world.approved("uma", "sue")
    key = key_of(world, rid)
    wo_key = key_of(world, wid)
    env = McpHarness.build(tmp_path, target=db)
    try:
        server = build_server(env.factory, actor=actor, lake_dir=tmp_path / "lake")
        for tool, args, found in (
            ("get_requisition", {"project": PROJECT, "key": key}, key),
            ("get_work_order", {"project": PROJECT, "key": wo_key}, wo_key),
            ("list_requisitions", {"project": PROJECT}, key),
            ("list_work_orders", {"project": PROJECT}, wo_key),
        ):
            reply = text_of(server, tool, args)
            assert "internal error" not in reply.lower()
            assert found in reply, (actor, tool)
        missing = text_of(server, "get_requisition", {"project": PROJECT, "key": FAKE_KEY})
        assert f"no requisition {FAKE_KEY!r} in project {PROJECT!r}" in missing
    finally:
        env.close()
