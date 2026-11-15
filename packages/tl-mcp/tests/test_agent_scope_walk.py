"""P2-X2-T04 (MCP): the agent scope walks through the proposing tools.

(a) the proposing tool ``create_record``, called by an agent with no module word on ``project:P1``
    and by the same agent on a scope that does not exist, answers the same error code and text
    (the refusal reads as a missing scope, 140);
(b) at the queue cap the tool answers the fixed queue text, with no digit;
(c) no MCP tool name contains ``stop`` or ``resume``: an agent cannot stop itself or another.

The no-word case calls the server directly: ``McpHarness.call`` grants the word first (trap 1).
"""

from __future__ import annotations

import asyncio
import re

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from tl_core.auth import accounts
from tl_core.services.agent_scope import QUEUE_CAP_SETTING, QUEUE_FULL_TEXT
from tl_core.services.settings import ChangeSetting, handle_change_setting

NOPE = "project:NOPE"  # a scope that does not exist: not in PROJECTS
TOOL = "create_record"


def bare_agent(env: McpHarness) -> None:
    """The server's agent account with the role ``user`` and no explicit module grant."""
    with env.factory(False) as uow:
        accounts.create_account(
            uow, username=ACTOR.partition(":")[2], display_name="Triage", kind="agent",
            roles=["user"], password=None, by="svc:test",
        )  # fmt: skip


def raw_error(env: McpHarness, scope: str, key: str) -> ToolError:
    """The tool called directly (no grant is made): the refusal the SDK raises."""
    with pytest.raises(ToolError) as caught:
        asyncio.run(
            env.server.call_tool(TOOL, {"scope": scope, "title": "walk", "key": key})
        )  # fmt: skip
    return caught.value


def test_a_bare_agents_refusal_is_the_same_as_a_missing_scope(env: McpHarness) -> None:
    bare_agent(env)
    on_p1 = raw_error(env, SCOPE, "WALK-MCP-A")
    on_nope = raw_error(env, NOPE, "WALK-MCP-A")
    assert type(on_p1) is type(on_nope)
    assert str(on_p1).replace(SCOPE, NOPE) == str(on_nope), (str(on_p1), str(on_nope))
    assert "no scope" in str(on_nope)


def test_the_word_makes_the_same_filing_pass(env: McpHarness) -> None:
    out = env.structured(TOOL, scope=SCOPE, title="walk", key="WALK-MCP-A2")
    assert isinstance(out, dict) and out["proposal"]["proposal_id"]


def test_a_full_queue_answers_the_fixed_text_with_no_digit(env: McpHarness) -> None:
    with env.factory(False) as uow:
        handle_change_setting(
            uow,
            ChangeSetting(
                actor="user:ada",
                source="test",
                scope=SCOPE,
                key=QUEUE_CAP_SETTING,
                layer=SCOPE,
                value=2,
                reason="test",
                accept_risk=True,
            ),
        )
    for n in range(2):
        env.structured(TOOL, scope=SCOPE, title=f"walk {n}", key=f"WALK-MCP-B-{n}")
    with pytest.raises(ToolError) as full:
        env.call(TOOL, scope=SCOPE, title="walk full", key="WALK-MCP-B-FULL")
    assert str(full.value) == f"Error executing tool {TOOL}: {QUEUE_FULL_TEXT}"
    assert re.search(r"\d", str(full.value)) is None


def test_no_mcp_tool_can_stop_or_resume_an_agent(env: McpHarness) -> None:
    names = [tool.name for tool in asyncio.run(env.server.list_tools())]
    assert names, "the tool list is empty: the walk would pass by finding nothing"
    assert [name for name in names if "stop" in name or "resume" in name] == []
