"""The feed half of `FakeClient` (P0-I6-S6). Provided; do not edit."""

from __future__ import annotations

import pytest
from fakes import SCOPE, FakeClient
from tl_core.feed.types import Reaction
from tl_core.services.errors import (
    InvalidScopeError,
    NoChangesError,
    PostNotFoundError,
    PostRetractedError,
)
from tl_core.services.feed import EditPost, PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost


def post(client: FakeClient, body: str, actor: str = "user:mlee") -> str:
    cmd = PostToFeed(actor=actor, source="tui", scope=SCOPE, body=body)
    return client.feed_post(cmd).stream_id


def react(
    client: FakeClient, post_id: str, reaction: Reaction, actor: str, on: bool = True
) -> None:
    cmd = ReactToPost(
        actor=actor, source="tui", scope=SCOPE, post_id=post_id, reaction=reaction, on=on
    )
    client.feed_react(cmd)


@pytest.fixture
def client() -> FakeClient:
    return FakeClient.with_valve_example()


def test_a_post_resolves_record_tags_and_raises_importance_for_signal_tags(
    client: FakeClient,
) -> None:
    valve = client.get_record(SCOPE, "FV-1001")
    assert valve is not None
    pid = post(client, "Bevels damaged #FV-1001 #hold @party:fab-a")
    (item,) = client.feed_page(SCOPE).items
    assert item.id == pid and item.item_type == "post"
    assert item.record_ids == (valve["id"],)
    assert [(t.kind, t.text) for t in item.tags] == [
        ("record", "FV-1001"),
        ("signal", "hold"),
        ("mention", "party:fab-a"),
    ]
    assert item.importance == "high"


def test_a_company_scope_post_is_refused(client: FakeClient) -> None:
    with pytest.raises(InvalidScopeError):
        client.feed_post(PostToFeed(actor="user:a", source="tui", scope="company", body="x"))


def test_the_page_is_newest_first_and_pages_by_before_seq(client: FakeClient) -> None:
    ids = [post(client, f"post {i}") for i in range(5)]
    first = client.feed_page(SCOPE, limit=2)
    assert [i.id for i in first.items] == [ids[4], ids[3]]
    assert first.next_before == first.items[-1].seq
    second = client.feed_page(SCOPE, limit=2, before_seq=first.next_before)
    assert [i.id for i in second.items] == [ids[2], ids[1]]
    last = client.feed_page(SCOPE, limit=2, before_seq=second.next_before)
    assert [i.id for i in last.items] == [ids[0]] and last.next_before is None


def test_filters_by_type_tag_and_record(client: FakeClient) -> None:
    valve = client.get_record(SCOPE, "FV-1001")
    assert valve is not None
    card = client.seed_card("jsmith recorded 14 welds", record_ids=(valve["id"],))
    held = post(client, "stop #hold #FV-1001")
    post(client, "plain note #bevel")
    mention = post(client, "ping @party:fab-a")
    assert [i.id for i in client.feed_page(SCOPE, item_type="card").items] == [card.id]
    assert [i.id for i in client.feed_page(SCOPE, tag="hold").items] == [held]
    assert [i.id for i in client.feed_page(SCOPE, tag="#HOLD").items] == [held]
    assert [i.id for i in client.feed_page(SCOPE, tag="@party:fab-a").items] == [mention]
    assert client.feed_page(SCOPE, tag="party:fab-a").items == []
    assert {i.id for i in client.feed_page(SCOPE, record_id=valve["id"]).items} == {card.id, held}


def test_a_record_feed_can_include_linked_records(client: FakeClient) -> None:
    a, b = client.get_record(SCOPE, "FV-1001"), client.get_record(SCOPE, "FV-1002")
    assert a is not None and b is not None
    client.seed_link("FV-1001", "FV-1002", "references", status="active")
    on_b = post(client, "about #FV-1002")
    assert client.feed_page(SCOPE, record_id=a["id"]).items == []
    page = client.feed_page(SCOPE, record_id=a["id"], include_linked=True)
    assert [i.id for i in page.items] == [on_b]


def test_labels_and_hold_suggestions(client: FakeClient) -> None:
    valve = client.get_record(SCOPE, "FV-1001")
    assert valve is not None
    held = post(client, "stop #hold #FV-1001")
    post(client, "no record #hold")
    page = client.feed_page(SCOPE)
    assert page.labels == {valve["id"]: "FV-1001"}
    assert list(page.suggestions) == [held]
    (suggestion,) = page.suggestions[held]
    assert (suggestion.kind, suggestion.record_id, suggestion.record_key) == (
        "constraint",
        valve["id"],
        "FV-1001",
    )
    assert suggestion.prompt == "Create a constraint on FV-1001?"


def test_edit_replaces_body_and_tags(client: FakeClient) -> None:
    pid = post(client, "draft #bevel")
    cmd = EditPost(actor="user:mlee", source="tui", scope=SCOPE, post_id=pid, body="final #hold")
    client.feed_edit(cmd)
    (item,) = client.feed_page(SCOPE).items
    assert item.summary == "final #hold" and item.importance == "high"
    with pytest.raises(NoChangesError):
        client.feed_edit(cmd)


def test_retract_leaves_a_tombstone_and_blocks_further_changes(client: FakeClient) -> None:
    pid = post(client, "oops #FV-1001 #hold")
    client.feed_retract(
        RetractPost(actor="user:mlee", source="tui", scope=SCOPE, post_id=pid, reason="x")
    )
    (item,) = client.feed_page(SCOPE).items
    assert item.retracted and item.summary == "[retracted]"
    assert [t.kind for t in item.tags] == ["record"]
    assert client.feed_page(SCOPE).suggestions == {}
    with pytest.raises(PostRetractedError):
        react(client, pid, "ack", "user:b")
    with pytest.raises(PostNotFoundError):
        client.feed_retract(
            RetractPost(actor="u", source="t", scope=SCOPE, post_id="nope", reason="x")
        )


def test_reactions_count_actors_and_refuse_no_ops(client: FakeClient) -> None:
    pid = post(client, "hello")
    react(client, pid, "ack", "user:a")
    react(client, pid, "ack", "user:b")
    react(client, pid, "+1", "user:a")
    assert client.feed_page(SCOPE).items[0].reactions == {"ack": 2, "+1": 1}
    with pytest.raises(NoChangesError):
        react(client, pid, "ack", "user:a")
    react(client, pid, "ack", "user:a", on=False)
    assert client.feed_page(SCOPE).items[0].reactions == {"ack": 1, "+1": 1}


def test_completion(client: FakeClient) -> None:
    post(client, "x #bevel-damage #area:A12 @party:fab-a", actor="user:mlee")
    post(client, "y", actor="agent:triage")
    texts = lambda sigil, prefix: [  # noqa: E731
        (c.text, c.kind)
        for c in client.feed_complete(SCOPE, sigil, prefix)  # type: ignore[arg-type]
    ]
    assert texts("#", "FV-100") == [
        ("FV-1001", "record"),
        ("FV-1002", "record"),
        ("FV-1003", "record"),
    ]
    assert texts("#", "ho") == [("hold", "signal")]
    assert texts("#", "be") == [("bevel-damage", "topic")]
    assert texts("#", "ar") == [("area:a12", "code")]
    assert texts("@", "pa") == [("party:fab-a", "mention")]
    assert texts("@", "") == [
        ("party:fab-a", "mention"),
        ("agent:triage", "mention"),
        ("mlee", "mention"),
    ]
    assert len(client.feed_complete(SCOPE, "#", "", limit=3)) == 3
