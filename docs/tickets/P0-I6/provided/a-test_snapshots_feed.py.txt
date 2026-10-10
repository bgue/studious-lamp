"""Snapshot of the feed pane at 120x40 (P0-I6-T04). Provided; T04 creates the snapshot file."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from textual.app import App, ComposeResult
from tl_tui.widgets.feed_pane import FeedPane


class FeedApp(App[None]):
    def __init__(self) -> None:
        super().__init__()
        client = FakeClient.with_valve_example()
        client.seed_card("jsmith created 14 records")
        client.seed_post(
            "Spool arrived with damaged bevels #FV-1001 #hold @party:fab-a", actor="user:mlee"
        )
        client.seed_post("Classified 3 letters #fyi", actor="agent:triage")
        self.client = client

    def compose(self) -> ComposeResult:
        yield FeedPane(self.client, SCOPE, actor="user:me", id="feed")


def test_feed_pane_snapshot(snap_compare: Any) -> None:
    assert snap_compare(FeedApp(), terminal_size=(120, 40))
