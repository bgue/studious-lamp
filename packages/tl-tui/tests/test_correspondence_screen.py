"""The correspondence screen on the fake client, driven with a pilot (P1-I5)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_correspondence
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_mod_correspondence.handlers.triage import ConfirmTriage
from tl_tui.app import TlApp
from tl_tui.widgets.correspondence_screen import CorrespondenceScreen


def world() -> FakeClient:
    client = FakeClient()
    seed_correspondence(client)
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, CorrespondenceScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f5")
        await settle(pilot)
        assert isinstance(app.screen, CorrespondenceScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def status(screen: CorrespondenceScreen) -> str:
    return str(screen.query_one("#log-status", Static).render())


def test_f5_lists_the_master_register_with_the_transmittal_among_the_items() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        text = screen_text(app)
        assert "P123 › Correspondence register › P123-COR-0001" in text
        assert [x.number for x in screen.lines] == [
            "P123-COR-0001", "P123-COR-0002", "P123-COR-0003", "P123-TRN-0001",
        ]  # fmt: skip
        assert "Isometrics [transmittal]" in text and "4 lines in the register" in text
        await pilot.press("escape")
        await settle(pilot)
        assert not isinstance(app.screen, CorrespondenceScreen)

    scenario(world(), steps)


def test_the_clocks_view_shows_the_reply_clock_with_fourteen_days_left() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("3")
        await settle(pilot)
        text = screen_text(app)
        assert "P123 › Response clocks › P123-COR-0003" in text
        assert "P123-COR-0003" in text and "2026-11-02" in text and "14 cal" in text
        assert "1 open clock" in text and "Item" in text
        assert "P123-COR-0003-C01" not in text and "P123-default@1" not in text
        app.display_mode.technical = True  # technical mode puts the clock key and calendar back
        screen.refresh_for_display_mode()
        await settle(pilot)
        text = screen_text(app)
        assert "P123-COR-0003-C01" in text and "calendar P123-default@1" in text

    scenario(world(), steps)


def test_the_inbox_lists_received_items_and_shows_the_suggestion() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("2")
        await settle(pilot)
        assert [x.number for x in screen.lines] == ["P123-COR-0001", "P123-COR-0002"]
        assert screen.query_one("#log-table", DataTable).row_count == 2
        assert "suggestion: Letter" in screen_text(app)
        assert "2 items awaiting triage" in screen_text(app)

    scenario(world(), steps)


def test_a_accepts_the_suggestion_with_the_expected_version() -> None:
    client = world()
    client.set_actions("ID-P123-COR-0001", ("ConfirmTriage", "Triage"))

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("2")
        await settle(pilot)
        assert "[a] Triage" in str(screen.query_one("#log-actions", Static).render())
        await pilot.press("a")
        await settle(pilot)
        [(name, cmd)] = client.correspondence_commands
        assert name == "ConfirmTriage" and isinstance(cmd, ConfirmTriage)
        assert (cmd.domain, cmd.subtype, cmd.stream_id) == ("general", "letter", "ID-P123-COR-0001")
        assert cmd.expected_version == 1 and cmd.actor == "user:kim" and cmd.source == "tui"
        assert cmd.scope == "project:P123"

    scenario(client, steps)


def test_a_outside_the_inbox_does_nothing() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("a")
        await settle(pilot)
        assert client.correspondence_commands == []  # the server offered nothing here

    scenario(client, steps)


def test_s_sweeps_and_a_refusal_is_shown_not_raised() -> None:
    client = world()
    client.is_corr_controller = False

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("s")
        await settle(pilot)
        assert status(screen).startswith("! ")
        assert "document_controller" in status(screen)
        client.is_corr_controller = True
        await pilot.press("s")
        await settle(pilot)
        assert "Sweep recorded 0 event(s)" in status(screen)
        assert [n for n, _ in client.correspondence_commands] == ["SweepClocks", "SweepClocks"]

    scenario(client, steps)


def test_tab_walks_the_views_and_m_adds_the_closed_clocks() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("tab", "tab")
        await settle(pilot)
        assert screen.mode == "clocks"
        before = client.calls.count("list_clocks")
        await pilot.press("m")
        await settle(pilot)
        assert client.calls.count("list_clocks") == before + 1 and "all clock" in status(screen)
        await pilot.press("tab")
        await settle(pilot)
        assert screen.mode == "register"

    scenario(client, steps)
