"""The comparison screen with a pilot (P1-I4-T09a2). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Static
from tl_mod_schedule.errors import SnapshotNotFoundError
from tl_mod_schedule.testing import make_activity
from tl_tui.app import TlApp
from tl_tui.widgets.compare_screen import CompareScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, CompareScreen], Awaitable[None]],
    *,
    new: int = 2,
    old: int | None = None,
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(CompareScreen(client, "P123", "MAIN", new, old))
        await pilot.pause()
        assert isinstance(app.screen, CompareScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def status(screen: CompareScreen) -> str:
    return str(screen.query_one("#cp-status", Static).render())


def body(screen: CompareScreen) -> str:
    return str(screen.query_one("#cp-body", Static).render())


def test_it_opens_on_the_first_section_with_the_header_and_every_count() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        text = screen_text(app)
        assert "Comparison of MAIN#2" in text
        assert "MAIN#2 (2026-10-12) against MAIN#1 (2026-10-05)" in text
        assert "data date +7d  |  latest finish 2026-10-16 to 2026-10-23 (+7d)" in text
        assert (
            "[Added 1]  Removed 1  Date shifts 1  Float 1  Logic 1  Progress 0  Durations 0  "
            "Critical 0" in text
        )
        assert body(screen) == "Added:\n+ A2500  Weld inspection hold point  (P > W)"
        assert status(screen) == "section 1 of 8"
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CompareScreen)

    scenario(world(), steps)


def test_right_and_left_walk_through_the_sections_and_wrap_around() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        await pilot.press("right")
        await pilot.pause()
        assert body(screen) == "Removed:\n- A1990  Temporary fencing  (P > W)"
        assert "Added 1  [Removed 1]" in screen_text(app) and status(screen) == "section 2 of 8"
        await pilot.press("n", "n")
        await pilot.pause()
        assert body(screen) == "Float:\n~ A1230  float 9d to 4d  ERODED  Install pipe rack supports"
        await pilot.press("b")
        await pilot.pause()
        assert body(screen).startswith("Date shifts:\n~ A1230  start -  finish +7d  largest 7d")
        await pilot.press("left", "left", "left")  # added, then wraps to the last section
        await pilot.pause()
        assert body(screen) == "Critical:\nnone" and status(screen) == "section 8 of 8"
        await pilot.press("right")
        await pilot.pause()
        assert body(screen).startswith("Added:") and status(screen) == "section 1 of 8"

    scenario(world(), steps)


def test_a_named_older_snapshot_is_compared_and_a_reload_reads_again() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        assert "MAIN#2 (2026-10-12) against MAIN#1 (2026-10-05)" in screen_text(app)
        await pilot.press("f5")
        await pilot.pause()
        assert screen.comparison is not None and screen.comparison.old.number == 1

    scenario(client, steps, new=2, old=1)


def test_the_first_snapshot_has_nothing_to_compare_with_and_the_refusal_is_shown() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        assert screen.comparison is None
        assert "has no earlier snapshot to compare" in body(screen)
        assert status(screen).startswith("! ") and "no earlier snapshot" in status(screen)
        await pilot.press("right", "left")  # the keys do nothing and nothing breaks
        await pilot.pause()
        assert isinstance(app.screen, CompareScreen)

    scenario(world(), steps, new=1)


def test_a_client_failure_on_reload_is_shown_and_does_not_crash_the_screen() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        def broken(*args: object, **kwargs: object) -> object:
            raise SnapshotNotFoundError("schedule MAIN has no snapshot 2")

        client.compare_snapshots = broken  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await pilot.pause()
        assert status(screen) == "! schedule MAIN has no snapshot 2"
        assert body(screen) == "schedule MAIN has no snapshot 2"
        assert isinstance(app.screen, CompareScreen)

    scenario(client, steps)


def three_snapshots() -> FakeClient:
    """Snapshot 1 has A1, snapshot 2 adds A2, snapshot 3 adds A3."""
    client = FakeClient()
    one = [make_activity("A1", seq=1)]
    two = [*one, make_activity("A2", seq=2)]
    three = [*two, make_activity("A3", seq=3)]
    client.add_schedule(
        "P123",
        "MAIN",
        [
            ("2026-10-05T08:00", "Superseded", one, []),
            ("2026-10-12T08:00", "Superseded", two, []),
            ("2026-10-19T08:00", "Published", three, []),
        ],
    )
    return client


def test_the_older_snapshot_it_was_given_is_the_one_compared_with() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        assert "MAIN#3 (2026-10-19) against MAIN#1 (2026-10-05)" in screen_text(app)
        assert "Added 2" in screen_text(app)
        assert body(screen).splitlines()[1:] == [
            "+ A2  Activity A2  (P > W)",
            "+ A3  Activity A3  (P > W)",
        ]

    scenario(three_snapshots(), steps, new=3, old=1)


def test_without_an_older_snapshot_the_one_before_is_used() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        assert "MAIN#3 (2026-10-19) against MAIN#2 (2026-10-12)" in screen_text(app)
        assert body(screen).splitlines()[1:] == ["+ A3  Activity A3  (P > W)"]

    scenario(three_snapshots(), steps, new=3)


def test_a_long_list_is_cut_and_the_screen_says_the_counts_are_still_exact() -> None:
    client = FakeClient()
    base = [make_activity("A0", seq=1)]
    many = [*base, *(make_activity(f"N{n:03}", seq=n + 2) for n in range(205))]
    client.add_schedule(
        "P123",
        "MAIN",
        [("2026-10-05T08:00", "Superseded", base, []), ("2026-10-12T08:00", "Published", many, [])],
    )

    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        assert "Added 205" in screen_text(app)  # the full count
        lines = body(screen).splitlines()
        assert len(lines) == 1 + 200 + 1 and lines[-1] == "... 5 more not shown"
        assert status(screen) == "section 1 of 8  (the lists were cut; the counts are exact)"

    scenario(client, steps)


def test_after_a_failed_reload_the_keys_leave_the_error_in_place() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: CompareScreen) -> None:
        def broken(*args: object, **kwargs: object) -> object:
            raise SnapshotNotFoundError("schedule MAIN has no snapshot 2")

        client.compare_snapshots = broken  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await pilot.pause()
        assert screen.comparison is None
        await pilot.press("right", "right")
        await pilot.pause()
        assert body(screen) == "schedule MAIN has no snapshot 2"
        assert status(screen) == "! schedule MAIN has no snapshot 2"

    scenario(client, steps)
