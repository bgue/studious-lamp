"""The forms MCP tools (V3-F2): four reads and the proposal, over a ledger built by the forms
module's own commands (``forms_world.py``, loaded by path), as ``test_permit_tools.py``."""

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
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_api.auth import Forbidden
from tl_core.auth.module_roles import holder_for_actor
from tl_core.auth.provider import AGENT_ACTIONS, agent_may
from tl_core.services import proposals
from tl_mcp.identity import MCP_ACTIONS
from tl_mod_forms.names import SUBMISSION_TABLE
from tl_mod_forms.tools import FORMS_MCP_ACTIONS

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
FORM_TOOLS = frozenset(
    {
        "list_form_templates",
        "get_form",
        "list_form_submissions",
        "get_form_submission",
        "propose_form_submission",
    }
)
ANSWERS = [{"q": "topic", "value": "Ladders", "note": None}]


def load_world() -> ModuleType:
    name = "forms_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "forms" / "tests" / "forms_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env(tmp_path: Path) -> Iterator[McpHarness]:
    built = McpHarness.build(tmp_path)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def world(env: McpHarness) -> Any:
    made = load_world().World(env.db)
    made.people()
    return made


def refused(env: McpHarness, tool: str, **arguments: Any) -> str:
    try:
        asyncio.run(env.server.call_tool(tool, arguments))
    except ToolError as exc:
        return str(exc).removeprefix(f"Error executing tool {tool}: ")
    raise AssertionError(f"{tool} should have been refused")


def submissions(env: McpHarness) -> int:
    with open_uow(env.db, readonly=True) as uow:
        return int(
            uow.conn().execute(text(f"SELECT count(*) FROM {SUBMISSION_TABLE}")).scalar_one()
        )


def accept(env: McpHarness, proposal_id: str, who: str) -> Any:
    with open_uow(env.db) as uow:
        return proposals.accept_proposal(
            uow,
            proposal_id=proposal_id,
            by=f"user:{who}",
            holds=lambda level: level == "user",
            holder=holder_for_actor(uow.conn(), f"user:{who}"),
        )


def test_the_reads_return_published_templates_as_json_schema_and_submissions(
    env: McpHarness, world: Any
) -> None:
    template = world.template()
    world.template(publish=False)
    key = str(world.key(template))
    listed = env.structured("list_form_templates")
    assert listed["total"] == 1
    assert listed["rows"][0]["key"] == key
    schema = env.structured("get_form", key=key)
    assert schema["type"] == "array"
    assert env.structured("get_form", key=key, version=1) == schema
    assert "model" in env.structured("get_form", key=key, projection="surveyjs")
    assert refused(env, "get_form", key=key, version=9) == refused(env, "get_form", key="TPL-9999")
    made = world.submit("uma", template)
    page = env.structured("list_form_submissions", project=PROJECT)
    assert page["total"] == 1
    assert page["rows"][0]["key"] == made.key
    got = env.structured("get_form_submission", project=PROJECT, key=made.key)
    assert got["answers"][0]["value"] == "Ladders"
    assert env.structured("list_form_submissions", project=PROJECT, state="Accepted")["total"] == 0


def test_an_own_draft_of_a_person_is_never_listed_or_read_by_an_agent(
    env: McpHarness, world: Any
) -> None:
    template = world.template()
    draft = world.save("uma", template)
    page = env.structured("list_form_submissions", project=PROJECT)
    assert page == {"rows": [], "total": 0}
    for ref in (str(draft.stream_id), str(draft.key)):
        assert "no such submission" in refused(env, "get_form_submission", project=PROJECT, key=ref)


def test_a_draft_stays_out_even_if_the_viewer_were_its_author(
    env: McpHarness, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Belt and braces: the tools drop a Draft row themselves, whoever the viewer is."""
    from tl_core import confidentiality

    template = world.template()
    draft = world.save("uma", template)
    world.submit("uma", template)
    author = confidentiality.Viewer(actor="user:uma", level=0, account="uma")
    monkeypatch.setattr(confidentiality, "current_viewer", lambda: author)
    page = env.structured("list_form_submissions", project=PROJECT)
    assert [r["state"] for r in page["rows"]] == ["Submitted"]
    assert page["total"] == 1
    assert "no such submission" in refused(
        env, "get_form_submission", project=PROJECT, key=str(draft.stream_id)
    )


def test_propose_files_a_pending_proposal_and_a_person_who_accepts_is_the_author(
    env: McpHarness, world: Any
) -> None:
    template = world.template()
    key = str(world.key(template))
    filed = env.structured(
        "propose_form_submission", project=PROJECT, template_key=key, answers=ANSWERS
    )
    assert filed["proposal"]["status"] == "pending"
    assert filed["proposal"]["command_type"] == "SubmitForm"
    assert filed["proposal"]["tool"] == "propose_form_submission"
    assert submissions(env) == 0
    accept(env, filed["proposal"]["proposal_id"], "rob")
    page = env.structured("list_form_submissions", project=PROJECT)
    assert page["total"] == 1
    assert page["rows"][0]["author"] == "user:rob"
    assert page["rows"][0]["state"] == "Submitted"


def test_a_proposal_names_a_visible_subject_and_refuses_an_unknown_one(
    env: McpHarness, world: Any
) -> None:
    template = world.template()
    key = str(world.key(template))
    world.record("awp.IWP", "P123-IWP-0001")
    filed = env.structured(
        "propose_form_submission",
        project=PROJECT,
        template_key=key,
        answers=ANSWERS,
        subject_key="P123-IWP-0001",
    )
    assert filed["proposal"]["status"] == "pending"
    assert refused(
        env,
        "propose_form_submission",
        project=PROJECT,
        template_key=key,
        answers=ANSWERS,
        subject_key="P123-IWP-9999",
    ) == ("no record with that key")


def test_no_tool_saves_reviews_voids_publishes_or_retires(env: McpHarness) -> None:
    names = {tool.name for tool in asyncio.run(env.server.list_tools())}
    assert {n for n in names if "form" in n} == FORM_TOOLS
    for verb in ("draft", "save", "accept", "return", "void", "publish", "retire", "discard"):
        assert not any(verb in name for name in names if "form" in name)


def test_an_agent_with_no_allow_row_is_refused_every_tool(tmp_path: Path) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    env = McpHarness.build(tmp_path, authorize_hook=authorizer)
    try:
        for tool, arguments in (
            ("list_form_templates", {}),
            ("get_form", {"key": "TPL-0001"}),
            ("list_form_submissions", {"project": PROJECT}),
            ("get_form_submission", {"project": PROJECT, "key": "P123-FRM-0001"}),
            (
                "propose_form_submission",
                {"project": PROJECT, "template_key": "TPL-0001", "answers": ANSWERS},
            ),
        ):
            with pytest.raises(ToolError, match="not allowed"):
                env.call(tool, **arguments)
        allowed.update(FORMS_MCP_ACTIONS)
        assert env.structured("list_form_templates")["total"] == 0
    finally:
        env.close()


def test_the_forms_tools_are_the_only_opening_for_agents_and_the_routes_stay_closed() -> None:
    assert FORMS_MCP_ACTIONS == {f"mcp.{name}" for name in FORM_TOOLS}
    for action in FORMS_MCP_ACTIONS:
        assert action in MCP_ACTIONS
        assert not agent_may(action, AGENT_ACTIONS)  # open only through ``MCP_ACTIONS``
    assert not agent_may("forms.read", MCP_ACTIONS | AGENT_ACTIONS)
