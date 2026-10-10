"""EmbeddedClient and the feed pane over the real feed services on a temporary ledger (P0-I6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from tl_adapters.sqlite.uow import create_schema
from tl_core.services.commands import CreateRecord
from tl_core.services.feed import PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient

SCOPE = "project:P123"
KEY = "P123-REC-0001"


@pytest.fixture
def client(tmp_path: Path) -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    found = EmbeddedClient.for_sqlite(db)
    found.create_record(
        CreateRecord(
            actor="user:jo",
            source="tui",
            scope=SCOPE,
            record_type="core.Record",
            title="T",
            key=KEY,
        )
    )
    return found


def post(client: EmbeddedClient, body: str, actor: str = "user:mlee") -> str:
    return client.feed_post(PostToFeed(actor=actor, source="tui", scope=SCOPE, body=body)).stream_id


def test_page_post_react_retract_and_suggestions_through_the_embedded_client(
    client: EmbeddedClient,
) -> None:
    pid = post(client, f"Spool arrived #{KEY} #hold")
    client.feed_react(
        ReactToPost(actor="user:a", source="tui", scope=SCOPE, post_id=pid, reaction="ack")
    )
    page = client.feed_page(SCOPE)
    assert [i.item_type for i in page.items] == ["post", "card"]
    post_item = page.items[0]
    assert (
        post_item.id == pid and post_item.reactions == {"ack": 1} and post_item.importance == "high"
    )
    assert page.labels == {post_item.record_ids[0]: KEY}
    (suggestion,) = page.suggestions[pid]
    assert suggestion.prompt == f"Create a constraint on {KEY}?"
    assert [i.id for i in client.feed_page(SCOPE, tag="hold").items] == [pid]

    client.feed_retract(
        RetractPost(actor="user:mlee", source="tui", scope=SCOPE, post_id=pid, reason="oops")
    )
    page = client.feed_page(SCOPE)
    assert page.items[0].retracted and page.items[0].summary == "[retracted]"
    assert page.suggestions == {}


def test_complete_through_the_embedded_client(client: EmbeddedClient) -> None:
    post(client, "x #bevel-damage @party:fab-a")
    assert [c.text for c in client.feed_complete(SCOPE, "#", "P123")] == [KEY]
    assert [c.text for c in client.feed_complete(SCOPE, "#", "bev")] == ["bevel-damage"]
    assert [c.text for c in client.feed_complete(SCOPE, "@", "")] == ["party:fab-a", "mlee"]


def test_the_app_shows_the_real_feed_and_posts_from_the_composer(client: EmbeddedClient) -> None:
    post(client, f"Spool arrived #{KEY}")
    app = TlApp(client, scope=SCOPE, actor="user:me")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("F")
        await pilot.pause()
        assert f"Spool arrived #{KEY}" in screen_text(app)
        await pilot.press("p")
        await pilot.pause()
        for key in "hello":
            await pilot.press(key)
        await pilot.press("enter")
        await pilot.pause()
        assert "hello" in screen_text(app)
        assert client.feed_page(SCOPE, item_type="post").items[0].actor == "user:me"

    run_pilot(app, scenario)
