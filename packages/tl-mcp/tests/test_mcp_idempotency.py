"""Idempotency keys on the MCP proposing tools (P2-X1-T03): one key, one proposal."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from tl_mcp.server import build_server

OTHER_ACTOR = "agent:other"
KEY = "weld-ncr-0042-r1"


def proposal_events(env: McpHarness) -> list[Any]:
    with env.factory(True) as uow:
        found = uow.ledger.read_after(0, limit=1000)
    return [e for e in found if e.event_type == "Proposal.Created"]


def create(env: McpHarness, title: str = "Weld NCR", **extra: Any) -> dict[str, Any]:
    out = env.structured("create_record", scope=SCOPE, title=title, key="P123-REC-0042", **extra)
    assert isinstance(out, dict)
    return out


def test_create_record_twice_with_one_key_files_one_proposal(env: McpHarness) -> None:
    first = create(env, idempotency_key=KEY)
    second = create(env, idempotency_key=KEY)
    assert first == second
    assert first["proposal"]["proposal_id"] == second["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 1


def test_same_key_with_another_title_is_refused_and_files_nothing_new(env: McpHarness) -> None:
    first = create(env, idempotency_key=KEY)
    with pytest.raises(ToolError, match="already used for a different request"):
        create(env, title="Cut NCR", idempotency_key=KEY)
    assert len(proposal_events(env)) == 1
    assert first["proposal"]["command"]["title"] == "Weld NCR"


def test_the_same_key_from_another_agent_is_a_separate_proposal(
    env: McpHarness, tmp_path: Path
) -> None:
    mine = create(env, idempotency_key=KEY)
    other_server = build_server(env.factory, actor=OTHER_ACTOR, lake_dir=tmp_path / "lake")
    other = McpHarness(env.db, env.factory, other_server)
    theirs = other.structured(
        "create_record", scope=SCOPE, title="Weld NCR", key="P123-REC-0043", idempotency_key=KEY
    )
    assert theirs["proposal"]["agent"] == OTHER_ACTOR
    assert theirs["proposal"]["proposal_id"] != mine["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 2


def test_no_key_means_two_calls_two_proposals(env: McpHarness) -> None:
    first = create(env)
    second = create(env)
    assert first["proposal"]["proposal_id"] != second["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 2


def test_a_129_character_key_is_refused_before_anything_is_stored(env: McpHarness) -> None:
    too_long = "k" * 129
    with pytest.raises(ToolError) as refused:
        create(env, idempotency_key=too_long)
    assert too_long not in str(refused.value)
    assert proposal_events(env) == []


def test_a_key_with_a_space_is_refused_and_the_text_does_not_contain_it(env: McpHarness) -> None:
    spaced = "weld ncr 42"
    with pytest.raises(ToolError) as refused:
        create(env, idempotency_key=spaced)
    assert spaced not in str(refused.value)
    assert proposal_events(env) == []


def test_update_psets_with_a_key_replays_the_first_proposal(env: McpHarness) -> None:
    env.create_record("P123-REC-0001")
    args: dict[str, Any] = {
        "record": "P123-REC-0001",
        "scope": SCOPE,
        "pset": "valve_data",
        "values": {"size_in": 4},
        "idempotency_key": "psets-42",
    }
    first = env.structured("update_psets", **args)
    second = env.structured("update_psets", **args)
    assert first == second
    assert first["proposal"]["proposal_id"] == second["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 1


def test_the_key_is_optional_on_the_five_tools_and_absent_from_post_feed(env: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    proposing = (
        "create_record",
        "update_psets",
        "link_records",
        "transition_workflow",
        "propose_setting_change",
    )
    for name in proposing:
        schema = tools[name].input_schema
        assert "idempotency_key" in schema["properties"], name
        assert "idempotency_key" not in schema.get("required", []), name
    assert "idempotency_key" not in tools["post_feed"].input_schema["properties"]


@pytest.mark.parametrize("length", [129, 1000])
def test_an_over_long_key_is_refused_without_echoing_any_part_of_it(
    env: McpHarness, length: int
) -> None:
    prefix, suffix = "SECRETPREFIX-", "-SECRETSUFFIX"
    key = prefix + "x" * (length - len(prefix) - len(suffix)) + suffix
    assert len(key) == length
    with pytest.raises(ToolError) as caught:
        env.call("create_record", scope=SCOPE, title="Weld NCR", key="P123-REC-0042",
                 idempotency_key=key)  # fmt: skip
    assert "SECRETPREFIX" not in str(caught.value)
    assert "SECRETSUFFIX" not in str(caught.value)
    assert len(proposal_events(env)) == 0
