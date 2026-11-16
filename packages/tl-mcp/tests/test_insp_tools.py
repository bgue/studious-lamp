"""The inspection MCP tools (P2-INSP-T07): four reads and propose_inspection, over a ledger built by
the quality module's own commands (``insp_world.py``, loaded by path, after ``punch_world.py``)."""

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
from tl_api.auth import Forbidden
from tl_core.auth.module_roles import holder_for_actor
from tl_core.auth.provider import agent_may
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.insp_tools import INSP_MCP_ACTIONS
from tl_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
AGENT = "agent:triage"
#: The five kinds of reader the walking tests use (ADR-0016).
READERS = ("agent:triage", "user:uma", "user:sue", "user:dora", "user:vera")
READS = ("list_inspections", "get_inspection", "list_checklists", "get_checklist")
PROPOSE = "propose_inspection"
#: Verbs that would change an inspection; no tool may carry one of them.
VERBS = frozenset({"schedule", "record", "verify", "reinspect", "cancel"})


def _load(name: str) -> ModuleType:
    """A quality test helper, loaded by path once (``insp_world`` imports ``punch_world``)."""
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_world() -> ModuleType:
    _load("punch_world")
    return _load("insp_world")


@pytest.fixture
def env(tmp_path: Path, db: DbTarget) -> Iterator[McpHarness]:
    built = McpHarness.build(tmp_path, target=db)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def world(env: McpHarness) -> Any:
    made = load_world().InspWorld(env.db)
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


def reader_refusal(env: McpHarness, actor: str, tool: str, **arguments: Any) -> str:
    try:
        as_reader(env, actor, tool, **arguments)
    except ToolError as exc:
        return str(exc).removeprefix(f"Error executing tool {tool}: ")
    raise AssertionError(f"{tool} should have been refused for {actor}")


def accept(env: McpHarness, made: dict[str, Any], who: str) -> Any:
    with open_uow(env.db) as uow:
        return proposals.accept_proposal(
            uow,
            proposal_id=made["proposal_id"],
            by=f"user:{who}",
            holds=lambda level: level == "user",
            holder=holder_for_actor(uow.conn(), f"user:{who}"),
        )


def inspection_keys(env: McpHarness) -> list[str]:
    with open_uow(env.db, readonly=True) as uow:
        found = uow.conn().execute(
            text(
                "SELECT r.key FROM cur_core_record r "
                "JOIN cur_quality_inspection i ON i.id = r.id ORDER BY r.key"
            )
        )
        return [str(k) for (k,) in found]


def key_of(env: McpHarness, record: str) -> str:
    with open_uow(env.db, readonly=True) as uow:
        return str(
            uow.conn()
            .execute(text("SELECT key FROM cur_core_record WHERE id = :i"), {"i": record})
            .scalar_one()
        )


def test_the_reads_return_rows_and_the_page_total(env: McpHarness, world: Any) -> None:
    iwp = world.record("awp.IWP", "P123-IWP-0001")
    world.plan(iwp)
    world.plan(iwp, point="review", area="L2")
    page = call(env, "list_inspections", project=PROJECT)
    assert page["total"] == 2
    assert [r["key"] for r in page["rows"]] == ["P123-INS-0001", "P123-INS-0002"]
    only = call(env, "list_inspections", project=PROJECT, point="review")
    assert only["total"] == 1
    assert only["rows"][0]["key"] == "P123-INS-0002"
    assert call(env, "list_inspections", project=PROJECT, state="Planned")["total"] == 2
    assert call(env, "list_inspections", project=PROJECT, state="Done")["total"] == 0
    limited = call(env, "list_inspections", project=PROJECT, limit=1)
    assert (limited["total"], len(limited["rows"])) == (2, 1)
    detail = call(env, "get_inspection", project=PROJECT, key="P123-INS-0001")
    assert detail["row"]["title"] == "Flange make-up"
    assert detail["row"]["state"] == "Planned"
    assert refused(env, "get_inspection", project=PROJECT, key="P123-INS-9999") == (
        "no inspection P123-INS-9999"
    )


def test_the_checklist_reads_return_rows_and_the_questions(env: McpHarness, world: Any) -> None:
    published = world.checklist()
    world.checklist(publish=False, title="Draft one")
    listed = call(env, "list_checklists", project=PROJECT)
    assert listed["total"] == 2
    only = call(env, "list_checklists", project=PROJECT, state="Published")
    assert [r["key"] for r in only["rows"]] == [key_of(env, published)]
    detail = call(env, "get_checklist", project=PROJECT, key=key_of(env, published))
    assert detail["row"]["state"] == "Published"
    assert len(detail["questions"]) == 3
    assert refused(env, "get_checklist", project=PROJECT, key="P123-CHK-9999") == (
        "no checklist P123-CHK-9999"
    )
    assert refused(env, "list_checklists", project=PROJECT, state="Bogus") == (
        "unknown checklist state"
    )


def test_a_reader_who_cannot_see_the_subject_gets_no_row_and_the_missing_key_text(
    env: McpHarness, world: Any
) -> None:
    secret = world.hidden_record()
    world.plan(world.record("awp.IWP", "P123-IWP-0001"))
    world.plan(secret, who="dora")
    assert inspection_keys(env) == ["P123-INS-0001", "P123-INS-0002"]
    for reader in READERS:
        listed = as_reader(env, reader, "list_inspections", project=PROJECT)
        assert listed["total"] == 1
        assert [r["key"] for r in listed["rows"]] == ["P123-INS-0001"]
        hidden = reader_refusal(env, reader, "get_inspection", project=PROJECT, key="P123-INS-0002")
        missing = reader_refusal(env, reader, "get_inspection", project=PROJECT, key="P123-INS-9")
        assert hidden == "no inspection P123-INS-0002"
        assert missing == "no inspection P123-INS-9"


def test_an_agent_without_an_allow_row_is_refused_every_tool(
    tmp_path: Path, db: DbTarget, world: Any
) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if not agent_may(action, frozenset(allowed)):
            raise Forbidden("closed")

    world.record("awp.IWP", "P123-IWP-0001")
    closed = McpHarness.build(tmp_path, target=db, authorize_hook=authorizer)
    try:
        calls: list[tuple[str, dict[str, Any]]] = [
            ("list_inspections", {"project": PROJECT}),
            ("get_inspection", {"project": PROJECT, "key": "P123-INS-0001"}),
            ("list_checklists", {"project": PROJECT}),
            ("get_checklist", {"project": PROJECT, "key": "P123-CHK-0001"}),
            (
                PROPOSE,
                {"project": PROJECT, "subject_key": "P123-IWP-0001", "title": "x", "point": "hold"},
            ),
        ]
        for tool, arguments in calls:
            assert refused(closed, tool, **arguments) == "not allowed: closed"
        allowed.update(INSP_MCP_ACTIONS)
        assert call(closed, "list_inspections", project=PROJECT)["total"] == 0
        assert call(closed, "list_checklists", project=PROJECT)["total"] == 0
        made = call(
            closed,
            PROPOSE,
            project=PROJECT,
            subject_key="P123-IWP-0001",
            title="Flange make-up",
            point="hold",
        )["proposal"]
        assert made["status"] == "pending"
        assert inspection_keys(closed) == []
    finally:
        closed.close()


def test_a_missing_or_hidden_subject_key_is_refused_with_one_text(
    env: McpHarness, world: Any
) -> None:
    secret = world.hidden_record()
    secret_key = key_of(env, secret)
    for key in ("P123-NOPE-0001", secret_key):
        message = refused(env, PROPOSE, project=PROJECT, subject_key=key, title="x", point="hold")
        assert message == "no record with that key"
    assert inspection_keys(env) == []


def test_propose_files_a_pending_proposal_that_changes_no_record(
    env: McpHarness, world: Any
) -> None:
    world.record("awp.IWP", "P123-IWP-0001")
    made = call(
        env,
        PROPOSE,
        project=PROJECT,
        subject_key="P123-IWP-0001",
        title="Flange make-up",
        point="witness",
        area="L1",
        planned_on="2026-12-01",
    )["proposal"]
    assert made["status"] == "pending"
    assert made["summary"] == "Plan inspection: Flange make-up"
    assert inspection_keys(env) == []


def test_accepting_the_proposal_plans_the_inspection_and_a_viewer_may_not(
    env: McpHarness, world: Any
) -> None:
    world.record("awp.IWP", "P123-IWP-0001")
    made = call(
        env,
        PROPOSE,
        project=PROJECT,
        subject_key="P123-IWP-0001",
        title="Flange make-up",
        point="hold",
    )["proposal"]
    with pytest.raises(ProposalAccessError):
        accept(env, made, "vera")  # a viewer lacks quality.inspection.plan
    assert inspection_keys(env) == []
    assert accept(env, made, "uma").status == "accepted"
    assert inspection_keys(env) == ["P123-INS-0001"]
    planned = call(env, "get_inspection", project=PROJECT, key="P123-INS-0001")
    assert planned["row"]["state"] == "Planned"


def test_no_tool_schedules_records_verifies_reinspects_or_cancels(env: McpHarness) -> None:
    names = {t.name for t in asyncio.run(env.server.list_tools())}
    banned = {
        "schedule_inspection",
        "record_inspection",
        "record_inspection_result",
        "verify_inspection",
        "reinspect_inspection",
        "cancel_inspection",
    }
    assert not banned & names
    assert not [n for n in names if "inspection" in n and n.split("_")[0] in VERBS]
    assert INSP_MCP_ACTIONS == {f"mcp.{t}" for t in (*READS, PROPOSE)}
    assert INSP_MCP_ACTIONS <= MCP_ACTIONS
    assert not {f"mcp.{n}" for n in banned} & MCP_ACTIONS


def test_the_inspection_tools_are_listed_and_the_reads_are_read_only(env: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    for name in (*READS, PROPOSE):
        assert name in tools
    for name in READS:
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
    annotations = tools[PROPOSE].annotations
    assert annotations is not None
    assert annotations.read_only_hint is not True
    assert annotations.destructive_hint is False


def test_the_five_readers_see_the_same_inspection_list(env: McpHarness, world: Any) -> None:
    secret = world.hidden_record()
    world.plan(world.record("awp.IWP", "P123-IWP-0001"))
    world.plan(secret, who="dora")
    for reader in READERS:
        listed = as_reader(env, reader, "list_inspections", project=PROJECT)
        assert listed["total"] == 1
        assert [r["key"] for r in listed["rows"]] == ["P123-INS-0001"]
