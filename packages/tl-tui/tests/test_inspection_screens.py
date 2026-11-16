"""The inspection log and screen on `FakeClient`, through the Textual pilot (P2-INSP-T10).

Model: `test_punch_screens.py`. The commands are recorded by the fake (`punch_commands`); a refusal
is a `ServiceError` the test puts on the fake's door.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_insp import seed_inspections
from helpers import run_pilot, screen_text, settle, static_of
from textual.pilot import Pilot
from tl_core.services.errors import ServiceError
from tl_mod_quality.commands import CancelInspection, ReinspectInspection, VerifyInspection
from tl_tui.app import TlApp
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.inspection_log import InspectionLogScreen, InspectionScreen

SIZES = [(80, 40), (170, 44)]
KEY_PLANNED = "P123-INS-0001"  # Planned: no verify, cancel is offered
KEY_SCHEDULED = "P123-INS-0002"  # Scheduled: cancel and no verify
KEY_DONE = "P123-INS-0003"  # Done: verify and reinspect
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app(*, actor: str = "user:kim") -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_inspections(client)
    return TlApp(client, scope=SCOPE, actor=actor), client


def run(app: TlApp, steps: Step, size: tuple[int, int] = (170, 44)) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


def open_log(app: TlApp) -> None:
    app.action_inspections()


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
        assert isinstance(screen, InspectionLogScreen)
        assert all(len(line) <= size[0] for line in text.splitlines()), f"overflow at {size}"
        header = next(line for line in text.splitlines() if "Number" in line)
        assert header.index("Title") < header.index("Point"), f"Title right of State at {size}"


def test_the_inspection_screen_mounts_at_80_and_170_columns() -> None:
    def open_inspection(app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", KEY_DONE))

    for size in SIZES:
        screen, text = screen_at(size, open_inspection)
        assert isinstance(screen, InspectionScreen)
        assert all(len(line) <= size[0] for line in text.splitlines()), f"overflow at {size}"
        assert f"{KEY_DONE} · Inspection 3" in text


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


def test_the_log_starts_with_every_inspection() -> None:
    assert row_count_after([]) == 6


def test_s_shows_the_next_state_only() -> None:
    assert row_count_after(["s"]) == 2  # Planned


def test_p_shows_the_next_point_only() -> None:
    assert row_count_after(["p"]) == 3  # hold: 1, 2 and 6


def test_m_shows_the_inspections_of_the_inspector_named_as_the_actor() -> None:
    assert row_count_after(["m"], actor="M. Okafor") == 2


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


# --- Enter and the inspection screen -----------------------------------------------------------


def test_enter_pushes_the_inspection_screen() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_log(app)
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen

    app, _client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], InspectionScreen)
    assert seen["screen"].key == KEY_PLANNED


def test_verify_on_a_done_inspection_asks_are_you_sure_and_sends_verify() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", KEY_DONE))
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
    assert isinstance(cmd, VerifyInspection)
    assert cmd.inspection == "INS-3"
    assert cmd.expected_version == 1
    assert cmd.scope == SCOPE
    assert cmd.actor == "user:kim"


def test_verify_on_a_planned_inspection_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", KEY_PLANNED))
        await settle(pilot)
        await pilot.press("v")
        await settle(pilot)
        seen["screen"] = app.screen

    app, client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], InspectionScreen)
    assert client.punch_commands == []


def test_cancel_on_a_scheduled_inspection_asks_a_reason_and_sends_cancel() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", KEY_SCHEDULED))
        await settle(pilot)
        await pilot.press("x")
        await settle(pilot)
        await pilot.press(*"Moved")
        await pilot.press("enter")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    (cmd,) = client.punch_commands
    assert isinstance(cmd, CancelInspection)
    assert cmd.inspection == "INS-2"
    assert cmd.reason == "Moved"


def test_reinspect_on_a_done_inspection_sends_no_date_when_none_is_typed() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", KEY_DONE))
        await settle(pilot)
        await pilot.press("r")
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)

    app, client = make_app()
    run(app, steps)
    (cmd,) = client.punch_commands
    assert isinstance(cmd, ReinspectInspection)
    assert cmd.planned_on is None


def test_a_refusal_shows_on_the_status_line_and_the_screen_reads_again() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", KEY_DONE))
        await settle(pilot)

        def refuse(name: str, cmd: object) -> None:
            raise ServiceError("You recorded this inspection, so someone else must verify it.")

        app.client.quality_command = refuse  # type: ignore[method-assign]
        await pilot.press("v")
        await settle(pilot)
        await pilot.press("y")
        await settle(pilot)
        seen["status"] = static_of(app.screen, "#inspection-status")
        seen["screen"] = app.screen

    app, _client = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], InspectionScreen)
    assert "someone else must verify it" in seen["status"]


def test_an_unknown_inspection_shows_an_error_status_and_no_traceback() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(InspectionScreen(app.client, "P123", "P123-INS-9999"))
        await settle(pilot)
        seen["page"] = static_of(app.screen, "#inspection-page")
        seen["status"] = static_of(app.screen, "#inspection-status")

    app, _client = make_app()
    run(app, steps)
    assert "This inspection could not be read." in seen["page"]
    assert seen["status"].startswith("! ")
