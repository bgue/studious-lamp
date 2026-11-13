"""The weekly cycle, steps 4 and 5 (P2-I5-T06b): the commitments and the progress screens, their
keys and their commands, through the Textual pilot over ``FakeClient``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_iwp import seed_iwp
from fakes_week import PROJECT, seed_week
from helpers import run_pilot, settle, static_of
from textual.pilot import Pilot
from textual.widgets import Input
from tl_api.routes.awp_progress import IwpProgress, ProgressItem
from tl_mod_awp.commands import CloseWeek, CommitIwpToWeek, RecordWeekOutcome, StartIwpWork
from tl_tui.app import TlApp
from tl_tui.weekly_text import commitment_summary, progress_summary
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.weekly_screen import CommitmentsScreen, ProgressScreen

SIZE = (170, 44)
Step = Callable[[Pilot[Any]], Awaitable[None]]


def make_app() -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_week(client)
    seed_iwp(client)
    client.seed_schedule(PROJECT)
    return TlApp(client, scope=SCOPE, actor="user:kim"), client


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot)

    run_pilot(app, go, size=SIZE)


async def press(pilot: Pilot[Any], *keys: str) -> None:
    for key in keys:
        await pilot.press(key)
        await settle(pilot)


def status_of(app: TlApp) -> str:
    return static_of(app.screen, "#log-status")


# --- step 4: the commitments ---------------------------------------------------------------


def test_four_shows_the_committed_plan_and_its_commitments() -> None:
    app, client = make_app()
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "4")
        seen["screen"] = app.screen
        seen["rows"] = list(app.screen.shown)  # type: ignore[attr-defined]
        seen["status"] = status_of(app)

    run(app, steps)
    assert isinstance(seen["screen"], CommitmentsScreen)
    assert len(seen["rows"]) == 2, "the plan's row, then its one commitment"
    assert seen["rows"][0].commitment is None
    assert seen["rows"][0].plan.week == "2026-W45"
    plan = client.get_weekly_plan(PROJECT, "2026-W45")
    assert seen["status"] == commitment_summary(plan)


def test_c_commits_an_issued_iwp_with_the_plan_version() -> None:
    app, client = make_app()
    issued = client.list_iwps(PROJECT, state="Issued")[0]

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "4", "c")
        app.screen.query_one("#field-hours", Input).value = "16"
        await press(pilot, "ctrl+s")

    run(app, steps)
    assert len(client.sent_commands) == 1
    name, cmd = client.sent_commands[0]
    assert name == "CommitIwpToWeek"
    assert isinstance(cmd, CommitIwpToWeek)
    assert cmd.plan_id == "PLAN-2"
    assert cmd.iwp_id == issued.id
    assert cmd.expected_version == 1
    assert cmd.actor == "user:kim"


def test_m_asks_a_reason_and_sends_the_outcome_missed() -> None:
    app, client = make_app()

    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "4", "down", "m")
        seen["asked"] = isinstance(app.screen, ActionFormScreen)
        await press(pilot, "ctrl+s")

    run(app, steps)
    assert seen["asked"], "m did not ask the reason"
    assert len(client.sent_commands) == 1
    name, cmd = client.sent_commands[0]
    assert name == "RecordWeekOutcome"
    assert isinstance(cmd, RecordWeekOutcome)
    assert cmd.outcome == "missed"
    assert cmd.miss_reason == "Weather"  # the first of the code list, as its key
    assert cmd.iwp_id == "IWP-0001"
    assert cmd.expected_version == 1


def test_z_asks_to_confirm_then_sends_close_week() -> None:
    app, client = make_app()
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "4", "z")
        seen["asked"] = isinstance(app.screen, ActionFormScreen)
        seen["sent_before"] = len(client.sent_commands)
        await press(pilot, "y")

    run(app, steps)
    assert seen["asked"], "z did not ask to confirm"
    assert seen["sent_before"] == 0, "the close was sent before the confirm"
    assert len(client.sent_commands) == 1
    name, cmd = client.sent_commands[0]
    assert name == "CloseWeek"
    assert isinstance(cmd, CloseWeek)
    assert cmd.plan_id == "PLAN-2"
    assert cmd.expected_version == 1


# --- step 5: the progress ------------------------------------------------------------------


def test_five_shows_the_kpi_line_and_reads_progress_for_the_highlighted_row_only() -> None:
    app, client = make_app()
    field = client.list_iwps(PROJECT, state="Issued")[0]
    client.load_progress(
        PROJECT,
        {
            field.number: IwpProgress(
                number=field.number,
                pct=Decimal("40.0"),
                edition="2026",
                items=[ProgressItem(key="10.0", pct=Decimal("40"), steps=["Fit"], hours=None)],
                notes=[],
            )
        },
    )
    calls: list[str] = []
    read = client.get_iwp_progress

    def counted(project: str, number: str) -> IwpProgress:
        calls.append(number)
        return read(project, number)

    client.get_iwp_progress = counted  # type: ignore[method-assign]
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "5")
        seen["screen"] = app.screen
        seen["status"] = status_of(app)

    run(app, steps)
    assert isinstance(seen["screen"], ProgressScreen)
    assert seen["status"] == progress_summary(client.list_kpis(PROJECT))
    assert "PPC 66.7%" in seen["status"]
    assert calls == [field.number], "one earned-progress read, for the highlighted row only"


def test_w_on_an_issued_row_sends_start_work_with_the_record_version() -> None:
    app, client = make_app()
    issued = client.list_iwps(PROJECT, state="Issued")[0]
    client.add_stored_record(f"rec-{issued.number}", issued.number, "awp.IWP", issued.title)

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "5", "w")

    run(app, steps)
    assert len(client.sent_commands) == 1
    name, cmd = client.sent_commands[0]
    assert name == "StartIwpWork"
    assert isinstance(cmd, StartIwpWork)
    assert cmd.iwp_id == issued.id
    assert cmd.expected_version == 1
