"""The derived-documents screen with a pilot (P1-I3-T07b). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from tl_mod_documents.errors import DerivedNotFoundError
from tl_tui.app import TlApp
from tl_tui.widgets.derived_documents import DerivedDocumentsScreen
from tl_tui.widgets.job_monitor import JobMonitorScreen
from tl_tui.widgets.publish_preview import PublishPreviewScreen

GOOD = "ISD-001@A/instrument-index"
BAD = "ISD-002@A/instrument-index"
BUSY = "ISD-003@A/instrument-index"


def world() -> FakeClient:
    client = FakeClient()
    client.seed_derivation("P123")
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, DerivedDocumentsScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f11")
        await pilot.pause()
        assert isinstance(app.screen, DerivedDocumentsScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def keys(screen: DerivedDocumentsScreen) -> list[str]:
    return [v.key for v in screen.shown]


def status(screen: DerivedDocumentsScreen) -> str:
    return str(screen.query_one("#dd-status", Static).render())


def test_f11_lists_the_derived_documents_and_describes_the_first() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        text = screen_text(app)
        assert "Derived documents of P123" in text
        assert keys(screen) == [GOOD, BAD, BUSY]
        assert screen.query_one("#dd-table", DataTable).row_count == 3
        assert "Valid" in text and "instrument-index@1.0.0" in text
        assert "3 of 3 derived documents" in text
        assert "passes:" in text and "report:" in text
        assert "instrument-index@1.0.0: valid" in text and "rows checked 3" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DerivedDocumentsScreen)

    scenario(world(), steps)


def test_moving_to_an_invalid_document_shows_its_issues_by_row_and_column() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("down")
        await pilot.pause()
        assert screen.detail is not None and screen.detail.key == BAD
        text = screen_text(app)
        assert "errors 2  warnings 1" in text
        assert "error   row 2 type: 'XX' is not one of CV, HV, PSV" in text
        assert "warning file: column 'note' is ignored" in text

    scenario(world(), steps)


def test_a_document_with_no_pass_says_so_and_has_no_report() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("down", "down")
        await pilot.pause()
        text = screen_text(app)
        assert "no pass yet" in text and "job JOB-" in text and "report:" not in text

    scenario(world(), steps)


def test_d_switches_between_the_report_and_the_diff() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("d")
        await pilot.pause()
        text = screen_text(app)
        assert screen.show_diff and "diff against the previous pass:" in text
        assert "added 1  removed 0  changed 1  unchanged 1" in text
        assert "~ 47-FV-1002: size_in 8 -> 6" in text
        assert client.calls.count("get_derived_diff") >= 1
        await pilot.press("down")  # the invalid one has no earlier pass: the refusal shows
        await pilot.pause()
        assert "there is no earlier data to compare with" in screen_text(app)
        await pilot.press("d")
        await pilot.pause()
        assert not screen.show_diff and "report:" in screen_text(app)

    scenario(client, steps)


def test_s_and_the_filter_box_narrow_the_list() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("s")
        await pilot.pause()
        assert screen.state == "Invalid" and keys(screen) == [BAD]
        assert "state Invalid" in status(screen)
        await pilot.press("s", "s", "s")
        await pilot.pause()
        assert screen.state is None and len(keys(screen)) == 3
        await pilot.press("slash")
        await pilot.press(*"isd-003")
        await pilot.pause()
        assert keys(screen) == [BUSY] and 'filter "isd-003"' in status(screen)
        await pilot.press("escape")
        await pilot.pause()
        assert screen.query_one("#dd-filter", Input).value == ""
        assert len(keys(screen)) == 3
        assert isinstance(app.screen, DerivedDocumentsScreen)  # the first Escape only cleared it

    scenario(world(), steps)


def test_x_queues_an_extraction_and_v_a_validation() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("x")
        await pilot.pause()
        assert client.calls.count("start_extraction") == 1
        assert f"Queued an extraction for {GOOD}" in status(screen)
        assert screen.shown[0].state == "Processing"  # read again after the command
        await pilot.press("v")  # a second job while one waits: the module refuses, the screen shows
        await pilot.pause()
        assert client.calls.count("validate_derived") == 1

    scenario(client, steps)


def test_a_refused_command_is_shown_and_the_screen_stays() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("down", "down")  # ISD-003 is being processed
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert status(screen).startswith("! ") and "is being processed" in status(screen)
        assert isinstance(app.screen, DerivedDocumentsScreen)

    scenario(client, steps)


def test_j_opens_the_job_monitor_and_p_the_publish_preview() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("j")
        await pilot.pause()
        assert isinstance(app.screen, JobMonitorScreen) and app.screen.derived == GOOD
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DerivedDocumentsScreen)
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, PublishPreviewScreen) and app.screen.derived == GOOD
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DerivedDocumentsScreen)

    scenario(world(), steps)


def test_the_letters_are_text_while_the_filter_box_has_focus() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        await pilot.press("slash")
        await pilot.press("x", "v", "d", "s", "j", "p")
        await pilot.pause()
        assert screen.text == "xvdsjp" and keys(screen) == []
        assert client.calls.count("start_extraction") == 0
        assert isinstance(app.screen, DerivedDocumentsScreen)

    scenario(client, steps)


def test_a_client_failure_is_shown_and_does_not_crash_the_screen() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DerivedDocumentsScreen) -> None:
        def broken(*args: object, **kwargs: object) -> list[object]:
            raise DerivedNotFoundError("the project is gone")

        client.list_derived_documents = broken  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await pilot.pause()
        assert status(screen) == "! the project is gone"
        assert isinstance(app.screen, DerivedDocumentsScreen)

    scenario(client, steps)
