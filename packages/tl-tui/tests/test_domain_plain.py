"""The domain screen in plain words (P1-UX-T04): Enter opens the record and Esc comes back to the
same row, a row the viewer cannot read opens as no record, the text has no technical tokens, the
technical mode restores the raw cells, and the RFI details are labelled."""

from __future__ import annotations

from fakes import SCOPE
from helpers import screen_text, settle
from test_domain_screen import scenario, world, world_today  # noqa: F401  (autouse fixture)
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, find_technical
from tl_tui.labels_load import load_labels
from tl_tui.widgets.domain_screen import DomainScreen
from tl_tui.widgets.record_screen import NO_RECORD, RecordScreen

RFI_TYPE = "correspondence.TechnicalItem"
COMMERCIAL_TYPE = "correspondence.CommercialItem"


def table_of(screen: DomainScreen) -> DataTable:  # type: ignore[type-arg]
    return screen.query_one("#log-table", DataTable)


async def open_and_return(
    pilot: Pilot[None], app: TlApp, screen: DomainScreen, row: int, record_id: str
) -> None:
    """Enter on the highlighted row opens ``record_id``; Esc returns to that same row."""
    assert table_of(screen).cursor_row == row
    await pilot.press("enter")
    await settle(pilot)
    assert isinstance(app.screen, RecordScreen)
    assert app.screen.record_id == record_id
    await pilot.press("escape")
    await settle(pilot)
    assert app.screen is screen
    assert table_of(screen).cursor_row == row


def test_enter_on_an_rfi_row_opens_the_record_and_escape_returns_to_the_same_row() -> None:
    client = world()
    lines = client.list_rfis("P123").lines
    second = lines[1]
    client.add_stored_record(second.id, second.number, RFI_TYPE, second.subject)

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("down")
        await settle(pilot)
        await open_and_return(pilot, app, screen, 1, second.id)

    scenario(client, steps)


def test_enter_on_a_commercial_row_opens_the_record_and_escape_returns_to_the_same_row() -> None:
    client = world()
    second = client.list_commercial("P123").lines[1]
    client.add_stored_record(second.id, second.number, COMMERCIAL_TYPE, second.number)

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2")
        await settle(pilot)
        await pilot.press("down")
        await settle(pilot)
        await open_and_return(pilot, app, screen, 1, second.id)

    scenario(client, steps)


def test_enter_on_an_evidence_row_opens_the_record_and_escape_returns_to_the_same_row() -> None:
    client = world()
    node = client.get_evidence_trail("P123", "P123-EW-0001").nodes[1]  # the RFI it came from
    client.add_stored_record(node.record_id, str(node.key), node.type, node.title)

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2", "t")
        await settle(pilot)
        assert screen.mode == "evidence"
        await pilot.press("down")
        await settle(pilot)
        await open_and_return(pilot, app, screen, 1, node.record_id)

    scenario(client, steps)


def test_a_row_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = world()  # the rows are listed, but no record is stored under their ids
    rfi_id = client.list_rfis("P123").lines[0].id

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert NO_RECORD in text
        assert rfi_id not in text
        await pilot.press("escape")
        await settle(pilot)
        assert app.screen is screen

    scenario(client, steps)


def test_plain_screen_text_has_no_technical_tokens() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        texts = [screen_text(app)]  # view 1, the first RFI in full
        await pilot.press("down")
        await settle(pilot)
        texts.append(screen_text(app))  # view 1, the overdue RFI in full
        await pilot.press("2")
        await settle(pilot)
        texts.append(screen_text(app))  # view 2, the first notice in full
        await pilot.press("t")
        await settle(pilot)
        texts.append(screen_text(app))  # view 3, the evidence trail and its panel
        for text in texts:
            assert find_technical(text, screen.labels) == []
            assert "early_warning" not in text
            assert "user:" not in text
            assert "ID-P123" not in text  # no record id in any view

    scenario(client, steps)


def test_technical_mode_restores_raw_cells_and_back() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        table = table_of(screen)
        plain_kind = str(table.get_row_at(0)[2])
        assert plain_kind != "rfi"
        app.display_mode.technical = True
        screen.refresh_for_display_mode()
        await settle(pilot)
        assert str(table.get_row_at(0)[2]) == "rfi"  # the raw subtype
        app.display_mode.technical = False
        screen.refresh_for_display_mode()
        await settle(pilot)
        assert str(table.get_row_at(0)[2]) == plain_kind

    scenario(client, steps)


def test_the_rfi_details_rows_are_labelled() -> None:
    client = world()
    labels = load_labels(client, "project:P123", (RFI_TYPE,))
    plain = DisplayMode()
    technical = DisplayMode()
    technical.technical = True

    def record(number: str) -> dict[str, object]:
        return {"type": RFI_TYPE, "key": number, "scope": SCOPE, "version": 1}

    answered_rows = details_for(client, "P123", record("P123-RFI-0001"), labels, plain)
    answered = {row.label: row.value for row in answered_rows}
    assert answered["Answer"] == "Re-route above the beam."
    assert answered["Escalated to"] == "P123-EW-0001 (Draft)"
    assert "Key" not in answered and "Schema hash" not in answered

    draft_rows = details_for(client, "P123", record("P123-RFI-0003"), labels, plain)
    draft = {row.label for row in draft_rows}
    assert "Answer" not in draft and "Escalated to" not in draft

    raw_rows = details_for(client, "P123", record("P123-RFI-0001"), labels, technical)
    assert "Key" in {row.label for row in raw_rows}
