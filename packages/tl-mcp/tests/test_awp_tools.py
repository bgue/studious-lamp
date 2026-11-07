"""The awp MCP tools (T06): four read tools and propose_cwp, over the S4 seed ledger."""

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
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, require_command_access
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mcp.server import build_server
from tl_mod_awp.commands import CreateCwp

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
SCOPE = "project:P123"
AGENT = "agent:triage"


def load_world() -> ModuleType:
    """The ``awp_world`` helper of the module tests (the S4 seed ledger), loaded by path."""
    name = "awp_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def seed_awp(db: DbTarget) -> Any:
    world = load_world().World(db)
    world.people()
    world.editions()
    world.seed()
    return world


@pytest.fixture
def env(tmp_path: Path, db: DbTarget) -> Iterator[McpHarness]:
    built = McpHarness.build(tmp_path, target=db)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def seeded(env: McpHarness) -> McpHarness:
    seed_awp(env.db)
    return env


def call(env: McpHarness, tool: str, **arguments: Any) -> Any:
    return env.structured(tool, **arguments)


def refused(env: McpHarness, tool: str, **arguments: Any) -> str:
    try:
        asyncio.run(env.server.call_tool(tool, arguments))
    except ToolError as exc:
        return str(exc)
    raise AssertionError(f"{tool} should have been refused")


def cwp_count(env: McpHarness) -> int:
    with open_uow(env.db, readonly=True) as uow:
        return int(
            uow.conn()
            .execute(text("SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'"))
            .scalar_one()
        )


def test_the_awp_tools_are_listed_and_only_the_reads_are_read_only(env: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    reads = {"list_cwps", "get_cwp", "wbs_tree", "path_of_construction"}
    assert reads | {"propose_cwp"} <= set(tools)
    for name in reads:
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
    annotations = tools["propose_cwp"].annotations
    assert annotations is not None
    assert annotations.read_only_hint is not True
    assert annotations.destructive_hint is False


def test_list_cwps_filters_by_state_discipline_and_area(seeded: McpHarness) -> None:
    rows = call(seeded, "list_cwps", project=PROJECT)["result"]
    assert len(rows) == 6
    assert [r["number"] for r in rows] == sorted(r["number"] for r in rows)
    planned = call(seeded, "list_cwps", project=PROJECT, state="Planned")["result"]
    assert len(planned) == 2
    assert len(call(seeded, "list_cwps", project=PROJECT, discipline="CIV")["result"]) == 2
    assert len(call(seeded, "list_cwps", project=PROJECT, cwa="A1")["result"]) == 2


def test_get_cwp_has_the_view_fields_and_no_counts(seeded: McpHarness) -> None:
    detail = call(seeded, "get_cwp", project=PROJECT, number="P123-CWP-CIV-0001")
    assert detail["number"] == "P123-CWP-CIV-0001"
    assert detail["allocations"][0]["wbs_code"] == "1.2.1"
    assert "counts" not in detail
    assert "timeline" not in detail
    assert "link_count" not in detail


def test_a_missing_cwp_and_a_made_up_number_answer_alike(seeded: McpHarness) -> None:
    for number in ("P123-CWP-NOPE-9999", "P123-CWP-PIP-9999"):
        message = refused(seeded, "get_cwp", project=PROJECT, number=number)
        assert f"no CWP {number!r} in project {PROJECT!r}" in message
    assert "P123-CWP-PIP-9999" not in refused(seeded, "get_cwp", project="P999", number="x")


def test_wbs_tree_takes_a_depth(seeded: McpHarness) -> None:
    tree = call(seeded, "wbs_tree", project=PROJECT)["result"]
    top = call(seeded, "wbs_tree", project=PROJECT, depth=1)["result"]
    assert len(tree) == 9
    assert [n["code"] for n in top] == ["1"]


def test_path_of_construction_reads_a_version(seeded: McpHarness) -> None:
    world = load_world().World(seeded.db)
    world.call(
        "sue",
        "MoveCwaInPath",
        cwa_code="A4",
        to_position=1,
        reason_code="Access",
        expected_version=1,
    )
    now = call(seeded, "path_of_construction", project=PROJECT)["result"]
    assert (now["version"], now["current_version"]) == (2, 2)
    assert now["steps"][0]["cwa"] == "A4"
    first = call(seeded, "path_of_construction", project=PROJECT, version=1)["result"]
    assert first["steps"][0]["cwa"] == "A1"


def test_path_of_construction_is_null_for_no_path_or_an_unknown_version(
    seeded: McpHarness, env: McpHarness
) -> None:
    """D39: the view's None is the answer (a null result), not an error."""
    assert call(seeded, "path_of_construction", project=PROJECT, version=9) == {"result": None}
    assert call(seeded, "path_of_construction", project="P999") == {"result": None}


def test_propose_cwp_files_a_pending_proposal_and_creates_nothing(seeded: McpHarness) -> None:
    before = cwp_count(seeded)
    made = call(
        seeded,
        "propose_cwp",
        project=PROJECT,
        discipline="PIP",
        title="Proposed piping",
        cwa_code="A2",
    )["proposal"]
    assert made["status"] == "pending"
    assert made["summary"] == 'Create a PIP CWP "Proposed piping" in A2'
    assert cwp_count(seeded) == before
    assert len(call(seeded, "list_cwps", project=PROJECT)["result"]) == 6


def test_a_person_accepts_the_proposal_and_the_cwp_appears(seeded: McpHarness) -> None:
    made = call(
        seeded, "propose_cwp", project=PROJECT, discipline="PIP", title="Piping", cwa_code="A2",
        summary="Piping for A2",
    )["proposal"]  # fmt: skip
    assert made["summary"] == "Piping for A2"

    def accept(who: str) -> Any:
        with open_uow(seeded.db) as uow:
            return proposals.accept_proposal(
                uow,
                proposal_id=made["proposal_id"],
                by=f"user:{who}",
                holds=lambda level: level == "user",
                holder=holder_for_actor(uow.conn(), f"user:{who}"),
            )

    with pytest.raises(ProposalAccessError):
        accept("vera")  # a viewer has no awp.cwp.edit
    assert cwp_count(seeded) == 6
    assert accept("uma").status == "accepted"
    assert len(call(seeded, "list_cwps", project=PROJECT)["result"]) == 7


def test_the_agent_cannot_create_a_cwp_directly(seeded: McpHarness) -> None:
    command = CreateCwp(
        actor=AGENT,
        source="mcp:triage",
        scope=SCOPE,
        discipline="PIP",
        title="Agent piping",
        cwa_code="A2",
    )
    with open_uow(seeded.db) as uow:
        with pytest.raises(ForbiddenError):
            require_command_access(uow.conn(), command)
    assert cwp_count(seeded) == 6


def test_a_bad_argument_is_refused_by_the_tool_schema(seeded: McpHarness) -> None:
    refused(seeded, "propose_cwp", project=PROJECT, discipline="PIP", title="", cwa_code="A2")
    refused(seeded, "propose_cwp", project=PROJECT, discipline="PIP", title="x", cwa_code="a 2")
    refused(seeded, "wbs_tree", project=PROJECT, depth=0)
    assert cwp_count(seeded) == 6


def test_the_server_for_a_person_reads_the_same_fields(seeded: McpHarness, tmp_path: Path) -> None:
    server = build_server(seeded.factory, actor="user:uma", lake_dir=tmp_path / "lake2")
    result = asyncio.run(server.call_tool("list_cwps", {"project": PROJECT}))
    assert isinstance(result, CallToolResult)
    assert result.structured_content is not None
    assert len(result.structured_content["result"]) == 6
