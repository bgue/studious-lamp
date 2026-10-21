"""The schedule screen opens records on Enter, and says it in plain words (P1-UX-T06).

Enter on a schedule or a snapshot row opens the full record screen and Esc returns to the same
row; the Details of both record types are labelled rows; plain mode names a snapshot ``Snapshot 2``
and hides its key, the worker command and the actor ids, and technical mode shows them again.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.widgets.record_screen import RecordScreen
from tl_tui.widgets.schedule_screen import ScheduleScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    return client


def processing() -> FakeClient:
    """MAIN, with its newest snapshot still waiting for the worker (state Processing)."""
    client = world()
    detail = client._schedules[("P123", "MAIN")]  # pyright: ignore[reportPrivateUsage]
    newest = detail.snapshots[0].model_copy(update={"state": "Processing", "is_current": False})
    client._schedules[("P123", "MAIN")] = detail.model_copy(  # pyright: ignore[reportPrivateUsage]
        update={"snapshots": [newest, *detail.snapshots[1:]]}
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


def test_enter_on_a_schedule_row_opens_the_record_and_escape_returns_to_the_same_row() -> None:
    client = world()
    client.add_stored_record("SCHED-MAIN", "MAIN", "schedule.Schedule", "MAIN schedule")

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        assert app.screen.view is not None and "Snapshots" in app.screen.view.details
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ScheduleScreen)
        assert screen.query_one("#sc-schedules", DataTable).cursor_row == 0
        schedule = screen.current_schedule()
        assert schedule is not None and schedule.code == "MAIN"

    scenario(client, steps)


def test_enter_on_a_snapshot_row_opens_the_snapshot_record() -> None:
    client = world()
    client.add_stored_record("SNAP-MAIN-2", "MAIN#2", "schedule.ScheduleSnapshot", "MAIN#2")

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("tab", "enter")  # the snapshot table, its first row: snapshot 2
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        assert app.screen.view is not None
        details = app.screen.view.details
        assert "2 of MAIN" in details and "Requested by" in details and "Current" in details
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ScheduleScreen)
        snap = screen.current_snapshot()
        assert snap is not None and snap.number == 2

    scenario(client, steps)


def test_a_row_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = world()  # no record stored under the snapshot's id: the viewer cannot read it

    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        await pilot.press("tab", "enter")
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert "No record" in text
        assert "SNAP-MAIN-2" not in text and "MAIN#2" not in text

    scenario(client, steps)


def test_plain_text_names_the_snapshot_and_hides_the_command_and_the_actor_id() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        text = screen_text(app)
        assert "Snapshot 2  Processing" in text and "waiting to be processed" in text
        assert "requested by dev" in text
        for hidden in ("MAIN#2", "user:dev", "tl xer worker", "SNAP-MAIN-2"):
            assert hidden not in text, hidden
        assert find_technical(text, screen.labels) == []

    scenario(processing(), steps)


def test_technical_mode_restores_the_key_and_the_command_and_back() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: ScheduleScreen) -> None:
        assert "tl xer worker" not in screen_text(app)
        app.display_mode.technical = True
        screen.refresh_for_display_mode()
        await pilot.pause()
        text = screen_text(app)
        assert "MAIN#2  Processing" in text and "tl xer worker" in text
        app.display_mode.technical = False
        screen.refresh_for_display_mode()
        await pilot.pause()
        text = screen_text(app)
        assert "Snapshot 2  Processing" in text and "tl xer worker" not in text
        assert "MAIN#2" not in text

    scenario(processing(), steps)


def test_the_schedule_and_snapshot_renderers_give_labelled_rows() -> None:
    client = world()
    schedule = client.add_stored_record("SCHED-MAIN", "MAIN", "schedule.Schedule", "MAIN schedule")
    snapshot = client.add_stored_record("SNAP-MAIN-2", "MAIN#2", "schedule.ScheduleSnapshot", "x")
    plain = DisplayMode()
    technical = DisplayMode()
    technical.technical = True

    listed = details_for(client, "P123", schedule, Labels(), plain)
    values = {row.label: row.value for row in listed}
    assert values["Type"] == "Schedule" and values["Code"] == "MAIN"
    assert values["Kind"] == "Current" and values["Current snapshot"] == "2"
    assert values["Snapshots"] == "2" and values["Data date"] == "2026-10-12"
    assert "Owner" not in values  # the seeded schedule has no owner
    assert "Key" not in values and "Schema hash" not in values

    rows = details_for(client, "P123", snapshot, Labels(), plain)
    values = {row.label: row.value for row in rows}
    assert values["Snapshot"] == "2 of MAIN" and values["State"] == "Published"
    assert values["Current"] == "Yes" and values["Compares with"] == "snapshot 1"
    assert values["P6 version"] == "20.12" and values["File"] == "MAIN-2.xer"
    assert values["Requested by"] == "dev" and values["Published"] == "2026-10-12"
    assert "File hash" not in values and "Attempts" not in values and "Key" not in values

    rows = details_for(client, "P123", snapshot, Labels(), technical)
    shown = {row.label: row.value for row in rows}
    assert shown["File hash"] == "a" * 64 and shown["Attempts"] == "1"
    assert shown["Key"] == "MAIN#2"
