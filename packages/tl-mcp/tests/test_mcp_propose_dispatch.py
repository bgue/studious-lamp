"""propose_dispatch: an agent proposes a slash command; a person's acceptance runs it (ADR-0018)."""

from __future__ import annotations

from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from tl_api.thread_runner import thread_runner
from tl_core import settings
from tl_core.proposals.types import ProposalView
from tl_core.services import proposals
from tl_core.services.commands import UpdateRecord
from tl_core.services.records import handle_update_record

ALICE = "user:alice"


def switch_on(env: McpHarness) -> None:
    with env.factory(False) as uow:
        for key, value in (("threads.enabled", True), ("threads.enabled_types", ["core.Record"])):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="test"
            )


def events(env: McpHarness, event_type: str) -> list[Any]:
    with env.factory(True) as uow:
        return [e for e in uow.ledger.read_after(0, limit=1000) if e.event_type == event_type]


def accept(env: McpHarness, proposal_id: str) -> ProposalView:
    return proposals.accept_or_fail(
        env.factory,
        proposal_id=proposal_id,
        by=ALICE,
        holds=lambda level: level == "user",
        runner=thread_runner(),
    )


def test_the_proposal_is_pending_and_nothing_ran(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    other = env.create_record("P123-REC-0002").stream_id
    out = env.structured(
        "propose_dispatch", record="P123-REC-0001", scope=SCOPE, text="/link P123-REC-0002"
    )
    proposal = out["proposal"]
    assert (proposal["status"], proposal["tool"], proposal["agent"]) == (
        "pending",
        "propose_dispatch",
        ACTOR,
    )
    assert proposal["command_type"] == "DispatchFromThread"
    assert (
        proposal["command"]["record_id"] == rid
        and proposal["command"]["text"] == "/link P123-REC-0002"
    )
    assert len(proposal["command"]["token"]) == 64
    assert "Nothing has changed yet" in out["message"]
    assert events(env, "Thread.MessagePosted") == [] and events(env, "Link.Added") == []
    assert other


def test_a_person_accepting_runs_the_dispatch_as_the_person_on_the_agents_suggestion(
    env: McpHarness,
) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    other = env.create_record("P123-REC-0002").stream_id
    out = env.structured("propose_dispatch", record=rid, text="/link P123-REC-0002")
    done = accept(env, out["proposal"]["proposal_id"])
    assert done.status == "accepted"
    (link,) = events(env, "Link.Added")
    assert (link.actor, link.source) == (ALICE, f"thread:{rid}")
    assert (link.payload["from_ref"], link.payload["to_ref"]) == (rid, other)
    (message,) = events(env, "Thread.MessagePosted")
    assert (message.actor, message.payload["kind"]) == (ALICE, "dispatch")
    (dispatched,) = events(env, "Thread.Dispatched")
    assert dispatched.payload["verb"] == "link"


def test_a_record_that_changed_since_fails_the_proposal(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    env.create_record("P123-REC-0002")
    out = env.structured("propose_dispatch", record=rid, text="/link P123-REC-0002")
    with env.factory(False) as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor="u",
                source="t",
                scope=SCOPE,
                stream_id=rid,
                expected_version=1,
                changes={"title": "changed"},
            ),
        )
    done = accept(env, out["proposal"]["proposal_id"])
    assert done.status == "failed" and "DispatchStaleError" in (done.reason or "")
    assert events(env, "Link.Added") == []


def test_a_plan_with_problems_or_a_plain_message_is_refused_at_once(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    for text, why in (
        ("/link NOPE-1", "no record .NOPE-1."),
        ("/assign @x W1", "not available"),
        ("hello", "plain message"),
        ("/link", "needs at least one"),
    ):
        with pytest.raises(ToolError, match=why):
            env.call("propose_dispatch", record=rid, text=text)
    assert [e for e in events(env, "Proposal.Created")] == []


def test_the_setting_none_refuses_the_tool_and_threads_off_refuses_it_too(env: McpHarness) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    env.create_record("P123-REC-0002")
    with pytest.raises(ToolError, match="threads are not switched on"):
        env.call("propose_dispatch", record=rid, text="/link P123-REC-0002")
    switch_on(env)
    with env.factory(False) as uow:
        settings.set_setting(
            uow,
            key="threads.agents.can_dispatch",
            layer="company",
            value="none",
            actor="user:a",
            source="test",
        )
    with pytest.raises(ToolError, match="agents may not propose"):
        env.call("propose_dispatch", record=rid, text="/link P123-REC-0002")


def test_a_person_without_the_roles_cannot_accept(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    env.create_record("P123-REC-0002")
    out = env.structured("propose_dispatch", record=rid, text="/link P123-REC-0002")
    with env.factory(False) as uow:
        settings.set_setting(
            uow,
            key="threads.dispatch.roles",
            layer="company",
            value=["admin"],
            actor="user:a",
            source="test",
        )
    done = accept(env, out["proposal"]["proposal_id"])
    assert done.status == "failed" and "DispatchForbiddenError" in (done.reason or "")
