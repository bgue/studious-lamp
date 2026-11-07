"""The storage locations: the tree of a project with what each place holds (P2-I3-T06h).

A full-size modal, a ``LogScreen`` that is not in the navigation yet. The list shows the locations
in tree order (the title indented under its parent); Kind, Lots and Lines leave the table when
every row has the same value. The panel describes the highlighted location: where it sits, the
stock it holds and the places under it. ``s`` opens the stock log of the highlighted location.
Read only: no action is offered, and Enter does nothing yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.views import LocationView

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, render
from tl_tui.location_text import (
    LOCATION_DROP,
    LOCATION_KEYS,
    columns_for,
    location_page,
    row_cells,
    summary_line,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.stock_screen import StockScreen


class LocationScreen(LogScreen[LocationView]):
    """The storage locations of ``project``, in tree order."""

    LOG_NAME: ClassVar[str] = "Locations"
    KEY_HINTS: ClassVar[str] = LOCATION_KEYS  # every key the log has, in one text
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("s stock here", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "The stock held at the highlighted location"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "stock_here", "Stock here", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.views: list[LocationView] = []  # as listed, before the filter box

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return columns_for(self.rows)

    def drop_order(self) -> Sequence[str]:
        return LOCATION_DROP

    def keep_columns(self) -> Sequence[str]:
        return ("Number", "Subject")

    def load_rows(self) -> Sequence[LocationView]:
        self.views = self.client.list_materials_locations(self.project, limit=MAX_VIEW_ROWS)
        return self.views

    def row_key(self, row: LocationView) -> str:
        return row.code

    def row_cells(self, row: LocationView) -> Sequence[str]:
        return row_cells(row, self.columns())

    def row_record(self, row: LocationView) -> tuple[str, str]:
        return (row.code, row.title)

    def panel_text(self, row: LocationView | None) -> Panel:
        """The highlighted location with the stock held there (one stock call per location)."""
        if row is None:
            return "No location matches."
        try:
            stock = self.client.list_materials_stock(
                self.project, location=row.code, limit=MAX_VIEW_ROWS
            )
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This location could not be read."
        technical = mode_of(self.app).technical
        return render(location_page(row, self.views, stock, technical=technical))

    def actions_for(self, row: LocationView) -> Sequence[LogAction]:
        return []  # read only

    def summary_text(self) -> str:
        return summary_line(len(self.shown), len(self.views), text=self.filter_text)

    def open_row(self, row: LocationView) -> None:
        """Enter does nothing yet: the record screen comes with the web twin."""

    # --- the log's own keys --------------------------------------------------------------

    def action_stock_here(self) -> None:
        """Open the stock log of the highlighted location."""
        if isinstance(self.focused, Input):
            return  # the key is text
        row = self.current()
        if row is None:
            return
        self.app.push_screen(StockScreen(self.client, self.project, location=row.code))
