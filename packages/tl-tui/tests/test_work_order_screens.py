"""The work order backlog and the work order screen on a pilot, with `FakeClient` (P2-I4A T07b).

The host app carries an `actor` (the signed-in person) so that `m` has someone to filter by.
"""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from fakes_requisitions import PROJECT, seed_requisitions
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.screen import Screen
from tl_tui.widgets.work_order_backlog import WorkOrderBacklogScreen, WorkOrderScreen

ACTOR = "user:uma"


class HostApp(App[None]):
    def __init__(self, screen: Screen[Any]) -> None:
        super().__init__()
        self.actor = ACTOR
        self.host = screen

    def on_mount(self) -> None:
        self.push_screen(self.host)


def _client() -> FakeClient:
    client = FakeClient()
    seed_requisitions(client)
    return client


async def _settle(pilot: Pilot[Any]) -> None:
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


def _drive(screen: Any, steps: Any, size: tuple[int, int] = (120, 40)) -> None:
    app = HostApp(screen)

    async def go(pilot: Pilot[Any]) -> None:
        await _settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


def test_the_backlog_mounts_at_80_and_170_columns_without_overflow() -> None:
    for width in (80, 170):
        screen = WorkOrderBacklogScreen(_client(), PROJECT)
        seen: dict[str, str] = {}

        async def steps(pilot: Pilot[Any], app: HostApp, seen: dict[str, str] = seen) -> None:
            seen["text"] = screen_text(app)

        _drive(screen, steps, size=(width, 30))
        lines = seen["text"].split("\n")
        assert all(len(line) <= width for line in lines), width
        assert f"{PROJECT}-WO-0001" in seen["text"], width


def test_s_and_m_change_the_row_count() -> None:
    counts: list[int] = []

    async def steps(pilot: Pilot[Any], app: HostApp) -> None:
        screen = app.screen
        counts.append(len(screen.shown))  # type: ignore[attr-defined]
        await pilot.press("m")  # assigned to the signed-in actor: WO-2 only
        await _settle(pilot)
        counts.append(len(screen.shown))  # type: ignore[attr-defined]
        await pilot.press("m")  # all again
        await _settle(pilot)
        counts.append(len(screen.shown))  # type: ignore[attr-defined]
        await pilot.press("s")  # state Open: WO-2
        await _settle(pilot)
        counts.append(len(screen.shown))  # type: ignore[attr-defined]
        await pilot.press("s")  # state Scheduled: WO-1
        await _settle(pilot)
        counts.append(len(screen.shown))  # type: ignore[attr-defined]

    _drive(WorkOrderBacklogScreen(_client(), PROJECT), steps)
    assert counts == [2, 1, 2, 1, 1]


def test_enter_pushes_the_work_order_screen() -> None:
    pushed: list[str] = []

    async def steps(pilot: Pilot[Any], app: HostApp) -> None:
        await pilot.press("enter")
        await _settle(pilot)
        pushed.append(type(app.screen).__name__)

    _drive(WorkOrderBacklogScreen(_client(), PROJECT), steps)
    assert pushed == [WorkOrderScreen.__name__]


def test_a_missing_key_shows_an_error_status_and_no_traceback() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: HostApp) -> None:
        await _settle(pilot)
        seen["text"] = screen_text(app)

    _drive(WorkOrderScreen(_client(), PROJECT, f"{PROJECT}-WO-9999"), steps)
    assert "could not be read" in seen["text"]
    assert "no work order" in seen["text"]
    assert "Traceback" not in seen["text"]
