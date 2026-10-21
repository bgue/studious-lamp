"""The record grid in plain words and in technical mode (P1-UX-T08c).

Plain mode shows a record type as its label and a property column under the property's label;
technical mode keeps the stored type and the dotted path. The text export and the stored column
keys do not change with the mode, and the grid redraws when the mode switches.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.display import DisplayMode
from tl_tui.widgets.column_chooser import ColumnChooser
from tl_tui.widgets.grid import (
    CORE_COLUMNS,
    GridColumn,
    RecordGrid,
    available_columns,
    cell_text,
    raw_text,
    to_tsv,
)

KEY = GridColumn("key", "Key", 12)
TYPE = GridColumn("type", "Type", 20)


class Host(App[None]):
    """A bare app with the grid; it carries a display mode the way TlApp does (plain at start)."""

    def __init__(self, client: FakeClient, **grid_args: Any) -> None:
        super().__init__()
        self.client = client
        self.grid_args = grid_args
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield RecordGrid(self.client, SCOPE, id="grid", **self.grid_args)


def _size_column(client: FakeClient) -> GridColumn:
    columns = available_columns(client.form_metadata(SCOPE, "core.Record"))
    return next(c for c in columns if c.key == "psets.valve_data.size_in")


def test_plain_type_cell_is_the_label_and_technical_the_raw_type() -> None:
    record = {"type": "engineering.ControlValve"}
    assert cell_text(record, TYPE, technical=False) == "Control valve"
    assert cell_text(record, TYPE) == "engineering.ControlValve"
    host = Host(FakeClient.with_valve_example(), columns=[KEY, TYPE])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        assert "Record" in screen_text(host) and "core.Record" not in screen_text(host)
        host.display_mode.technical = True
        grid.refresh_for_display_mode()
        await pilot.pause()
        assert "core.Record" in screen_text(host)

    run_pilot(host, scenario)


def test_property_header_is_the_label_in_plain_and_the_path_in_technical() -> None:
    client = FakeClient.with_valve_example()
    size = _size_column(client)
    assert size.label == "valve_data.size_in" and size.plain_label == "size_in"
    host = Host(client, columns=[KEY, size])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        header = screen_text(host).splitlines()[0]
        assert "size_in" in header and "valve_data.size_in" not in header
        host.display_mode.technical = True
        grid.refresh_for_display_mode()
        await pilot.pause()
        # the technical header is cut to the 14-column width, so its visible part is checked
        assert "valve_data.si" in screen_text(host).splitlines()[0]

    run_pilot(host, scenario)


def test_a_property_without_a_label_gets_the_humanized_leaf_in_plain() -> None:
    client = FakeClient.with_valve_example()
    meta = client.form_metadata(SCOPE, "core.Record")
    group = meta.psets[0]
    unlabeled = group.fields[0].model_copy(update={"label": ""})
    group_copy = group.model_copy(update={"fields": [unlabeled, *group.fields[1:]]})
    bare = meta.model_copy(update={"psets": [group_copy, *meta.psets[1:]]})
    column = next(c for c in available_columns(bare) if c.key == "psets.valve_data.size_in")
    assert column.plain_label == "Size in" and column.label == "valve_data.size_in"


def test_the_column_chooser_lists_labels_in_plain_and_returns_the_original_columns() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one(RecordGrid)
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ColumnChooser)
        text = screen_text(app)
        assert "size_in" in text and "valve_data.size_in" not in text
        await pilot.press(*["down"] * len(CORE_COLUMNS), "space", "ctrl+s")
        await pilot.pause()
        added = grid.columns[-1]
        assert added.key == "psets.valve_data.size_in"
        assert added.label == "valve_data.size_in" and added.plain_label == "size_in"

    run_pilot(app, scenario, size=(120, 40))


def test_export_text_and_column_keys_do_not_change_with_the_mode() -> None:
    client = FakeClient.with_valve_example()
    size = _size_column(client)
    record = {
        "key": "FV-1001",
        "type": "engineering.ControlValve",
        "psets": {"valve_data": {"size_in": 6.0}},
    }
    assert raw_text(record, TYPE) == "engineering.ControlValve"
    assert raw_text(record, size) == "6.0"
    assert to_tsv([TYPE, size], [record]) == (
        "Type\tvalve_data.size_in\nengineering.ControlValve\t6.0\n"
    )
    assert [TYPE.key, size.key] == ["type", "psets.valve_data.size_in"]
    host = Host(client, columns=[KEY, TYPE, size])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        plain_tsv = grid.copy_text()
        host.display_mode.technical = True
        grid.refresh_for_display_mode()
        await pilot.pause()
        assert grid.copy_text() == plain_tsv
        assert plain_tsv.splitlines()[0] == "Key\tType\tvalve_data.size_in"
        assert [c.key for c in grid.columns] == ["key", "type", "psets.valve_data.size_in"]

    run_pilot(host, scenario)


def test_grid_refreshes_on_the_mode_switch() -> None:
    app = TlApp(FakeClient.with_valve_example(), scope=SCOPE, actor="user:boss", is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        grid.set_columns([KEY, TYPE])
        await pilot.pause()
        assert "Record" in screen_text(app) and "core.Record" not in screen_text(app)
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.display_mode.technical is True
        assert "core.Record" in screen_text(app)
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.display_mode.technical is False
        assert "core.Record" not in screen_text(app)

    run_pilot(app, scenario)


def _relabel_size(client: FakeClient, label: str) -> None:
    """Give size_in the label the schema carries (co.acme.engineering: Nominal size)."""
    meta = client.form_metadata(SCOPE, "core.Record")
    group = meta.psets[0]
    fields = [
        f.model_copy(update={"label": label}) if f.path == "psets.valve_data.size_in" else f
        for f in group.fields
    ]
    group_copy = group.model_copy(update={"fields": fields})
    client.metadata = meta.model_copy(update={"psets": [group_copy, *meta.psets[1:]]})


def test_the_chooser_shows_the_schema_label_in_plain_and_the_path_in_technical() -> None:
    client = FakeClient.with_valve_example()
    _relabel_size(client, "Nominal size")
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ColumnChooser)
        text = screen_text(app)
        assert "Nominal size" in text and "size_in" not in text
        await pilot.press("escape")
        await pilot.pause()
        app.display_mode.technical = True
        await pilot.press("c")
        await pilot.pause()
        assert "valve_data.size_in" in screen_text(app)

    run_pilot(app, scenario, size=(120, 40))
