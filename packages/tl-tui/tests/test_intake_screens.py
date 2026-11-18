"""The Intake log on `FakeClient` (V3-F4; I05), by pilot: rows, panel, state filter, refusal."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_forms import seed_intake
from helpers import run_pilot, screen_text, settle, static_of
from textual.pilot import Pilot
from tl_core.auth.errors import ForbiddenError
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.intake_text import intake_cells, intake_page, intake_summary
from tl_tui.widgets.intake_log import IntakeLogScreen

Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def run(app: TlApp, steps: Step, size: tuple[int, int] = (170, 44)) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


def make_app() -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_intake(client)
    return TlApp(client, scope=SCOPE, actor="user:ada"), client


def test_the_palette_lists_intake_and_its_action_exists() -> None:
    rows = {c.id: c for c in APP_COMMANDS}
    assert rows["intake"].action == "intake" and rows["intake"].keys == ""
    assert callable(getattr(TlApp, "action_intake", None))


def shown_at(size: tuple[int, int]) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_intake()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, IntakeLogScreen)
        seen["rows"] = [screen.row_cells(r)[0] for r in screen.shown]
        seen["summary"] = static_of(screen, "#log-status")
        seen["text"] = screen_text(app)

    app, _ = make_app()
    run(app, steps, size=size)
    return seen


def test_the_log_lists_the_items_the_client_gave_with_a_summary_at_both_widths() -> None:
    for size in ((80, 40), (170, 44)):
        seen = shown_at(size)
        assert seen["rows"] == ["00000001", "00000002", "00000003"]
        assert "3 intake items: 1 Pending, 1 Accepted, 1 Rejected" in seen["summary"]
        assert all(len(line) <= size[0] for line in seen["text"].splitlines())


def test_the_panel_shows_the_answers_of_a_pending_item_only() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_intake()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, IntakeLogScreen)
        seen["panels"] = [str(screen.panel_text(r)) for r in screen.shown]

    app, _ = make_app()
    run(app, steps)
    pending, accepted, rejected = seen["panels"]
    assert "Need a ladder" in pending and "Answers" in pending
    assert "Need a ladder" not in accepted and "Sam Smith" in accepted and "SubmitForm" in accepted
    assert "Rejected" in rejected and "spam" in rejected.lower()


def test_s_cycles_the_state_filter() -> None:
    seen: list[list[str]] = []

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_intake()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, IntakeLogScreen)
        for _ in range(4):
            await pilot.press("s")
            await settle(pilot)
            seen.append([r.state for r in screen.shown])

    app, _ = make_app()
    run(app, steps)
    assert seen == [["Pending"], ["Accepted"], ["Rejected"], ["Pending", "Accepted", "Rejected"]]


def test_a_refused_read_is_the_status_line_and_no_row() -> None:
    seen: dict[str, Any] = {}

    class Refusing(FakeClient):
        def list_intake_items(self, *a: Any, **k: Any) -> Any:
            raise ForbiddenError("forms.intake.review needs the controller access word")

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_intake()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, IntakeLogScreen)
        seen["rows"] = list(screen.shown)
        seen["status"] = static_of(screen, "#log-status")

    app = TlApp(Refusing(), scope=SCOPE, actor="user:uma")
    run(app, steps)
    assert seen["rows"] == [] and "access word" in seen["status"]


def test_the_pure_text_names_no_secret_and_no_list_holds_an_answer() -> None:
    from fakes_forms import intake_item

    pending = intake_item(1, answers=[{"q": "topic", "value": "Need a ladder"}])
    assert "Need a ladder" not in " ".join(intake_cells(pending.row))
    assert "01J0000000000000000000" not in " ".join(intake_cells(pending.row))
    page = intake_page(pending, technical=False)
    flat = str(page)
    assert "01J00000000000000000CODE01" not in flat  # the code id is technical only
    assert intake_summary({}, 0, 0, None) == "0 intake items"
