"""The snapshots of a schedule come a page at a time on the schedule screen (round 3, F4)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_tui.app import TlApp
from tl_tui.schedule_text import snapshot_page_line
from tl_tui.widgets.schedule_screen import SNAPSHOT_PAGE, ScheduleScreen

TOTAL = 130


def crowded() -> FakeClient:
    """MAIN with ``TOTAL`` snapshots, newest first (the fake pages them like the service)."""
    client = FakeClient()
    client.seed_schedule("P123")
    detail = client._schedules[("P123", "MAIN")]  # pyright: ignore[reportPrivateUsage]
    template = detail.snapshots[1]
    many = [
        template.model_copy(update={"number": n, "key": f"MAIN#{n}", "is_current": n == TOTAL})
        for n in range(TOTAL, 0, -1)
    ]
    client._schedules[("P123", "MAIN")] = detail.model_copy(  # pyright: ignore[reportPrivateUsage]
        update={"snapshots": many, "snapshot_count": TOTAL, "current_snapshot_number": TOTAL}
    )
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, ScheduleScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f12")
        await pilot.pause()
        assert isinstance(app.screen, ScheduleScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def numbers(screen: ScheduleScreen) -> list[int]:
    assert screen.detail is not None
    return [s.number for s in screen.detail.snapshots]


def test_the_page_line_says_where_the_page_is() -> None:
    assert snapshot_page_line(0, 5, 5) is None
    assert snapshot_page_line(0, 50, 130) == "snapshots 1 to 50 of 130  (n next page)"
    assert snapshot_page_line(50, 50, 130) == (
        "snapshots 51 to 100 of 130  (n next page  b previous page)"
    )
    assert snapshot_page_line(100, 30, 130) == "snapshots 101 to 130 of 130  (b previous page)"
    assert snapshot_page_line(200, 0, 130) == "snapshots 0 to 200 of 130  (b previous page)"


def test_the_first_page_is_the_newest_snapshots_and_n_and_b_turn_the_pages() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        table = screen.query_one("#sc-snapshots", DataTable)
        assert table.row_count == SNAPSHOT_PAGE and numbers(screen)[0] == TOTAL
        assert "snapshots 1 to 50 of 130" in screen_text(app)
        await pilot.press("n")
        await pilot.pause()
        assert numbers(screen) == list(range(80, 30, -1)) and table.row_count == SNAPSHOT_PAGE
        assert "snapshots 51 to 100 of 130" in screen_text(app)
        await pilot.press("n", "n")
        await pilot.pause()
        assert numbers(screen) == list(range(30, 0, -1))  # the last, short page
        assert "oldest snapshots" in str(screen.query_one("#sc-status", Static).render())
        await pilot.press("b")
        await pilot.pause()
        assert numbers(screen)[0] == 80
        await pilot.press("b", "b")
        await pilot.pause()
        assert numbers(screen)[0] == TOTAL and screen.page_start == 0
        assert "newest snapshots" in str(screen.query_one("#sc-status", Static).render())

    scenario(crowded(), steps)


def test_a_reload_keeps_the_page() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("f5")
        await pilot.pause()
        assert screen.page_start == SNAPSHOT_PAGE and numbers(screen)[0] == 80

    scenario(crowded(), steps)


def test_a_schedule_with_one_page_shows_no_page_line_and_n_says_so() -> None:
    client = FakeClient()
    client.seed_schedule("P123")

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        assert "snapshots 1 to" not in screen_text(app)
        await pilot.press("n")
        await pilot.pause()
        assert screen.page_start == 0
        assert "oldest snapshots" in str(screen.query_one("#sc-status", Static).render())

    scenario(client, steps)
