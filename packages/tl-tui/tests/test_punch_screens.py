"""The punch log and item screen on `FakeClient`, through the Textual pilot (P2-PUNCH-T06).

Model: `test_materials_screens.py`. The commands are recorded by the fake (`punch_commands`); a
refusal is a `ServiceError` the test puts on the fake's door.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_punch import seed_punch
from helpers import run_pilot, screen_text, settle, static_of
from textual.pilot import Pilot
from tl_core.services.errors import ServiceError
from tl_mod_quality.commands import ClearPunchItem, ReopenPunchItem, VerifyPunchItem
from tl_tui.app import TlApp
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.punch_log import PunchLogScreen, PunchScreen

SIZES = [(80, 40), (170, 44)]
KEY_OPEN = "P123-PUN-0001"  # Open, category A, overdue
KEY_CLEARED = "P123-PUN-0004"
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app(*, actor: str = "user:kim") -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_punch(client)
    return TlApp(client, scope=SCOPE, actor=actor), client


def run(app: TlApp, steps: Step, size: tuple[int, int] = (170, 44)) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


def open_log(app: TlApp) -> None:
    app.action_punch()


# --- layout ------------------------------------------------------------------------------------


def screen_at(size: tuple[int, int], open_screen: Callable[[TlApp], None]) -> tuple[Any, str]:
    """The screen the step opens, and its rendered text, at ``size``."""
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_screen(app)
        await settle(pilot)
        seen["screen"] = app.screen
        seen["text"] = screen_text(app)

    app, _client = make_app()
    run(app, steps, size=size)
    return seen["screen"], seen["text"]


def test_the_log_mounts_at_80_and_170_columns_without_overflow() -> None:
    for size in SIZES:
        screen, text = screen_at(size, open_log)
        assert isinstance(screen, PunchLogScreen)
        assert all(len(line) <= size[0] for line in text.splitlines()), f"overflow at {size}"
        header = next(line for line in text.splitlines() if "Number" in line)
        assert header.index("Subject") < header.index("Cat"), f"Subject right of Cat at {size}"


def test_the_item_screen_mounts_at_80_and_170_columns() -> None:
    def open_item(app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_OPEN))

    for size in SIZES:
        screen, text = screen_at(size, open_item)
        assert isinstance(screen, PunchScreen)
        assert all(len(line) <= size[0] for line in text.splitlines())
        assert f"{KEY_OPEN} · Punch item 1" in text


# --- the log's filter keys ---------------------------------------------------------------------


def row_count_after(keys: list[str], actor: str = "user:kim") -> int:
    seen: dict[str, int] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_log(app)
        await settle(pilot)
        for key in keys:
            await pilot.press(key)
            await settle(pilot)
        seen["count"] = len(app.screen.shown)  # type: ignore[attr-defined]

    app, _client = make_app(actor=actor)
    run(app, steps)
    return seen["count"]


def test_the_log_starts_with_every_item() -> None:
    assert row_count_after([]) == 6


def test_s_shows_the_open_items() -> None:
    assert row_count_after(["s"]) == 3


def test_c_shows_category_a_only() -> None:
    assert row_count_after(["c"]) == 2


def test_o_shows_the_overdue_items_only() -> None:
    assert row_count_after(["o"]) == 1


def test_m_shows_the_items_of_the_signed_in_actor() -> None:
    assert row_count_after(["m"], actor="Ferrari") == 3


def test_the_keys_row_names_the_log_keys() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_log(app)
        await settle(pilot)
        seen["text"] = screen_text(app)

    app, _client = make_app()
    run(app, steps)
    assert "s state" in seen["text"]
    assert "m mine" in seen["text"]


# --- Enter and the item screen -----------------------------------------------------------------


def test_enter_pushes_the_item_screen() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_log(app)
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen

    app, _client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PunchScreen)
    assert seen["screen"].key == KEY_OPEN


def test_clear_on_an_open_item_asks_a_note_and_sends_clear() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_OPEN))
        await settle(pilot)
        await pilot.press("c")
        await settle(pilot)
        seen["asks"] = isinstance(app.screen, ActionFormScreen)
        await pilot.press(*"Fixed")
        await pilot.press("enter")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    assert seen["asks"]
    (cmd,) = client.punch_commands
    assert isinstance(cmd, ClearPunchItem)
    assert cmd.note == "Fixed"
    assert cmd.punch_item == "PUN-1"
    assert cmd.scope == SCOPE
    assert cmd.actor == "user:kim"


def test_verify_on_a_cleared_item_asks_are_you_sure_and_sends_verify() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_CLEARED))
        await settle(pilot)
        await pilot.press("v")
        await settle(pilot)
        seen["asks"] = isinstance(app.screen, ActionFormScreen)
        await pilot.press("y")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    assert seen["asks"]
    (cmd,) = client.punch_commands
    assert isinstance(cmd, VerifyPunchItem)
    assert cmd.punch_item == "PUN-4"


def test_reopen_on_a_cleared_item_asks_a_reason() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_CLEARED))
        await settle(pilot)
        await pilot.press("o")
        await settle(pilot)
        await pilot.press(*"Leaks")
        await pilot.press("enter")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    (cmd,) = client.punch_commands
    assert isinstance(cmd, ReopenPunchItem)
    assert cmd.reason == "Leaks"


def test_a_key_not_offered_for_the_state_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_CLEARED))
        await settle(pilot)
        await pilot.press("c")  # Clear is for Open only
        await settle(pilot)
        seen["screen"] = app.screen

    app, client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PunchScreen)
    assert client.punch_commands == []


def test_verify_on_an_open_item_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_OPEN))
        await settle(pilot)
        await pilot.press("v")
        await settle(pilot)
        seen["screen"] = app.screen

    app, client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PunchScreen)
    assert client.punch_commands == []


def test_a_refusal_shows_on_the_status_line() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", KEY_CLEARED))
        await settle(pilot)

        def refuse(name: str, cmd: object) -> None:
            raise ServiceError("You cleared this item, so someone else must verify it.")

        app.client.quality_command = refuse  # type: ignore[method-assign]
        await pilot.press("v")
        await settle(pilot)
        await pilot.press("y")
        await settle(pilot)
        seen["status"] = static_of(app.screen, "#punch-status")

    app, _client = make_app()
    run(app, steps)
    assert seen["status"].startswith("! ")
    assert "someone else must verify" in seen["status"]


def test_an_unknown_item_shows_an_error_and_no_traceback() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PunchScreen(app.client, "P123", "P123-PUN-9999"))
        await settle(pilot)
        seen["status"] = static_of(app.screen, "#punch-status")
        seen["page"] = static_of(app.screen, "#punch-page")

    app, _client = make_app()
    run(app, steps)
    assert seen["status"].startswith("! ")
    assert seen["page"] == "This punch item could not be read."
