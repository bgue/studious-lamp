"""A refused cancel stays on the job monitor's status line, after the reload (T07a follow-up)."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot
from textual.pilot import Pilot
from textual.widgets import Static
from tl_mod_documents.derivation.derived import StartExtraction
from tl_mod_documents.errors import JobStateError
from tl_tui.app import TlApp
from tl_tui.widgets.job_monitor import JobMonitorScreen

GOOD = "ISD-001@A/instrument-index"


def test_a_failed_cancel_is_shown_and_the_reload_does_not_wipe_it() -> None:
    client = FakeClient()
    client.seed_derivation("P123")
    base: dict[str, Any] = {"actor": "user:kim", "source": "tui", "scope": "project:P123"}
    client.start_extraction(
        StartExtraction(**base, derived_id=client.get_derived_document("P123", GOOD).id)
    )

    def refuse(*args: object, **kwargs: object) -> None:
        raise JobStateError("a worker took the job while you looked")

    client.cancel_job = refuse  # type: ignore[method-assign,assignment]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(JobMonitorScreen(client, "P123", "user:kim"))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, JobMonitorScreen) and screen.shown[0].state == "queued"
        await pilot.press("c")
        await pilot.pause()
        text = str(screen.query_one("#jobs-status", Static).render())
        assert text == "! a worker took the job while you looked"
        assert isinstance(app.screen, JobMonitorScreen)

    run_pilot(app, go)
