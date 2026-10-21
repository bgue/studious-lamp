"""The activity screen with a pilot (P1-I4-T09a3). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.testing import make_activity
from tl_tui.app import TlApp
from tl_tui.widgets import activity_screen
from tl_tui.widgets.activity_screen import ActivityScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, ActivityScreen], Awaitable[None]],
    *,
    number: int | None = None,
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(ActivityScreen(client, "P123", "MAIN", number))
        await pilot.pause()
        assert isinstance(app.screen, ActivityScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def ids(screen: ActivityScreen) -> list[str]:
    return [a.activity_id for a in screen.shown]


def status(screen: ActivityScreen) -> str:
    return str(screen.query_one("#ac-status", Static).render())


def test_it_lists_the_current_snapshots_activities_and_describes_the_first() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        text = screen_text(app)
        assert "Activities of Snapshot 2" in text
        assert ids(screen) == ["A1220", "A1230", "A1240", "A2500"]
        assert screen.query_one("#ac-table", DataTable).row_count == 4
        assert "Set rack foundations" in text and "critical" in text
        assert status(screen) == "Snapshot 2  data date 2026-10-12  |  1-4 of 4 activities"
        assert "A1220  Set rack foundations  |  Snapshot 2" in text
        assert "predecessors 0" in text and "successors 1" in text and "  A1230  FS  lag 0h" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ActivityScreen)

    scenario(world(), steps)


def test_moving_to_an_activity_shows_its_neighbours_and_its_float_trend() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("down")
        await pilot.pause()
        text = screen_text(app)
        assert "A1230  Install pipe rack supports  |  Snapshot 2" in text
        assert "float total 32h  free 40h" in text
        assert "predecessors 1" in text and "  A1220  FS  lag 0h" in text
        assert "successors 2" in text and "  A2500  FS  lag 0h" in text
        assert "float trend:" in text
        assert "#1  2026-10-05  Superseded  float 9d" in text
        assert "#2  2026-10-12  Published  float 4d" in text

    scenario(world(), steps)


def test_an_activity_that_is_in_one_snapshot_only_has_a_one_line_trend() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("down", "down", "down")  # A2500, new in snapshot 2
        await pilot.pause()
        text = screen_text(app)
        assert "A2500  Weld inspection hold point  |  Snapshot 2" in text
        assert "#2  2026-10-12  Published  float 2d" in text and "#1  2026-10-05" not in text

    scenario(world(), steps)


def test_a_named_snapshot_is_listed_and_an_activity_it_lacks_is_not() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        assert ids(screen) == ["A1220", "A1230", "A1240", "A1990"]
        assert "Activities of Snapshot 1" in screen_text(app)
        await pilot.press("down", "down", "down")  # A1990, which snapshot 2 lacks
        await pilot.pause()
        text = screen_text(app)
        assert "A1990  Temporary fencing  |  Snapshot 1" in text
        assert "#1  2026-10-05  Superseded  float 12d" in text

    scenario(world(), steps, number=1)


def test_c_keeps_the_critical_activities_and_again_shows_them_all() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("c")
        await pilot.pause()
        assert ids(screen) == ["A1220"] and screen.critical_only
        assert status(screen).endswith("1-1 of 1 activities  |  critical only")
        await pilot.press("c")
        await pilot.pause()
        assert len(ids(screen)) == 4 and not screen.critical_only

    scenario(world(), steps)


def test_the_filter_box_narrows_by_id_or_name_and_the_letters_are_text_there() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("slash")
        await pilot.press(*"rack")  # r, a, c, k: c is a key of the screen, here it is text
        await pilot.pause()
        assert ids(screen) == ["A1220", "A1230", "A1240"] and not screen.critical_only
        assert 'filter "rack"' in status(screen)
        await pilot.press("escape")  # the first Escape clears the box
        await pilot.pause()
        assert screen.query_one("#ac-filter", Input).value == ""
        assert len(ids(screen)) == 4 and isinstance(app.screen, ActivityScreen)

    scenario(world(), steps)


def test_n_and_b_page_forward_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity_screen, "PAGE", 3)

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        assert ids(screen) == ["A1220", "A1230", "A1240"]
        assert status(screen).endswith("1-3 of 4 activities")
        await pilot.press("b")
        await pilot.pause()
        assert "This is the first page." in status(screen) and screen.first == 0
        await pilot.press("n")
        await pilot.pause()
        assert ids(screen) == ["A2500"] and screen.first == 3
        assert status(screen).endswith("4-4 of 4 activities")
        await pilot.press("n")
        await pilot.pause()
        assert "This is the last page." in status(screen) and screen.first == 3
        await pilot.press("b")
        await pilot.pause()
        assert ids(screen) == ["A1220", "A1230", "A1240"] and screen.first == 0

    scenario(world(), steps)


def test_a_snapshot_with_no_rows_says_so() -> None:
    client = FakeClient()
    client.add_schedule("P123", "MAIN", [("2026-10-05T08:00", "Invalid", [], [])])

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        assert screen.shown == []
        assert status(screen).startswith("! ") and "has no activities to read" in status(screen)
        await pilot.press("c", "n", "b")
        await pilot.pause()
        assert isinstance(app.screen, ActivityScreen)

    scenario(client, steps, number=1)


def test_a_client_failure_on_reload_is_shown_and_does_not_crash_the_screen() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        def broken(*args: object, **kwargs: object) -> object:
            raise ScheduleNotFoundError("the project is gone")

        client.list_activities = broken  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await pilot.pause()
        assert status(screen) == "! the project is gone"
        assert screen.shown == [] and isinstance(app.screen, ActivityScreen)

    scenario(client, steps)


def test_a_reload_keeps_the_highlighted_activity() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("down", "down")
        await pilot.press("f5")
        await pilot.pause()
        row = screen.current()
        assert row is not None and row.activity_id == "A1240"

    scenario(world(), steps)


def test_c_and_the_filter_go_back_to_the_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity_screen, "PAGE", 1)

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("n", "n")
        await pilot.pause()
        assert screen.first == 2 and ids(screen) == ["A1240"]
        await pilot.press("c")  # one critical activity: the page it was on would be empty
        await pilot.pause()
        assert screen.first == 0 and ids(screen) == ["A1220"]
        await pilot.press("c", "n", "n")
        await pilot.pause()
        assert screen.first == 2
        await pilot.press("slash")
        await pilot.press("x")
        await pilot.pause()
        assert screen.first == 0 and 'filter "x"' in status(screen)

    scenario(world(), steps)


def test_the_last_page_is_the_one_that_ends_at_the_total_and_b_steps_back_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activity_screen, "PAGE", 2)

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("n")
        await pilot.pause()
        assert ids(screen) == ["A1240", "A2500"] and screen.first == 2
        await pilot.press("n")  # four activities, two a page: this is the last page
        await pilot.pause()
        assert "This is the last page." in status(screen)
        assert ids(screen) == ["A1240", "A2500"] and screen.first == 2

    scenario(world(), steps)


def test_b_goes_back_one_page_not_to_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity_screen, "PAGE", 1)

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("n", "n", "n")
        await pilot.pause()
        assert screen.first == 3 and ids(screen) == ["A2500"]
        await pilot.press("b")
        await pilot.pause()
        assert screen.first == 2 and ids(screen) == ["A1240"]

    scenario(world(), steps)


def test_an_activity_in_no_published_snapshot_still_shows_its_facts_and_says_so() -> None:
    client = FakeClient()
    client.add_schedule(
        "P123",
        "SIDE",
        [("2026-10-05T08:00", "Valid", [make_activity("S1", name="Lone activity")], [])],
    )

    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        text = screen_text(app)
        assert "S1  Lone activity  |  Snapshot 1" in text  # the facts are there
        assert "no published snapshot of SIDE has 'S1'" in text  # and why there is no trend
        assert "float trend:" not in text

    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(ActivityScreen(client, "P123", "SIDE", 1))
        await pilot.pause()
        assert isinstance(app.screen, ActivityScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def test_escape_in_an_empty_filter_box_closes_the_screen() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ActivityScreen) -> None:
        await pilot.press("slash")
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ActivityScreen)

    scenario(world(), steps)
