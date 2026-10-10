"""The feed in the app: `F` opens it, `p` the composer, Esc goes back (P0-I6-S8)."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input
from tl_core.services.feed import PostToFeed
from tl_tui.app import TlApp
from tl_tui.widgets.composer import ComposerScreen
from tl_tui.widgets.feed_pane import FeedPane
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.main_area import MainArea


def seeded() -> FakeClient:
    client = FakeClient.with_valve_example()
    client.seed_post("Spool arrived #FV-1001 #hold", actor="user:mlee")
    client.seed_card("jsmith created 2 records")
    return client


def sent(client: FakeClient) -> list[PostToFeed]:
    return [c for c in client.feed_commands if isinstance(c, PostToFeed)]


def test_f_opens_the_project_feed_and_escape_returns_to_the_grid() -> None:
    app = TlApp(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("F")
        await pilot.pause()
        main = app.query_one("#main", MainArea)
        assert main.showing_feed
        pane = app.query_one(FeedPane)
        assert pane.record_id is None and len(pane.items) == 2
        assert "Spool arrived #FV-1001 #hold" in screen_text(app)
        assert app.focused is not None and pane in app.focused.ancestors_with_self
        await pilot.press("escape")
        await pilot.pause()
        assert not main.showing_feed and app.query_one("#grid", RecordGrid).display
        assert not list(app.query(FeedPane))

    run_pilot(app, scenario)


def test_f_in_a_record_view_opens_that_records_feed() -> None:
    app = TlApp(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")  # open the first record
        await pilot.pause()
        await pilot.press("F")
        await pilot.pause()
        pane = app.query_one(FeedPane)
        assert pane.record_key == "FV-1001" and pane.record_id is not None
        assert [i.item_type for i in pane.items] == ["post"]

    run_pilot(app, scenario)


def test_p_from_the_grid_posts_and_the_feed_shows_it() -> None:
    client = seeded()
    app = TlApp(client, actor="user:me")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, ComposerScreen)
        app.screen.query_one("#composer-input", Input).value = "Crew on site #fyi"
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, ComposerScreen)
        (command,) = sent(client)[1:]
        assert (command.actor, command.scope, command.body) == (
            "user:me",
            SCOPE,
            "Crew on site #fyi",
        )
        await pilot.press("F")
        await pilot.pause()
        assert "Crew on site #fyi" in screen_text(app)

    run_pilot(app, scenario)


def test_p_in_the_feed_pane_opens_the_composer_and_reloads_the_pane() -> None:
    client = seeded()
    app = TlApp(client, actor="user:me")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("F")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, ComposerScreen)
        app.screen.query_one("#composer-input", Input).value = "Second shift started"
        await pilot.press("enter")
        await pilot.pause()
        pane = app.query_one(FeedPane)
        assert pane.items[0].summary == "Second shift started"

    run_pilot(app, scenario)


def test_p_in_a_record_feed_starts_the_composer_with_the_records_tag() -> None:
    app = TlApp(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter", "F")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, ComposerScreen)
        assert app.screen.query_one("#composer-input", Input).value == "#FV-1001 "

    run_pilot(app, scenario)


def test_f_and_p_do_nothing_under_a_modal() -> None:
    app = TlApp(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screens = len(app.screen_stack)
        await pilot.press("escape")  # closes the composer
        await pilot.pause()
        await pilot.press("n")  # a form
        await pilot.pause()
        depth = len(app.screen_stack)
        await pilot.press("F")
        await pilot.pause()
        assert len(app.screen_stack) == depth and screens >= 2

    run_pilot(app, scenario)


def test_the_palette_offers_the_feed_commands() -> None:
    from tl_tui.commands import command_by_id

    assert command_by_id("feed") is not None and command_by_id("post") is not None
