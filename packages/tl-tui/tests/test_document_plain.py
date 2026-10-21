"""The document register: Enter opens the record, plain words, the technical lines (P1-UX-T01)."""

from __future__ import annotations

from fakes import SCOPE, FakeClient, valve_form_metadata
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input
from tl_schema.forms import EnumValue, FieldMeta
from tl_tui.app import TlApp
from tl_tui.display import find_technical
from tl_tui.widgets.document_register import DocumentRegisterScreen
from tl_tui.widgets.record_screen import RecordScreen


def world(*, unreadable: str | None = None) -> FakeClient:
    """The seeded documents, each readable as a record except ``unreadable`` (a view id)."""
    client = FakeClient()
    client.seed_documents("P123")
    for view in client.list_documents("P123", include_void=True):
        if view.id != unreadable:
            client.add_stored_record(view.id, view.number, "documents.Document", view.title)
    return client


def coded(client: FakeClient) -> None:
    """The document form's code lists, so that load_labels finds ISO and PIP as words."""
    fields = [
        FieldMeta.model_validate(
            {
                "path": path,
                "label": path,
                "description": path,
                "kind": "enum",
                "layer": "standard",
                "group": "document",
                "order": order,
                "enum_values": [EnumValue(code=code, label=label)],
            }
        )
        for order, (path, code, label) in enumerate(
            [("doc_type", "ISO", "Isometric"), ("discipline", "PIP", "Piping")], start=1
        )
    ]
    base = valve_form_metadata()
    client.metadata_by_type["documents.Document"] = base.model_copy(
        update={"core_fields": fields, "psets": []}
    )


def test_enter_opens_the_record_screen_and_escape_returns_to_the_same_row() -> None:
    client = world()
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        assert isinstance(register, DocumentRegisterScreen)
        table = register.query_one("#docs-table", DataTable)
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        assert "ISO-2000" in screen_text(app) and "Number" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is register
        assert table.cursor_row == 1

    run_pilot(app, go)


def test_enter_in_the_filter_box_does_not_open_a_record() -> None:
    client = world()
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        assert isinstance(register, DocumentRegisterScreen)
        await pilot.press("slash")
        await pilot.pause()
        assert isinstance(register.focused, Input)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DocumentRegisterScreen)
        assert isinstance(register.focused, DataTable)

    run_pilot(app, go)


def test_a_row_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = world(unreadable="DOC-ISO-2000")  # no stored record for this row
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        assert app.screen.view is None
        text = screen_text(app)
        assert "No record" in text
        assert "DOC-ISO-2000" not in text and "ISO-2000" not in text

    run_pilot(app, go)


def test_plain_text_has_labels_not_codes_or_class_names() -> None:
    client = world()
    coded(client)
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        assert isinstance(register, DocumentRegisterScreen)
        text = screen_text(app)
        row = [
            str(cell) for cell in register.query_one("#docs-table", DataTable).get_row("ISO-1234")
        ]
        assert row == [
            "ISO-1234",
            "Issued",
            "B(IFC)",
            "Isometric",
            "Piping",
            "Isometric, line 47-P-101",
        ]
        assert "state Issued  |  type Isometric  |  discipline Piping" in text
        assert "(Record) pin A, current B" in text  # the linked record's type, not core.Record
        assert "Registered" in text
        assert find_technical(text) == []
        assert "core.Record" not in text and "PIP" not in text and "type ISO" not in text

    run_pilot(app, go)


def test_technical_mode_adds_the_scheme_and_record_lines_and_back() -> None:
    client = world()
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        assert isinstance(register, DocumentRegisterScreen)
        assert "scheme alpha" not in screen_text(app)
        assert "record DOC-ISO-1234" not in screen_text(app)
        app.display_mode.technical = True
        register.refresh_for_display_mode()
        await pilot.pause()
        assert "scheme alpha" in screen_text(app) and "record DOC-ISO-1234" in screen_text(app)
        app.display_mode.technical = False
        register.refresh_for_display_mode()
        await pilot.pause()
        assert "scheme alpha" not in screen_text(app)
        assert "record DOC-ISO-1234" not in screen_text(app)

    run_pilot(app, go)
