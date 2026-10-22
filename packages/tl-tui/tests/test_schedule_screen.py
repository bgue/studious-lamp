"""The schedule screen with a pilot (P1-I4-T09a1). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text, settle
from textual.app import ComposeResult
from textual.pilot import Pilot
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.lookahead import LookAhead, LookAheadRow
from tl_mod_schedule.resolver import OrphanedLink
from tl_mod_schedule.testing import make_activity
from tl_tui.app import TlApp
from tl_tui.widgets.schedule_screen import ScheduleScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    client.put_look_ahead(
        "P123",
        "MAIN",
        LookAhead(
            "MAIN#2", 2, "2026-10-12T08:00", "2026-10-12", "2026-11-09", 4,
            (LookAheadRow(
                "A1230", "Install pipe rack supports", "P > W", "in_progress", "in_progress",
                "2026-10-05T08:00", "2026-10-23T16:00", 4.0, False, 40.0,
            ),),
            {"in_progress": 1, "critical": 0, "total": 1},
        ),
    )  # fmt: skip
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, ScheduleScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f12")
        await settle(pilot)
        assert isinstance(app.screen, ScheduleScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def status(screen: ScheduleScreen) -> str:
    return str(screen.query_one("#log-status", Static).render())


def test_f12_lists_the_schedules_and_the_snapshots_and_describes_the_current_one() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        text = screen_text(app)
        assert "P123 › Schedules › MAIN: MAIN schedule" in text and "1 of 1 schedules" in status(
            screen
        )
        assert [v.code for v in screen.shown] == ["MAIN"]
        assert screen.query_one("#log-table", DataTable).row_count == 1
        assert screen.query_one("#sc-snapshots", DataTable).row_count == 2
        assert "2*" in text and "Published (current)" in text and "Superseded" in text
        assert "MAIN schedule" in text and "2026-10-12" in text
        assert "Snapshot 2  Published (current)" in text and "compares with snapshot 1" in text
        assert screen.detail is not None and screen.detail.code == "MAIN"
        snap = screen.current_snapshot()
        assert snap is not None and snap.number == 2
        await pilot.press("escape")
        await settle(pilot)
        assert not isinstance(app.screen, ScheduleScreen)

    scenario(world(), steps)


def test_moving_to_the_older_snapshot_describes_it() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("tab", "down")
        await settle(pilot)
        snap = screen.current_snapshot()
        assert snap is not None and snap.number == 1
        text = screen_text(app)
        assert "Snapshot 1  Superseded" in text and "(current)" not in text.split("Snapshot 1")[1]
        assert "compares with snapshot" not in text  # the first snapshot has none

    scenario(world(), steps)


def test_l_shows_the_look_ahead_and_o_the_orphaned_links_and_each_goes_back() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("l")
        await settle(pilot)
        text = screen_text(app)
        assert screen.panel == "look_ahead"
        assert "look-ahead Snapshot 2: 2026-10-12 to 2026-11-09 (4 weeks)" in text
        assert "A1230  In progress" in text
        await pilot.press("l")
        await settle(pilot)
        assert screen.panel == "snapshot" and "look-ahead MAIN#2:" not in screen_text(app)
        await pilot.press("o")
        await settle(pilot)
        assert screen.panel == "orphans" and "no orphaned links" in screen_text(app)
        client.put_orphans("P123", "MAIN", [OrphanedLink("LNK1", "REC1", "A1990", 1, "gone")])
        await pilot.press("f5")
        await settle(pilot)
        text = screen_text(app)
        assert "orphaned links: 1" in text and "A1990  last seen in snapshot 1" in text
        await pilot.press("o")
        await settle(pilot)
        assert screen.panel == "snapshot"

    scenario(client, steps)


def test_the_panel_warns_while_the_links_are_being_checked() -> None:
    client = world()
    detail = client._schedules[("P123", "MAIN")]  # pyright: ignore[reportPrivateUsage]
    client._schedules[("P123", "MAIN")] = detail.model_copy(  # pyright: ignore[reportPrivateUsage]
        update={"links_being_checked": True}
    )

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        text = " ".join(screen_text(app).split())
        assert "links to activities are being checked" in text

    scenario(client, steps)


class Probe(ModalScreen[None]):
    """Stands in for the comparison and the activity screens: records how it was opened."""

    BINDINGS = [("escape", "close", "Close")]  # noqa: RUF012
    opened: list[tuple[object, ...]] = []  # noqa: RUF012

    def __init__(self, *args: object) -> None:
        super().__init__()
        Probe.opened.append(args)

    def compose(self) -> ComposeResult:
        yield from ()

    def action_close(self) -> None:
        self.dismiss(None)


def test_c_opens_the_comparison_and_a_the_activities_of_the_highlighted_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tl_tui.widgets.schedule_screen as module

    Probe.opened = []
    monkeypatch.setattr(module, "CompareScreen", Probe)
    monkeypatch.setattr(module, "ActivityScreen", Probe)
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("c")
        await settle(pilot)
        assert isinstance(app.screen, Probe)
        assert Probe.opened[0] == (client, "P123", "MAIN", 2)
        await pilot.press("escape")
        await settle(pilot)
        await pilot.press("a")  # the current snapshot
        await settle(pilot)
        assert Probe.opened[1] == (client, "P123", "MAIN", 2)
        await pilot.press("escape")
        await settle(pilot)
        await pilot.press("tab", "down", "a")  # the older snapshot
        await settle(pilot)
        assert isinstance(app.screen, Probe)
        assert Probe.opened[2] == (client, "P123", "MAIN", 1)
        await pilot.press("escape")
        await settle(pilot)
        await pilot.press("c")  # the older snapshot has nothing before it: still asked for
        await settle(pilot)
        assert Probe.opened[3] == (client, "P123", "MAIN", 1)
        await pilot.press("escape")
        await settle(pilot)
        assert isinstance(app.screen, ScheduleScreen)

    scenario(client, steps)


def test_p_publishes_the_highlighted_snapshot_and_reads_again() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("tab", "down", "p")
        await settle(pilot)
        [cmd] = client.schedule_commands
        assert isinstance(cmd, PublishScheduleSnapshot)
        assert (cmd.snapshot_id, cmd.scope, cmd.actor, cmd.source) == (
            "SNAP-MAIN-1",
            "project:P123",
            "user:kim",
            "tui",
        )
        assert status(screen) == "Published MAIN#1."

    scenario(client, steps)


def test_a_person_who_may_not_publish_sees_the_refusal_and_nothing_is_sent() -> None:
    client = world()
    client.is_controller = False

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("p")
        await settle(pilot)
        assert status(screen).startswith("! ") and "document_controller or admin" in status(screen)
        assert client.schedule_commands == []
        assert isinstance(app.screen, ScheduleScreen)

    scenario(client, steps)


def test_the_filter_box_narrows_the_schedules_and_the_letters_are_text_there() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("slash")
        await pilot.press(*"clop")  # c, l, o and p are keys of the screen: here they are text
        await settle(pilot)
        assert screen.filter_text == "clop" and screen.shown == []
        assert "0 of 1 schedules" in status(screen) and 'filter "clop"' in status(screen)
        assert "No schedule matches." in screen_text(app)
        assert client.schedule_commands == [] and screen.panel == "snapshot"
        await pilot.press("escape")  # the first Escape clears the box
        await settle(pilot)
        assert screen.query_one("#log-filter", Input).value == ""
        assert [v.code for v in screen.shown] == ["MAIN"]
        assert isinstance(app.screen, ScheduleScreen)

    scenario(client, steps)


def test_a_client_failure_is_shown_and_does_not_crash_the_screen() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        def broken(*args: object, **kwargs: object) -> list[object]:
            raise ScheduleNotFoundError("the project is gone")

        client.list_schedules = broken  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await settle(pilot)
        assert status(screen) == "! the project is gone"
        assert isinstance(app.screen, ScheduleScreen)

    scenario(client, steps)


def test_a_project_with_no_schedule_says_so_and_offers_no_action() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        assert "0 of 0 schedules" in status(screen) and "No schedule matches." in screen_text(app)
        assert str(screen.query_one("#log-actions", Static).render()) == ""  # nothing to act on
        for key in ("c", "a", "p"):  # so the keys do nothing
            await pilot.press(key)
            await settle(pilot)
            assert "0 of 0 schedules" in status(screen), key
        assert isinstance(app.screen, ScheduleScreen)

    scenario(FakeClient(), steps)


def test_a_schedule_with_no_snapshot_answers_each_key_with_a_message() -> None:
    client = FakeClient()
    client.add_schedule("P123", "EMPTY", [])

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        assert "[c] Compare" in str(screen.query_one("#log-actions", Static).render())
        for key in ("c", "a", "p"):  # each key says it on its own
            screen.query_one("#log-status", Static).update("")
            await pilot.press(key)
            await settle(pilot)
            assert status(screen) == "! No snapshot is highlighted.", key
        assert client.schedule_commands == []
        assert isinstance(app.screen, ScheduleScreen)

    scenario(client, steps)


def two_schedules() -> FakeClient:
    """MAIN (two snapshots) and SIDE (one Published and one Invalid snapshot), whose titles do
    not hold their codes."""
    client = world()
    client.add_schedule(
        "P123",
        "SIDE",
        [
            ("2026-09-01T08:00", "Published", [make_activity("S1")], []),
            ("2026-09-08T08:00", "Invalid", [], []),
        ],
    )
    for code, title in (("MAIN", "Process unit"), ("SIDE", "Turnaround plan")):
        found = client._schedules[("P123", code)]  # pyright: ignore[reportPrivateUsage]
        client._schedules[("P123", code)] = found.model_copy(  # pyright: ignore[reportPrivateUsage]
            update={"title": title}
        )
    return client


def test_the_filter_looks_at_the_code_and_at_the_title() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        assert [v.code for v in screen.shown] == ["MAIN", "SIDE"]
        await pilot.press("slash")
        await pilot.press(*"turnaround")  # only SIDE's title holds it
        await settle(pilot)
        assert [v.code for v in screen.shown] == ["SIDE"]
        await pilot.press("ctrl+u")
        await pilot.press(*"main")  # only MAIN's code holds it
        await settle(pilot)
        assert [v.code for v in screen.shown] == ["MAIN"]

    scenario(two_schedules(), steps)


def test_moving_between_schedules_loads_their_snapshots_and_a_reload_keeps_the_place() -> None:
    client = two_schedules()

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        assert screen.query_one("#sc-snapshots", DataTable).row_count == 2
        await pilot.press("down")  # SIDE
        await settle(pilot)
        schedule = screen.current_schedule()
        assert schedule is not None and schedule.code == "SIDE"
        assert screen.detail is not None and screen.detail.code == "SIDE"
        assert "Invalid" in screen_text(app)
        await pilot.press("tab", "down")  # SIDE's older snapshot
        await settle(pilot)
        snap = screen.current_snapshot()
        assert snap is not None and snap.number == 1
        await pilot.press("f5")
        await settle(pilot)
        schedule, snap = screen.current_schedule(), screen.current_snapshot()
        assert schedule is not None and schedule.code == "SIDE"  # not back on MAIN
        assert snap is not None and snap.number == 1  # not back on the newest

    scenario(client, steps)


def test_the_look_ahead_is_asked_for_the_highlighted_snapshot_and_a_refusal_is_in_the_panel() -> (
    None
):
    client = two_schedules()
    asked: list[int | None] = []
    real = client.get_look_ahead

    def spy(project: str, code: str, *, snapshot: int | None = None, weeks: int = 4) -> LookAhead:
        asked.append(snapshot)
        return real(project, code, snapshot=snapshot, weeks=weeks)

    client.get_look_ahead = spy  # type: ignore[method-assign]

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("tab", "down", "l")  # MAIN#1
        await settle(pilot)
        assert asked == [1]
        await pilot.press("shift+tab", "down")  # SIDE, whose newest snapshot is Invalid
        await settle(pilot)
        text = " ".join(screen_text(app).split())
        assert asked[-1] == 2 and "has no activities to read" in text
        assert isinstance(app.screen, ScheduleScreen)

    scenario(client, steps)


def test_publishing_reads_again_and_sends_the_project_it_was_opened_for() -> None:
    client = FakeClient()
    client.seed_schedule("ABC")
    reads: list[str] = []
    real = client.list_schedules

    def spy(project: str) -> list[object]:
        reads.append(project)
        return real(project)  # type: ignore[return-value]

    client.list_schedules = spy  # type: ignore[method-assign,assignment]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(ScheduleScreen(client, "ABC", "user:kim"))
        await settle(pilot)
        assert reads == ["ABC"]
        await pilot.press("p")
        await settle(pilot)
        [cmd] = client.schedule_commands
        assert isinstance(cmd, PublishScheduleSnapshot) and cmd.scope == "project:ABC"
        assert reads == ["ABC", "ABC"]  # read again after the command

    run_pilot(app, go)


def test_escape_in_an_empty_filter_box_closes_the_screen() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("slash")
        await pilot.press("escape")
        await settle(pilot)
        assert not isinstance(app.screen, ScheduleScreen)

    scenario(world(), steps)
