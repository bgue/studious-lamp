"""The write tools: propose-only record changes, a direct labelled post, bounds and the hook."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from mcp_types import CallToolResult
from sqlalchemy import text
from tl_api.auth import Forbidden
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_mcp.main import main
from tl_mcp.modes import HUMAN_GATE_MESSAGE, ToolModeError, resolve_tool_modes
from tl_mcp.server import build_server
from tl_mcp.write_tools import MAX_JSON_CHARS

ALICE = "user:alice"
PROPOSING = ("create_record", "update_psets", "link_records", "transition_workflow")


def events(env: McpHarness, event_type: str | None = None) -> list[Any]:
    with env.factory(True) as uow:
        found = uow.ledger.read_after(0, limit=1000)
    return [e for e in found if event_type is None or e.event_type == event_type]


def accept(env: McpHarness, proposal_id: str) -> ProposalView:
    return proposals.accept_or_fail(env.factory, proposal_id=proposal_id, by=ALICE)


def propose_create(env: McpHarness, key: str = "P123-REC-0042", **extra: Any) -> dict[str, Any]:
    out = env.structured("create_record", scope=SCOPE, title="Weld NCR", key=key, **extra)
    assert isinstance(out, dict)
    return out


# --- proposing ---------------------------------------------------------------------------------


def test_create_record_files_a_pending_proposal_and_creates_nothing(env: McpHarness) -> None:
    out = propose_create(env, summary="Create the weld NCR")
    proposal = out["proposal"]
    assert (proposal["status"], proposal["tool"], proposal["agent"]) == (
        "pending",
        "create_record",
        ACTOR,
    )
    assert proposal["summary"] == "Create the weld NCR" and proposal["scope"] == SCOPE
    assert "Nothing has changed yet" in out["message"]
    assert [e.event_type for e in events(env)] == ["Proposal.Created"]
    (created,) = events(env)
    assert (created.actor, created.source) == (ACTOR, "mcp:triage")


def test_a_person_accepting_creates_the_record_with_the_agent_as_source(env: McpHarness) -> None:
    proposal = propose_create(env, description="Found at weld W-12")["proposal"]
    accepted = accept(env, proposal["proposal_id"])
    assert accepted.status == "accepted"
    (record,) = [e for e in events(env) if e.event_type == "Record.Created"]
    assert (record.actor, record.source) == (ALICE, "mcp:triage")
    assert record.payload["title"] == "Weld NCR" and record.payload["key"] == "P123-REC-0042"
    assert record.causation_id == events(env, "Proposal.Created")[0].event_id


def test_update_psets_proposes_with_the_current_version_unless_one_is_given(
    env: McpHarness,
) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    out = env.structured(
        "update_psets",
        record="P123-REC-0001",
        scope=SCOPE,
        pset="valve_data",
        values={"size_in": 4},
    )
    command = out["proposal"]["command"]
    assert (command["stream_id"], command["expected_version"]) == (rid, 1)
    assert command["layer"] == "standard" and command["values"] == {"size_in": 4}
    assert (
        "valve_data" in out["proposal"]["summary"] and "P123-REC-0001" in out["proposal"]["summary"]
    )
    assert accept(env, out["proposal"]["proposal_id"]).status == "accepted"


def test_update_psets_with_a_stale_expected_version_is_refused_now(env: McpHarness) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    first = env.structured("update_psets", record=rid, pset="valve_data", values={"size_in": 4})[
        "proposal"
    ]
    accept(env, first["proposal_id"])
    with pytest.raises(ToolError, match="version"):
        env.call(
            "update_psets",
            record=rid,
            pset="valve_data",
            values={"size_in": 6},
            expected_version=1,
        )


def test_link_records_resolves_keys_and_proposes_an_add_link(env: McpHarness) -> None:
    a = env.create_record("P123-REC-0001").stream_id
    b = env.create_record("P123-REC-0002").stream_id
    out = env.structured(
        "link_records",
        from_record="P123-REC-0001",
        to_record="P123-REC-0002",
        scope=SCOPE,
        relation="requires",
    )
    command = out["proposal"]["command"]
    assert (command["from_id"], command["to_id"], command["relation"]) == (a, b, "requires")
    assert not events(env, "Link.Added")
    assert accept(env, out["proposal"]["proposal_id"]).status == "accepted"
    (added,) = events(env, "Link.Added")
    assert (added.actor, added.source) == (ALICE, "mcp:triage")


def test_transition_workflow_proposes_and_a_person_accepts(env: McpHarness) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    out = env.structured("transition_workflow", record=rid, transition="submit")
    assert out["proposal"]["command"]["transition"] == "submit"
    assert out["proposal"]["command"]["actor_roles"] == []
    assert accept(env, out["proposal"]["proposal_id"]).status == "accepted"
    (moved,) = events(env, "Workflow.Transitioned")
    assert (moved.actor, moved.source) == (ALICE, "mcp:triage")


def test_the_handlers_own_refusals_come_back_to_the_agent(env: McpHarness) -> None:
    env.create_record("P123-REC-0001")
    cases: list[tuple[str, dict[str, Any], str]] = [
        ("create_record", {"scope": SCOPE, "title": "x", "key": "P123-REC-0001"}, "already used"),
        ("create_record", {"scope": "company", "title": "x", "record_type": "no.Such"}, "record"),
        ("update_psets", {"record": "01NOSUCH", "pset": "p", "values": {"a": 1}}, "no record"),
        (
            "update_psets",
            {"record": "P123-REC-0001", "scope": SCOPE, "pset": "no_such_pset", "values": {"a": 1}},
            "no_such_pset",
        ),
        (
            "link_records",
            {"from_record": "P123-REC-0001", "to_record": "P123-REC-9999", "scope": SCOPE},
            "no record",
        ),
        (
            "transition_workflow",
            {"record": "P123-REC-0001", "scope": SCOPE, "transition": "fly"},
            "fly",
        ),
    ]
    for tool, args, expect in cases:
        with pytest.raises(ToolError, match=expect):
            env.call(tool, **args)
    assert events(env, "Proposal.Created") == []  # none was recorded


def test_a_key_needs_its_scope(env: McpHarness) -> None:
    env.create_record("P123-REC-0001")
    with pytest.raises(ToolError, match="give `scope`"):
        env.call("update_psets", record="P123-REC-0001", pset="valve_data", values={"a": 1})


def test_the_daily_budget_stops_an_agent_and_says_so(
    env: McpHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(proposals.BUDGET_ENV, "2")
    propose_create(env, "P123-REC-0001")
    propose_create(env, "P123-REC-0002")
    with pytest.raises(ToolError, match=r"agent:triage has used its 2 proposals"):
        propose_create(env, "P123-REC-0003")
    assert len(events(env, "Proposal.Created")) == 2
    # a person deciding does not give the budget back: it counts proposals made today
    accept(env, events(env, "Proposal.Created")[0].stream_id)
    with pytest.raises(ToolError, match="proposals"):
        propose_create(env, "P123-REC-0004")


# --- post_feed ---------------------------------------------------------------------------------


def test_post_feed_writes_directly_labelled_with_the_agent(env: McpHarness) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    out = env.structured("post_feed", scope=SCOPE, body="Spool #P123-REC-0001 looks wrong #hold")
    assert (out["author"], out["scope"], out["suggested_links"]) == (ACTOR, SCOPE, 1)
    (posted,) = events(env, "Feed.Posted")
    assert (posted.actor, posted.source, posted.stream_id) == (ACTOR, "mcp:triage", out["post_id"])
    assert posted.payload["author"] == ACTOR and posted.payload["record_ids"] == [rid]
    (suggested,) = events(env, "Link.Suggested")
    assert (suggested.actor, suggested.source) == (ACTOR, "mcp:triage")
    with env.factory(True) as uow:
        row = (
            uow.conn()
            .execute(
                text("SELECT actor, importance FROM cur_feed_items WHERE item_id = :i"),
                {"i": out["post_id"]},
            )
            .one()
        )
    assert (row.actor, row.importance) == (ACTOR, "high")  # `#hold` is a signal tag
    with env.factory(True) as uow:  # a record tag only suggests: the record has no live link
        count = (
            uow.conn()
            .execute(text("SELECT COUNT(*) FROM cur_links WHERE status = 'active'"))
            .scalar_one()
        )
    assert count == 0
    assert events(env, "Proposal.Created") == []  # a post is not proposed


def test_post_feed_needs_a_project(env: McpHarness) -> None:
    with pytest.raises(ToolError, match="project"):
        env.call("post_feed", scope="company", body="hello")
    with pytest.raises(ToolError):
        env.call("post_feed", scope=SCOPE, body="x", importance="urgent")


# --- identity, hook and bounds ----------------------------------------------------------------


def test_every_write_tool_calls_the_hook_before_writing_anything(tmp_path: Path) -> None:
    seen: list[tuple[str, str, str]] = []

    def deny(actor: str, action: str, resource: str) -> None:
        seen.append((actor, action, resource))
        raise Forbidden("nobody may")

    env = McpHarness.build(tmp_path, authorize_hook=deny)
    try:
        env.create_record("P123-REC-0001")
        head = len(events(env))
        calls: dict[str, dict[str, Any]] = {
            "create_record": {"scope": SCOPE, "title": "t"},
            "update_psets": {
                "record": "P123-REC-0001",
                "scope": SCOPE,
                "pset": "p",
                "values": {"a": 1},
            },
            "link_records": {
                "from_record": "P123-REC-0001",
                "to_record": "P123-REC-0001",
                "scope": SCOPE,
            },
            "transition_workflow": {
                "record": "P123-REC-0001",
                "scope": SCOPE,
                "transition": "submit",
            },
            "post_feed": {"scope": SCOPE, "body": "hello"},
        }
        for tool, args in calls.items():
            with pytest.raises(ToolError, match="not allowed: nobody may"):
                env.call(tool, **args)
        assert len(events(env)) == head
    finally:
        env.close()
    assert [a for _, a, _ in seen] == [f"mcp.{t}" for t in calls]
    assert {actor for actor, _, _ in seen} == {ACTOR}


def test_oversized_input_is_refused_before_the_hook_runs(tmp_path: Path) -> None:
    seen: list[str] = []

    def record_and_deny(actor: str, action: str, resource: str) -> None:
        seen.append(action)
        raise Forbidden("stop here")

    env = McpHarness.build(tmp_path, authorize_hook=record_and_deny)
    try:
        big = "x" * 129
        too_big: list[tuple[str, dict[str, Any]]] = [
            ("create_record", {"scope": big, "title": "t"}),
            ("create_record", {"scope": SCOPE, "title": "t" * 501}),
            ("create_record", {"scope": SCOPE, "title": ""}),
            ("create_record", {"scope": SCOPE, "title": "t", "description": "d" * 10_001}),
            ("create_record", {"scope": SCOPE, "title": "t", "key": big}),
            ("create_record", {"scope": SCOPE, "title": "t", "record_type": big}),
            ("create_record", {"scope": SCOPE, "title": "t", "summary": "s" * 301}),
            ("create_record", {"scope": SCOPE, "title": "t", "numbering": {big: "v"}}),
            ("create_record", {"scope": SCOPE, "title": "t", "numbering": {"k": big}}),
            (
                "create_record",
                {"scope": SCOPE, "title": "t", "numbering": {str(n): "v" for n in range(21)}},
            ),
            ("update_psets", {"record": big, "pset": "p", "values": {"a": 1}}),
            ("update_psets", {"record": "r", "pset": big, "values": {"a": 1}}),
            ("update_psets", {"record": "r", "pset": "p", "values": {}}),
            ("update_psets", {"record": "r", "pset": "p", "values": {"a": 1}, "layer": "x"}),
            (
                "update_psets",
                {"record": "r", "pset": "p", "values": {"a": 1}, "expected_version": 0},
            ),
            ("link_records", {"from_record": big, "to_record": "b"}),
            ("link_records", {"from_record": "a", "to_record": big}),
            ("link_records", {"from_record": "a", "to_record": "b", "relation": big}),
            ("link_records", {"from_record": "a", "to_record": "b", "note": "n" * 1001}),
            ("transition_workflow", {"record": "r", "transition": big}),
            ("transition_workflow", {"record": "r", "transition": "t", "reason": "r" * 1001}),
            ("post_feed", {"scope": SCOPE, "body": ""}),
            ("post_feed", {"scope": SCOPE, "body": "b" * 10_001}),
            ("post_feed", {"scope": big, "body": "b"}),
        ]
        for tool, args in too_big:
            with pytest.raises(ToolError):
                env.call(tool, **args)
        assert seen == []  # the schema stopped every one of them
        for tool, args in (
            ("create_record", {"scope": "s" * 128, "title": "t" * 500, "key": "k" * 128}),
            ("post_feed", {"scope": SCOPE, "body": "b" * 10_000}),
        ):
            with pytest.raises(ToolError, match="not allowed"):
                env.call(tool, **args)
        assert seen == ["mcp.create_record", "mcp.post_feed"]
    finally:
        env.close()


def test_json_values_are_bounded_as_text(env: McpHarness) -> None:
    huge = {"a": "x" * MAX_JSON_CHARS}
    with pytest.raises(ToolError, match="longer than"):
        env.call("create_record", scope=SCOPE, title="t", psets={"valve_data": huge})
    with pytest.raises(ToolError, match="longer than"):
        env.call("update_psets", record="r", pset="p", values=huge)
    assert events(env) == []


def test_every_string_the_tools_accept_has_a_length_limit(env: McpHarness) -> None:
    def strings(node: Any, path: str) -> list[str]:
        """Paths of string schemas without a maxLength, anywhere under ``node``."""
        found: list[str] = []
        if isinstance(node, dict):
            if node.get("type") == "string" and "maxLength" not in node and "enum" not in node:
                found.append(path)
            for key, value in node.items():
                found.extend(strings(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found.extend(strings(value, f"{path}[{index}]"))
        return found

    unbounded: list[str] = []
    for tool in asyncio.run(env.server.list_tools()):
        unbounded += strings(tool.input_schema, tool.name)
    # the only unbounded strings are the free-form JSON values, which check_json bounds as text
    assert unbounded == []


def test_a_user_actor_server_also_proposes_and_tags_its_source(tmp_path: Path) -> None:
    env = McpHarness.build(tmp_path)
    try:
        server = build_server(env.factory, actor="user:carol")
        result = asyncio.run(
            server.call_tool(
                "create_record", {"scope": SCOPE, "title": "t", "key": "P123-REC-0001"}
            )
        )
        assert isinstance(result, CallToolResult) and result.structured_content is not None
        assert result.structured_content["proposal"]["agent"] == "user:carol"
        (created,) = events(env, "Proposal.Created")
        assert created.source == "mcp:carol"
    finally:
        env.close()


# --- modes -------------------------------------------------------------------------------------


def test_write_mode_is_refused_with_the_human_gate_message(env: McpHarness) -> None:
    assert resolve_tool_modes({"create_record": "propose"}) == {t: "propose" for t in PROPOSING}
    for tool in PROPOSING:
        with pytest.raises(ToolModeError, match="human gate") as refused:
            build_server(env.factory, actor=ACTOR, tool_modes={tool: "write"})
        assert str(refused.value) == HUMAN_GATE_MESSAGE
    with pytest.raises(ToolModeError, match="unknown tool mode"):
        resolve_tool_modes({"create_record": "auto"})
    with pytest.raises(ToolModeError, match="not a record-changing tool"):
        resolve_tool_modes({"search_records": "propose"})
    with pytest.raises(ToolModeError, match="no mode"):
        resolve_tool_modes({"post_feed": "write"})


def test_the_entry_point_refuses_write_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "tl.db"
    McpHarness.build(tmp_path).close()
    code = main(["--actor", ACTOR, "--db", str(db), "--tool-mode", "create_record=write"])
    assert code == 2
    assert "human gate" in capsys.readouterr().err
