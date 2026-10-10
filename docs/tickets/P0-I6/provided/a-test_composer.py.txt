"""Composer: token detection, completion with Tab, posting and errors (P0-I6-T06). Provided."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, OptionList
from tl_core.services.errors import InvalidScopeError
from tl_core.services.feed import PostToFeed
from tl_tui.widgets.composer import ComposerScreen, apply_completion, completion_token


class Host(App[None]):
    def __init__(self, client: FakeClient, **kw: Any) -> None:
        super().__init__()
        self.client = client
        self.kw = kw
        self.result: list[str | None] = []

    def on_mount(self) -> None:
        screen = ComposerScreen(self.client, SCOPE, actor="user:me", **self.kw)
        self.push_screen(screen, self.result.append)


def field(app: App[Any]) -> Input:
    return app.screen.query_one("#composer-input", Input)


def popup(app: App[Any]) -> OptionList:
    return app.screen.query_one("#composer-popup", OptionList)


def sent(client: FakeClient) -> list[PostToFeed]:
    return [c for c in client.feed_commands if isinstance(c, PostToFeed)]


# --- pure functions ---------------------------------------------------------------------------


def test_completion_token() -> None:
    assert completion_token("see #FV-1", 9) == ("#", "FV-1", 4)
    assert completion_token("#", 1) == ("#", "", 0)
    assert completion_token("ping @party:fa", 14) == ("@", "party:fa", 5)
    assert completion_token("see #FV-1 and", 13) is None
    assert completion_token("see #FV-1 and", 9) == ("#", "FV-1", 4)
    assert completion_token("a#b", 3) is None
    assert completion_token("me@site.org", 11) is None
    assert completion_token("plain", 5) is None
    assert completion_token("", 0) is None


def test_apply_completion() -> None:
    assert apply_completion("see #FV-1", 9, 4, "#", "FV-1001") == ("see #FV-1001 ", 13)
    assert apply_completion("see #FV-1 now", 9, 4, "#", "FV-1001") == ("see #FV-1001 now", 13)
    assert apply_completion("@pa", 3, 0, "@", "party:fab-a") == ("@party:fab-a ", 13)


# --- the screen -------------------------------------------------------------------------------


def test_typing_a_hash_shows_candidates_and_tab_completes_the_highlighted_one() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "see #FV-100"
        field(app).cursor_position = len("see #FV-100")
        await pilot.pause()
        assert popup(app).display and popup(app).option_count == 3
        assert "FV-1001" in screen_text(app) and "Control valve FCV" in screen_text(app)
        await pilot.press("down")
        await pilot.press("tab")
        assert field(app).value == "see #FV-1002 "
        assert not popup(app).display  # the space ended the token

    run_pilot(app, scenario)


def test_at_completes_people_and_enter_posts_the_text() -> None:
    client = FakeClient.with_valve_example()
    client.seed_post("x @party:fab-a", actor="user:mlee")
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "ping @pa"
        field(app).cursor_position = 8
        await pilot.pause()
        await pilot.press("tab")
        assert field(app).value == "ping @party:fab-a "
        await pilot.press("enter")
        await pilot.pause()
        (command,) = sent(client)[1:]
        assert (command.actor, command.source, command.scope) == ("user:me", "tui", SCOPE)
        assert command.body == "ping @party:fab-a "
        assert app.result == [client.feed_page(SCOPE).items[0].id]

    run_pilot(app, scenario)


def test_escape_closes_the_list_first_and_then_cancels() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "#ho"
        field(app).cursor_position = 3
        await pilot.pause()
        assert popup(app).display
        await pilot.press("escape")
        assert not popup(app).display and app.screen.id != "_default"
        await pilot.press("escape")
        await pilot.pause()
        assert app.result == [None]

    run_pilot(app, scenario)


def test_tab_and_arrows_do_nothing_without_a_list() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "plain text"
        field(app).cursor_position = 10
        await pilot.pause()
        await pilot.press("tab", "down", "up")
        assert field(app).value == "plain text"

    run_pilot(app, scenario)


def test_a_blank_post_is_refused_and_the_composer_stays_open() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "   "
        await pilot.press("enter")
        await pilot.pause()
        assert "Write something first" in screen_text(app)
        assert sent(client) == [] and app.result == []

    run_pilot(app, scenario)


def test_a_client_error_is_shown_and_the_text_is_kept() -> None:
    client = FakeClient.with_valve_example()

    def refuse(cmd: PostToFeed) -> Any:
        raise InvalidScopeError("a post belongs to a project")

    client.feed_post = refuse  # type: ignore[method-assign]
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "hello"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "a post belongs to a project" in screen_text(app)
        assert field(app).value == "hello" and app.result == []

    run_pilot(app, scenario)


def test_a_prefill_starts_the_text_with_the_cursor_at_the_end() -> None:
    app = Host(FakeClient.with_valve_example(), prefill="#FV-1001 ")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert field(app).value == "#FV-1001 " and field(app).cursor_position == 9
        await pilot.press("h", "i")
        assert field(app).value == "#FV-1001 hi"

    run_pilot(app, scenario)


def test_square_brackets_in_text_are_not_markup() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field(app).value = "done [x] #fyi"
        await pilot.press("enter")
        await pilot.pause()
        assert sent(client)[0].body == "done [x] #fyi"

    run_pilot(app, scenario)
