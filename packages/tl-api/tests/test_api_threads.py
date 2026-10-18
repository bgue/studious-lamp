"""Record threads over HTTP: read, post, preview and confirm a dispatch, and who sees what
(P1-I7 WS-B)."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from harness import ALICE, BOB, SCOPE, Harness
from test_stream import open_stream
from tl_api.tokens import add_token
from tl_core import settings
from tl_core.auth import accounts
from tl_core.threads.visibility import use_read_filter
from tl_core.uow import UnitOfWork

AGENT = "agent:triage"


def switch_on(h: Harness) -> None:
    with h.backend(False) as uow:
        for key, value in (("threads.enabled", True), ("threads.enabled_types", ["core.Record"])):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="t", reason="t"
            )


def make_account(h: Harness, name: str, kind: str = "person") -> None:
    """The command runner reads what an actor holds from its account."""
    with h.backend(False) as uow:
        accounts.create_account(
            uow,
            username=name,
            display_name=name,
            kind=kind,  # type: ignore[arg-type]
            roles=["user"],
            password=None,
            by="user:a",
        )


def post(client: TestClient, record_id: str, body: str) -> Any:
    return client.post(
        "/commands/PostThreadMessage", json={"scope": SCOPE, "record_id": record_id, "body": body}
    )


def agent_client(h: Harness) -> TestClient:
    client = TestClient(h.app, raise_server_exceptions=False)
    client.headers.update({"Authorization": f"Bearer {add_token(h.settings.tokens_path, AGENT)}"})
    return client


def test_a_message_is_posted_read_edited_and_retracted_over_http(harness: Harness) -> None:
    switch_on(harness)
    rid = harness.create_record("P123-REC-0001").stream_id
    made = post(harness.client, rid, "Flanges short @lchen")
    assert made.status_code == 200, made.text
    mid = made.json()["key"]
    assert made.json()["stream_id"] == f"thread:{rid}"
    page = harness.client.get(f"/records/{rid}/thread")
    assert page.status_code == 200
    body = page.json()
    assert body["enabled"] is True and body["message_count"] == 1
    assert body["messages"][0]["author"] == ALICE and body["messages"][0]["mentions"] == ["lchen"]
    edit = harness.client.post(
        "/commands/EditThreadMessage",
        json={"scope": SCOPE, "record_id": rid, "message_id": mid, "body": "Flanges short"},
    )
    assert edit.status_code == 200, edit.text
    other = harness.client_for(BOB).post(
        "/commands/RetractThreadMessage",
        json={"scope": SCOPE, "record_id": rid, "message_id": mid, "reason": "x"},
    )
    assert other.status_code == 403 and other.json()["error"] == "not_message_author"
    gone = harness.client.post(
        "/commands/RetractThreadMessage",
        json={"scope": SCOPE, "record_id": rid, "message_id": mid, "reason": "oops"},
    )
    assert gone.status_code == 200
    shown = harness.client.get(f"/records/{rid}/thread").json()["messages"][0]
    assert shown["retracted"] is True and shown["body"] == ""


def test_the_thread_of_a_record_that_is_not_there_is_the_record_404(harness: Harness) -> None:
    got = harness.client.get("/records/nope/thread")
    assert got.status_code == 404 and got.json()["error"] == "record_not_found"


def test_threads_off_refuses_a_post_with_403(harness: Harness) -> None:
    rid = harness.create_record("P123-REC-0001").stream_id
    refused = post(harness.client, rid, "hello")
    assert refused.status_code == 403 and refused.json()["error"] == "threads_disabled"
    assert harness.client.get(f"/records/{rid}/thread").json()["enabled"] is False


def test_a_slash_message_is_stored_not_dispatched(harness: Harness) -> None:
    switch_on(harness)
    rid = harness.create_record("P123-REC-0001").stream_id
    made = post(harness.client, rid, "/raise record Something")
    assert made.status_code == 200
    events = harness.client.get("/events").json()["events"]
    assert [e["event_type"] for e in events].count("Record.Created") == 1


def test_preview_then_dispatch_runs_what_was_previewed(harness: Harness) -> None:
    switch_on(harness)
    make_account(harness, "alice")
    rid = harness.create_record("P123-REC-0001").stream_id
    other = harness.create_record("P123-REC-0002").stream_id
    line = "/link P123-REC-0002 as requires"
    shown = harness.client.post(f"/records/{rid}/thread/preview", json={"text": line})
    assert shown.status_code == 200, shown.text
    preview = shown.json()["preview"]
    assert preview["can_dispatch"] is True and preview["planned"][0]["command_type"] == "AddLink"
    assert preview["planned"][0]["permitted"] is True
    done = harness.client.post(
        f"/records/{rid}/thread/dispatch",
        json={"text": line, "token": preview["token"], "expires_at": preview["expires_at"]},
    )
    assert done.status_code == 200, done.text
    events = harness.client.get("/events").json()["events"]
    link = next(e for e in events if e["event_type"] == "Link.Added")
    assert link["actor"] == ALICE and link["source"] == f"thread:{rid}"
    assert link["payload"]["to_ref"] == other
    assert link["correlation_id"].startswith("dispatch:")
    assert [e["event_type"] for e in events][-2:] == ["Link.Added", "Thread.Dispatched"]


def test_a_parse_problem_is_a_200_with_the_problem(harness: Harness) -> None:
    switch_on(harness)
    rid = harness.create_record("P123-REC-0001").stream_id
    bad = harness.client.post(f"/records/{rid}/thread/preview", json={"text": "/link"})
    assert bad.status_code == 200
    assert bad.json()["preview"] is None and bad.json()["problem"]["code"] == "missing_argument"


def test_a_stale_token_is_409_and_nothing_is_written(harness: Harness) -> None:
    switch_on(harness)
    rid = harness.create_record("P123-REC-0001").stream_id
    harness.create_record("P123-REC-0002")
    preview = harness.client.post(
        f"/records/{rid}/thread/preview", json={"text": "/link P123-REC-0002"}
    ).json()["preview"]
    before = len(harness.client.get("/events").json()["events"])
    stale = harness.client.post(
        f"/records/{rid}/thread/dispatch",
        json={"text": "/link P123-REC-0002 as requires", "token": preview["token"]},
    )
    assert stale.status_code == 409 and stale.json()["error"] == "dispatch_stale"
    assert len(harness.client.get("/events").json()["events"]) == before


def test_the_dispatch_body_takes_no_server_fields(harness: Harness) -> None:
    switch_on(harness)
    rid = harness.create_record("P123-REC-0001").stream_id
    token = "0" * 64
    for extra in (
        {"source": "thread:x"},
        {"correlation_id": "dispatch:x"},
        {"actor": "user:root"},
        {"roles": ["admin"]},
        {"holds": True},
        {"scope": "company"},
    ):
        refused = harness.client.post(
            f"/records/{rid}/thread/dispatch", json={"text": "/hold", "token": token, **extra}
        )
        assert refused.status_code == 422, extra


def test_an_agent_cannot_preview_or_dispatch_but_can_read_and_post(harness: Harness) -> None:
    switch_on(harness)
    rid = harness.create_record("P123-REC-0001").stream_id
    agent = agent_client(harness)
    for path, body in (
        ("preview", {"text": "/hold"}),
        ("dispatch", {"text": "/hold", "token": "0" * 64}),
    ):
        refused = agent.post(f"/records/{rid}/thread/{path}", json=body)
        assert refused.status_code == 403 and refused.json()["error"] == "agent_must_propose"
    assert agent.get(f"/records/{rid}/thread").status_code == 200
    posted = post(agent, rid, "found a leak")
    assert posted.status_code == 200, posted.text
    assert posted.json()["events"][0]["actor"] == AGENT


def test_a_person_without_the_roles_gets_403(harness: Harness) -> None:
    switch_on(harness)
    with harness.backend(False) as uow:
        settings.set_setting(
            uow,
            key="threads.dispatch.roles",
            layer="company",
            value=["admin"],
            actor="user:a",
            source="t",
            reason="t",
        )
    rid = harness.create_record("P123-REC-0001").stream_id
    refused = harness.client.post(f"/records/{rid}/thread/preview", json={"text": "/hold"})
    assert refused.status_code == 403 and refused.json()["error"] == "dispatch_forbidden"


# --- visibility is the record's: the events API and the stream (FANOUT D9, D17) ---------------


def hide(record_id: str) -> Any:
    def read_filter(uow: UnitOfWork, rid: str, actor: str) -> bool:
        return rid != record_id

    return use_read_filter(read_filter)


def thread_event_records(events: list[dict[str, Any]]) -> set[str]:
    return {e["payload"]["record_id"] for e in events if e["event_type"].startswith("Thread.")}


def test_a_filter_hides_the_thread_of_an_unreadable_record_everywhere(harness: Harness) -> None:
    switch_on(harness)
    secret = harness.create_record("P123-REC-0001").stream_id
    open_ = harness.create_record("P123-REC-0002").stream_id
    post(harness.client, secret, "private words")
    post(harness.client, open_, "public words")
    with hide(secret):
        events = harness.client.get("/events").json()["events"]
        assert thread_event_records(events) == {open_}
        assert harness.client.get(f"/records/{secret}/thread").status_code == 404
        assert harness.client.get(f"/records/{open_}/thread").status_code == 200
        assert post(harness.client, secret, "more").status_code == 404
        with harness.live() as server, open_stream(server, {"after": 0}) as stream:
            seen: list[str] = []
            while not seen:  # the replay: records, settings, then the open record's message
                message = stream.message()
                if message["event"].startswith("Thread."):
                    seen.append(json.loads(message["data"])["payload"]["record_id"])
            assert seen == [open_]
            post(harness.client_for(ALICE), secret, "live but hidden")
            post(harness.client_for(ALICE), open_, "live and shown")
            live = stream.message()  # the hidden one produced no message at all
            assert live["event"] == "Thread.MessagePosted"
            assert json.loads(live["data"])["payload"]["record_id"] == open_
    without = harness.client.get("/events").json()["events"]
    assert thread_event_records(without) == {secret, open_}  # no filter plugged: all readable


def test_an_agent_token_can_neither_preview_nor_confirm_a_dispatch(harness: Harness) -> None:
    switch_on(harness)
    make_account(harness, "triage", "agent")
    rid = harness.create_record("P123-REC-0001").stream_id
    harness.create_record("P123-REC-0002")
    agent = agent_client(harness)
    line = "/link P123-REC-0002"
    shown = harness.client.post(f"/records/{rid}/thread/preview", json={"text": line}).json()
    token = shown["preview"]["token"]
    for path, body in (
        ("preview", {"text": line}),
        ("dispatch", {"text": line, "token": token}),
    ):
        refused = agent.post(f"/records/{rid}/thread/{path}", json=body)
        assert refused.status_code == 403, (path, refused.text)
    events = harness.client.get("/events").json()["events"]
    assert not [e for e in events if e["event_type"] in ("Link.Added", "Thread.Dispatched")]


def test_a_person_accepts_an_agents_dispatch_proposal_over_http(harness: Harness) -> None:
    """The accept route passes the runner, so a proposed dispatch can be accepted at all."""
    from tl_api.thread_runner import thread_runner
    from tl_core.services import proposals
    from tl_core.threads.dispatch import build_dispatch_proposal

    switch_on(harness)
    make_account(harness, "alice")
    make_account(harness, "triage", "agent")
    rid = harness.create_record("P123-REC-0001").stream_id
    other = harness.create_record("P123-REC-0002").stream_id
    runner = thread_runner()
    command = build_dispatch_proposal(
        harness.backend,
        scope=SCOPE,
        record_id=rid,
        text="/link P123-REC-0002",
        agent=AGENT,
        runner=runner,
    )
    view = proposals.submit(
        harness.backend,
        tool="propose_dispatch",
        agent=AGENT,
        command=command,
        summary="link",
        runner=runner,
    )
    done = harness.client.post(f"/proposals/{view.proposal_id}/accept", json={})
    assert done.status_code == 200 and done.json()["status"] == "accepted", done.text
    events = harness.client.get("/events").json()["events"]
    link = next(e for e in events if e["event_type"] == "Link.Added")
    assert link["actor"] == ALICE and link["payload"]["to_ref"] == other
    assert link["source"] == f"thread:{rid}"
