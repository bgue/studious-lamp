"""The job monitor with a pilot (P1-I3-T07a). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_mod_documents.derivation.derived import StartExtraction
from tl_tui.app import TlApp
from tl_tui.widgets.job_monitor import JobMonitorScreen

GOOD = "ISD-001@A/instrument-index"
BASE: dict[str, Any] = {"actor": "user:kim", "source": "tui", "scope": "project:P123"}


def world() -> FakeClient:
    client = FakeClient()
    client.seed_derivation("P123")
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, JobMonitorScreen], Awaitable[None]],
    *,
    derived: str | None = GOOD,
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    closed: list[object] = []

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(
            JobMonitorScreen(client, "P123", "user:kim", derived=derived), closed.append
        )
        await pilot.pause()
        assert isinstance(app.screen, JobMonitorScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def states(screen: JobMonitorScreen) -> list[str]:
    return [j.state for j in screen.shown]


def status(screen: JobMonitorScreen) -> str:
    return str(screen.query_one("#jobs-status", Static).render())


def test_the_monitor_lists_the_jobs_of_one_derived_document() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: JobMonitorScreen) -> None:
        assert states(screen) == ["succeeded"]  # the first row of the table is ISD-001
        text = screen_text(app)
        assert f"Jobs of {GOOD} in P123" in text and "1 of 1 jobs" in text
        assert screen.query_one("#jobs-table", DataTable).row_count == 1
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, JobMonitorScreen)

    scenario(world(), steps)


def test_the_panel_describes_the_highlighted_job() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: JobMonitorScreen) -> None:
        screen.derived = None  # the whole project: running, failed, succeeded (newest first)
        screen.reload()
        await pilot.pause()
        screen.query_one("#jobs-table", DataTable).move_cursor(row=1)  # the failed one
        await pilot.pause()
        text = screen_text(app)
        assert "attempt 1 of 3" in text and "error timeout: extractor timed out" in text
        assert "by user:alice" in text

    scenario(world(), steps)


def test_s_narrows_by_state_and_a_second_pass_shows_all_again() -> None:
    client = world()
    client.start_extraction(
        StartExtraction(**BASE, derived_id=client.get_derived_document("P123", GOOD).id)
    )

    async def steps(pilot: Pilot[None], app: TlApp, screen: JobMonitorScreen) -> None:
        screen.derived = None  # the whole project, as when the monitor is opened without a document
        screen.reload()
        await pilot.pause()
        assert sorted(states(screen)) == ["failed", "queued", "running", "succeeded"]
        await pilot.press("s")
        await pilot.pause()
        assert screen.state == "failed" and states(screen) == ["failed"]
        assert "state failed" in status(screen)
        await pilot.press("s", "s", "s", "s")
        await pilot.pause()
        assert screen.state is None and len(states(screen)) == 4

    scenario(client, steps)


def test_c_cancels_a_queued_job_and_refuses_one_that_has_run() -> None:
    client = world()
    queued = client.start_extraction(
        StartExtraction(**BASE, derived_id=client.get_derived_document("P123", GOOD).id)
    )

    async def steps(pilot: Pilot[None], app: TlApp, screen: JobMonitorScreen) -> None:
        screen.derived = None
        screen.reload()
        await pilot.pause()
        keys = [j.id for j in screen.shown]
        assert keys[0] == queued.stream_id  # newest first
        await pilot.press("down")  # a job that has already run
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert "only a queued job can be cancelled" in status(screen)
        assert client.calls.count("cancel_job") == 0
        await pilot.press("up")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert client.calls.count("cancel_job") == 1
        assert "Cancelled" in status(screen)
        assert client.get_processing_job("P123", queued.stream_id).state == "cancelled"
        assert "cancelled" in states(screen)

    scenario(client, steps)


def test_the_screen_reads_again_on_its_own() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: JobMonitorScreen) -> None:
        before = client.calls.count("list_processing_jobs")
        await pilot.pause(2.6)  # the refresh interval is two seconds
        assert client.calls.count("list_processing_jobs") > before

    scenario(client, steps)


def test_a_client_failure_is_shown_and_does_not_crash_the_screen() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: JobMonitorScreen) -> None:
        def broken(*args: object, **kwargs: object) -> list[object]:
            raise client_error()

        from tl_mod_documents.errors import DerivedNotFoundError

        def client_error() -> Exception:
            return DerivedNotFoundError("the derived document is gone")

        client.list_processing_jobs = broken  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await pilot.pause()
        assert status(screen) == "! the derived document is gone"
        assert isinstance(app.screen, JobMonitorScreen)

    scenario(client, steps)
