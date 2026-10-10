"""The feed methods of ApiClient against EmbeddedClient on one SQLite ledger.

Reads must return equal data, commands sent remotely must have the effect the embedded handlers
have, and failures must raise the same exception class. Nothing is mocked.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest
from pydantic import TypeAdapter
from support import ACTOR, Pair
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import (
    InvalidScopeError,
    PostNotFoundError,
    PostRetractedError,
)
from tl_core.services.feed import EditPost, PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost
from tl_core.services.feed_queries import FeedPage

SCOPE = "project:P123"
PAGE: TypeAdapter[FeedPage] = TypeAdapter(FeedPage)


def common(**extra: Any) -> dict[str, Any]:
    return {"actor": ACTOR, "source": "tui", "scope": SCOPE, **extra}


def dump(page: FeedPage) -> Any:
    return PAGE.dump_python(page, mode="json")


def test_a_post_made_remotely_reads_back_the_same_through_both_clients(pair: Pair) -> None:
    record = pair.remote.create_record(
        CreateRecord(**common(record_type="core.Record", title="Spool", key="P123-REC-0001"))
    )
    posted = pair.remote.feed_post(
        PostToFeed(**common(body="Spool #P123-REC-0001 arrived #hold @party:acme"))
    )
    assert posted.events[0].event_type == "Feed.Posted"
    assert [e.event_type for e in posted.events[1:]] == ["Link.Suggested"]
    remote, embedded = pair.remote.feed_page(SCOPE), pair.embedded.feed_page(SCOPE)
    assert dump(remote) == dump(embedded)
    assert [i.id for i in remote.items if i.item_type == "post"] == [posted.stream_id]
    assert remote.suggestions[posted.stream_id][0].record_id == record.stream_id
    filters: list[dict[str, Any]] = [
        {"item_type": "post"},
        {"tag": "hold"},
        {"tag": "@party:acme"},
        {"record_id": record.stream_id},
        {"record_id": record.stream_id, "include_linked": True},
        {"limit": 1},
    ]
    for kwargs in filters:
        assert dump(pair.remote.feed_page(SCOPE, **kwargs)) == dump(
            pair.embedded.feed_page(SCOPE, **kwargs)
        ), kwargs


def test_paging_follows_next_before_the_same_way(pair: Pair) -> None:
    for n in range(5):
        pair.remote.feed_post(PostToFeed(**common(body=f"post {n}")))
    seen: list[str] = []
    before: int | None = None
    while True:
        page = pair.remote.feed_page(SCOPE, item_type="post", limit=2, before_seq=before)
        seen.extend(i.summary for i in page.items)
        before = page.next_before
        if before is None:
            break
    assert seen == [f"post {n}" for n in (4, 3, 2, 1, 0)]


def test_completion_equals_the_embedded_answer(pair: Pair) -> None:
    pair.remote.create_record(
        CreateRecord(**common(record_type="core.Record", title="Spool", key="P123-REC-0001"))
    )
    pair.remote.feed_post(PostToFeed(**common(body="see #hold and #area:A12 @party:acme")))
    cases: list[tuple[Literal["#", "@"], str]] = [
        ("#", ""),
        ("#", "h"),
        ("#", "ar"),
        ("@", ""),
        ("@", "p"),
    ]
    for sigil, prefix in cases:
        remote = pair.remote.feed_complete(SCOPE, sigil, prefix)
        assert remote == pair.embedded.feed_complete(SCOPE, sigil, prefix), (sigil, prefix)
    assert len(pair.remote.feed_complete(SCOPE, "#", "", limit=2)) == 2


def test_edit_react_and_retract_have_the_embedded_effect(pair: Pair) -> None:
    for client in (pair.embedded, pair.remote):
        post = client.feed_post(PostToFeed(**common(body="first")))
        assert (
            client.feed_edit(EditPost(**common(post_id=post.stream_id, body="second"))).version == 2
        )
        reacted = client.feed_react(ReactToPost(**common(post_id=post.stream_id, reaction="ack")))
        assert reacted.events[0].event_type == "Feed.Reacted"
        retracted = client.feed_retract(
            RetractPost(**common(post_id=post.stream_id, reason="oops"))
        )
        assert retracted.events[0].event_type == "Feed.Retracted"
        item = next(i for i in client.feed_page(SCOPE).items if i.id == post.stream_id)
        assert item.retracted and item.summary == "[retracted]"


def test_failures_raise_the_same_exception_classes(pair: Pair) -> None:
    for client in (pair.embedded, pair.remote):
        with pytest.raises(PostNotFoundError):
            client.feed_edit(EditPost(**common(post_id="01NOSUCHPOST", body="x")))
        with pytest.raises(InvalidScopeError):
            client.feed_post(PostToFeed(**{**common(body="x"), "scope": "company"}))
        post = client.feed_post(PostToFeed(**common(body="gone")))
        client.feed_retract(RetractPost(**common(post_id=post.stream_id, reason="r")))
        with pytest.raises(PostRetractedError):
            client.feed_edit(EditPost(**common(post_id=post.stream_id, body="again")))
