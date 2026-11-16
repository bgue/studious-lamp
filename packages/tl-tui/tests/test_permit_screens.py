"""The permit log and screen on `FakeClient`, through the Textual pilot (P2-PTW-T11).

Model: `test_inspection_screens.py`. The commands are recorded by the fake (`punch_commands`); a
refusal is a `ServiceError` the test puts on the fake's door.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_permits import seed_permits
from helpers import run_pilot, screen_text, settle, static_of
from textual.pilot import Pilot
from tl_core.services.errors import ServiceError
from tl_mod_permits.commands import (
    ApprovePermit,
    ResumePermit,
    SuspendPermit,
)
from tl_tui.app import TlApp
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.permit_log import PermitLogScreen, PermitScreen

SIZES = [(80, 40), (170, 44)]
KEY_REQUESTED = "P123-PTW-0001"  # Requested: approve and reject
KEY_ACTIVE = "P123-PTW-0003"  # Active: suspend and revalidate, not approve
KEY_SUSPENDED = "P123-PTW-0005"  # Suspended: resume
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app(*, actor: str = "user:kim") -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_permits(client)
    return TlApp(client, scope=SCOPE, actor=actor), client


def run(app: TlApp, steps: Step, size: tuple[int, int] = (170, 44)) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


def open_log(app: TlApp) -> None:
    app.action_permits()


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
        assert isinstance(screen, PermitLogScreen)
        assert all(len(line) <= size[0] for line in text.splitlines()), f"overflow at {size}"
        header = next(line for line in text.splitlines() if "Number" in line)
        assert header.index("Subject") < header.index("State"), f"Subject right of State {size}"


def test_the_permit_screen_mounts_at_80_and_170_columns() -> None:
    def open_permit(app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_ACTIVE))

    for size in SIZES:
        screen, text = screen_at(size, open_permit)
        assert isinstance(screen, PermitScreen)
        assert all(len(line) <= size[0] for line in text.splitlines()), f"overflow at {size}"
        assert f"{KEY_ACTIVE} · Permit 3" in text


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


def test_the_log_starts_with_every_permit() -> None:
    assert row_count_after([]) == 8


def test_s_shows_the_next_state_only() -> None:
    assert row_count_after(["s"]) == 1  # Requested


def test_t_shows_the_next_type_only() -> None:
    assert row_count_after(["t"]) == 2  # hot work: permits 2 and 7


def test_a_shows_the_next_area_only() -> None:
    assert row_count_after(["a"]) == 1  # area A1: permit 3


def test_m_shows_the_permits_whose_holder_is_the_actor() -> None:
    assert row_count_after(["m"], actor="Ann") == 2  # holder Ann: permits 4 and 6


def test_the_keys_row_names_the_log_keys() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_log(app)
        await settle(pilot)
        seen["text"] = screen_text(app)

    app, _client = make_app()
    run(app, steps)
    assert "s state" in seen["text"]
    assert "t type" in seen["text"]
    assert "m mine" in seen["text"]


# --- Enter and the permit screen ---------------------------------------------------------------


def test_enter_pushes_the_permit_screen() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_log(app)
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen

    app, _client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PermitScreen)
    assert seen["screen"].key == KEY_REQUESTED


def test_approve_on_a_requested_permit_asks_and_sends_approve_with_the_id_and_version() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_REQUESTED))
        await settle(pilot)
        await pilot.press("a")
        await settle(pilot)
        seen["asks"] = isinstance(app.screen, ActionFormScreen)
        await pilot.press("y")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    assert seen["asks"]
    (cmd,) = client.punch_commands
    assert isinstance(cmd, ApprovePermit)
    assert cmd.permit == "PTW-1"
    assert cmd.expected_version == 1
    assert cmd.scope == SCOPE
    assert cmd.actor == "user:kim"


def test_s_on_a_requested_permit_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_REQUESTED))
        await settle(pilot)
        await pilot.press("s")
        await settle(pilot)
        seen["screen"] = app.screen

    app, client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PermitScreen)
    assert client.punch_commands == []


def test_suspend_on_an_active_permit_asks_a_reason_and_sends_suspend() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_ACTIVE))
        await settle(pilot)
        await pilot.press("s")
        await settle(pilot)
        await pilot.press(*"Gas")
        await pilot.press("enter")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    (cmd,) = client.punch_commands
    assert isinstance(cmd, SuspendPermit)
    assert cmd.permit == "PTW-3"
    assert cmd.reason == "Gas"


def test_approve_on_an_active_permit_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_ACTIVE))
        await settle(pilot)
        await pilot.press("a")
        await settle(pilot)
        seen["screen"] = app.screen

    app, client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PermitScreen)
    assert client.punch_commands == []


def test_resume_on_a_suspended_permit_sends_resume() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_SUSPENDED))
        await settle(pilot)
        await pilot.press("r")
        await settle(pilot)
        await pilot.press("y")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    (cmd,) = client.punch_commands
    assert isinstance(cmd, ResumePermit)
    assert cmd.permit == "PTW-5"


def test_a_blank_reason_sends_nothing_and_does_not_crash() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_ACTIVE))
        await settle(pilot)
        await pilot.press("s")
        await settle(pilot)
        await pilot.press(" ")
        await pilot.press("enter")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    assert client.punch_commands == []


def test_a_refusal_shows_on_the_status_line_and_the_permit_reads_again() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", KEY_REQUESTED))
        await settle(pilot)

        def refuse(name: str, cmd: object) -> None:
            raise ServiceError("You requested this permit, so someone else must approve it.")

        app.client.permit_command = refuse  # type: ignore[method-assign]
        await pilot.press("a")
        await settle(pilot)
        await pilot.press("y")
        await settle(pilot)
        seen["status"] = static_of(app.screen, "#permit-status")
        seen["screen"] = app.screen

    app, _client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], PermitScreen)
    assert "someone else must approve it" in seen["status"]


def test_an_unknown_permit_shows_an_error_status_and_no_traceback() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(PermitScreen(app.client, "P123", "P123-PTW-9999"))
        await settle(pilot)
        seen["page"] = static_of(app.screen, "#permit-page")
        seen["status"] = static_of(app.screen, "#permit-status")

    app, _client = make_app()
    run(app, steps)
    assert "This permit could not be read." in seen["page"]
    assert seen["status"].startswith("! ")
