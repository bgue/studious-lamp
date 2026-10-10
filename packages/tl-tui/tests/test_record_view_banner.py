"""Record view "updated by" line (P0-I4-T62). Provided; do not edit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Static
from tl_tui.widgets.record_view import RecordView


class Host(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.client = FakeClient.with_valve_example()

    def compose(self) -> ComposeResult:
        yield RecordView(self.client, SCOPE, "FV-1001", id="record")


def banner(app: Host) -> Static:
    return app.query_one("#rv-banner", Static)


def test_the_line_is_hidden_until_there_is_something_to_say() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert not banner(app).display
        assert "Updated by" not in screen_text(app)

    run_pilot(app, scenario)


def test_note_remote_update_shows_who_and_the_new_version_under_the_header() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        view.note_remote_update("user:bob", 5)
        await pilot.pause()
        assert banner(app).display
        lines = screen_text(app).splitlines()
        row = next(i for i, line in enumerate(lines) if "! Updated by user:bob (now v5)" in line)
        header = next(i for i, line in enumerate(lines) if "FV-1001 ·" in line)
        assert row > header  # under the header
        assert all("Updated by" not in line for line in lines[:header])

    run_pilot(app, scenario)


def test_the_time_is_shown_when_given_and_a_later_note_replaces_the_line() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        view.note_remote_update("user:bob", 5, datetime(2026, 10, 10, 9, 30, 12, tzinfo=UTC))
        await pilot.pause()
        assert "! Updated by user:bob at 09:30:12 (now v5)" in screen_text(app)
        view.note_remote_update("user:carol", 6)
        await pilot.pause()
        text = screen_text(app)
        assert "! Updated by user:carol (now v6)" in text and "user:bob" not in text

    run_pilot(app, scenario)


def test_clear_remote_update_hides_the_line_again() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        view.note_remote_update("user:bob", 5)
        await pilot.pause()
        view.clear_remote_update()
        await pilot.pause()
        assert not banner(app).display
        assert "Updated by" not in screen_text(app)

    run_pilot(app, scenario)


def test_the_actor_is_not_read_as_markup_and_reload_keeps_the_line() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        view.note_remote_update("user:[bold]x[/]", 2)
        view.reload()
        await pilot.pause()
        assert "! Updated by user:[bold]x[/] (now v2)" in screen_text(app)

    run_pilot(app, scenario)
