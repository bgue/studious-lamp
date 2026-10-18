"""read_thread and post_thread_message: the thread of a record, read and posted to by an agent.

Provided; do not edit.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from tl_core import settings
from tl_core.threads.contract import READ_THREAD_MAX_PAGE
from tl_core.threads.messages import PostThreadMessage, handle_post_thread_message

PERSON = "user:rgarcia"


def switch_on(env: McpHarness) -> None:
    with env.factory(False) as uow:
        for key, value in (("threads.enabled", True), ("threads.enabled_types", ["core.Record"])):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="test"
            )


def person_posts(env: McpHarness, record_id: str, body: str) -> None:
    command = PostThreadMessage(
        actor=PERSON, source="test", scope=SCOPE, record_id=record_id, body=body
    )
    with env.factory(False) as uow:
        handle_post_thread_message(uow, command)


def events(env: McpHarness, event_type: str) -> list[Any]:
    with env.factory(True) as uow:
        return [e for e in uow.ledger.read_after(0, limit=1000) if e.event_type == event_type]


def test_read_thread_returns_the_messages_oldest_first_by_id_or_by_key(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    person_posts(env, rid, "Flanges short for W019 @lchen")
    person_posts(env, rid, "On it")
    for arguments in ({"record": rid}, {"record": "P123-REC-0001", "scope": SCOPE}):
        page = env.structured("read_thread", **arguments)
        assert page["enabled"] is True and page["message_count"] == 2
        assert [m["body"] for m in page["messages"]] == ["Flanges short for W019 @lchen", "On it"]
        assert page["messages"][0]["mentions"] == ["lchen"] and page["next_before"] is None
        assert {p["actor"] for p in page["participants"]} >= {PERSON, "user:seed", "user:lchen"}


def test_read_thread_pages_back_with_next_before(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    for n in range(5):
        person_posts(env, rid, f"m{n}")
    newest = env.structured("read_thread", record=rid, limit=2)
    assert [m["body"] for m in newest["messages"]] == ["m3", "m4"]
    older = env.structured("read_thread", record=rid, limit=2, before_seq=newest["next_before"])
    assert [m["body"] for m in older["messages"]] == ["m1", "m2"]


def test_read_thread_of_a_record_with_no_thread_is_empty_and_says_if_threads_are_on(
    env: McpHarness,
) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    off = env.structured("read_thread", record=rid)
    assert off["enabled"] is False and off["messages"] == []
    switch_on(env)
    assert env.structured("read_thread", record=rid)["enabled"] is True


def test_read_thread_of_a_record_that_is_not_there_is_the_record_error(env: McpHarness) -> None:
    with pytest.raises(ToolError, match="no record"):
        env.call("read_thread", record="nope")
    with pytest.raises(ToolError, match="give `scope`"):
        env.call("read_thread", record="P123-REC-0001")


def test_read_thread_bounds_its_inputs(env: McpHarness) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    for bad in (
        {"record": rid, "limit": 0},
        {"record": rid, "limit": READ_THREAD_MAX_PAGE + 1},
        {"record": rid, "before_seq": -1},
        {"record": ""},
        {"record": "r" * 400},
    ):
        with pytest.raises(ToolError):
            env.call("read_thread", **bad)


def test_post_thread_message_writes_directly_labelled_with_the_agent(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    other = env.create_record("P123-REC-0002").stream_id
    out = env.structured(
        "post_thread_message",
        record="P123-REC-0001",
        scope=SCOPE,
        body="Check #P123-REC-0002 @kpatel",
    )
    assert out["record_id"] == rid and out["author"] == ACTOR and out["message_id"]
    assert out["mentions"] == ["kpatel"] and out["record_refs"] == [other]
    (posted,) = events(env, "Thread.MessagePosted")
    assert (posted.actor, posted.source, posted.stream_id) == (ACTOR, "mcp:triage", f"thread:{rid}")
    page = env.structured("read_thread", record=rid)
    assert page["messages"][0]["author"] == ACTOR and page["messages"][0]["body"].startswith(
        "Check"
    )


def test_a_slash_message_from_an_agent_is_only_a_message(env: McpHarness) -> None:
    switch_on(env)
    rid = env.create_record("P123-REC-0001").stream_id
    env.structured("post_thread_message", record=rid, body="/raise record Something")
    assert [e.event_type for e in events(env, "Record.Created")] == ["Record.Created"]
    assert len(events(env, "Thread.Dispatched")) == 0
    assert env.structured("read_thread", record=rid)["messages"][0]["dispatch"] is None


def test_post_thread_message_refuses_when_threads_are_off_and_for_bad_input(
    env: McpHarness,
) -> None:
    rid = env.create_record("P123-REC-0001").stream_id
    with pytest.raises(ToolError, match="threads are not switched on"):
        env.call("post_thread_message", record=rid, body="hello")
    switch_on(env)
    for bad in ("", "   ", "b" * 10_001, "bell\x07"):
        with pytest.raises(ToolError):
            env.call("post_thread_message", record=rid, body=bad)
    with pytest.raises(ToolError, match="no record"):
        env.call("post_thread_message", record="nope", body="x")
    assert events(env, "Thread.MessagePosted") == []
