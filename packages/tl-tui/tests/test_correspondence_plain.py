"""Enter on the correspondence screen opens the record; plain text shows labels (P1-UX-T03)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_correspondence, seed_domains
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.widgets.correspondence_screen import CorrespondenceScreen
from tl_tui.widgets.record_screen import NO_RECORD, RecordScreen

PROJECT = "P123"
ACTOR = "user:kim"
ITEM = "correspondence.Correspondence"
CLOCK = "correspondence.ResponseClock"
Steps = Callable[[Pilot[None], TlApp, CorrespondenceScreen], Awaitable[None]]


def world(*, domains: bool = False) -> FakeClient:
    client = FakeClient()
    seed_correspondence(client)
    if domains:
        seed_domains(client)
    return client


def scenario(client: FakeClient, steps: Steps) -> None:
    app = TlApp(client, scope=SCOPE, actor=ACTOR)

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f5")
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, CorrespondenceScreen)
        await steps(pilot, app, screen)

    run_pilot(app, go)


async def open_row(pilot: Pilot[None], screen: CorrespondenceScreen, row: int) -> None:
    screen.query_one("#log-table", DataTable).move_cursor(row=row)
    await settle(pilot)
    await pilot.press("enter")
    await settle(pilot)


def headers(screen: CorrespondenceScreen) -> list[str]:
    table = screen.query_one("#log-table", DataTable)
    return [str(column.label) for column in table.columns.values()]


def assert_plain(text: str, labels: Labels) -> None:
    for token in ("general/letter", "P123-COR-0003-C01", "P123-default@1", "user:"):
        assert token not in text, token
    assert find_technical(text, labels) == []


def test_enter_on_a_register_row_opens_the_item_and_escape_returns_to_the_same_row() -> None:
    client = world(domains=True)
    client.add_stored_record("ID-P123-COR-0003", "P123-COR-0003", ITEM, "Re: Revised programme")

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await open_row(pilot, screen, 2)  # P123-COR-0003, the issued item with a domain
        record = app.screen
        assert isinstance(record, RecordScreen) and record.record_id == "ID-P123-COR-0003"
        assert record.view is not None and "Letter" in record.view.details
        await pilot.press("escape")
        await settle(pilot)
        assert app.screen is screen
        assert screen.query_one("#log-table", DataTable).cursor_row == 2

    scenario(client, steps)


def test_enter_in_the_inbox_and_in_the_clocks_view_opens_the_record_screen() -> None:
    client = world()
    client.add_stored_record("ID-P123-COR-0001", "P123-COR-0001", ITEM, "Revised programme")
    client.add_stored_record("CLK-1", "P123-COR-0003-C01", CLOCK, "Reply expected")

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("2")
        await settle(pilot)
        await open_row(pilot, screen, 0)
        record = app.screen
        assert isinstance(record, RecordScreen) and record.record_id == "ID-P123-COR-0001"
        await pilot.press("escape")
        await settle(pilot)
        assert app.screen is screen

        await pilot.press("3")
        await settle(pilot)
        await open_row(pilot, screen, 0)
        record = app.screen
        assert isinstance(record, RecordScreen) and record.record_id == "CLK-1"
        assert record.view is not None and "Days left" in record.view.details
        await pilot.press("escape")
        await settle(pilot)
        assert app.screen is screen

    scenario(client, steps)


def test_a_row_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = world()  # no stored record under the row's id: the viewer cannot read it

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await open_row(pilot, screen, 0)
        record = app.screen
        assert isinstance(record, RecordScreen) and record.view is None
        text = screen_text(app)
        assert NO_RECORD in text
        assert "ID-P123-COR-0001" not in text and "P123-COR-0001" not in text

    scenario(client, steps)


def test_plain_text_has_domain_labels_and_no_clock_key_or_calendar() -> None:
    client = world(domains=True)

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        # the register, with the issued item (and its clock) highlighted: the item panel too
        await pilot.press("1")
        await settle(pilot)
        screen.query_one("#log-table", DataTable).move_cursor(row=2)
        await settle(pilot)
        register = screen_text(app)
        assert "Letter" in register and "Transmittal" in register
        assert "running due 2026-11-02 left 14" in register
        assert_plain(register, screen.labels)

        await pilot.press("2")  # the triage inbox: the suggestion is a label too
        await settle(pilot)
        inbox = screen_text(app)
        assert "suggestion: Letter" in inbox
        assert_plain(inbox, screen.labels)

        await pilot.press("3")  # the clocks view: the item number leads, no calendar
        await settle(pilot)
        clocks = screen_text(app)
        assert "P123-COR-0003" in clocks and "Item" in headers(screen)
        assert_plain(clocks, screen.labels)

    scenario(client, steps)


def test_technical_mode_restores_the_clock_key_and_the_calendar_and_back() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: CorrespondenceScreen) -> None:
        await pilot.press("3")
        await settle(pilot)
        assert "P123-COR-0003-C01" not in screen_text(app) and "Item" in headers(screen)

        app.display_mode.technical = True
        screen.refresh_for_display_mode()
        await settle(pilot)
        text = screen_text(app)
        assert "P123-COR-0003-C01" in text and "calendar P123-default@1" in text
        assert "Clock" in headers(screen) and "Item" not in headers(screen)

        app.display_mode.technical = False
        screen.refresh_for_display_mode()
        await settle(pilot)
        text = screen_text(app)
        assert "P123-COR-0003-C01" not in text and "P123-default@1" not in text
        assert "Item" in headers(screen) and "Clock" not in headers(screen)

    scenario(client, steps)


def test_the_item_and_clock_renderers_give_labelled_rows() -> None:
    client = world()
    item_record = client.add_stored_record(
        "ID-P123-COR-0003", "P123-COR-0003", ITEM, "Re: Revised programme"
    )
    clock_record = client.add_stored_record("CLK-1", "P123-COR-0003-C01", CLOCK, "Reply expected")
    labels = Labels(subtypes={("general", "letter"): "Letter"})
    plain = DisplayMode()
    technical = DisplayMode()
    technical.technical = True

    item_plain = {
        r.label: r.value for r in details_for(client, PROJECT, item_record, labels, plain)
    }
    assert item_plain["Domain"] == "Letter" and item_plain["Number"] == "P123-COR-0003"
    assert item_plain["Medium"] == "Letter" and item_plain["Direction"] == "Out"
    assert "Received via" not in item_plain and "Key" not in item_plain
    item_tech = {r.label for r in details_for(client, PROJECT, item_record, labels, technical)}
    assert {"Received via", "External reference", "Key"} <= item_tech

    clock_plain = {
        r.label: r.value for r in details_for(client, PROJECT, clock_record, labels, plain)
    }
    for label in ("Type", "Item", "Label", "Kind", "State", "Started", "Due", "Days left"):
        assert label in clock_plain, label
    assert clock_plain["Item"] == "P123-COR-0003" and clock_plain["Length"] == "14 calendar days"
    assert "Calendar" not in clock_plain and "Clock key" not in clock_plain
    clock_tech = {
        r.label: r.value for r in details_for(client, PROJECT, clock_record, labels, technical)
    }
    assert clock_tech["Calendar"] == "P123-default@1"
    assert clock_tech["Clock key"] == "P123-COR-0003-C01"
