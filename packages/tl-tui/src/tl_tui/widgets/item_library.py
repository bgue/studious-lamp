"""The company item library: every item by code, with the projects that hold it (P2-I3-T06c).

A full-size modal, a ``LogScreen`` that is not in the navigation yet. The list shows the items by
code (State, Category, UOM and Projects leave the table when every row has the same value);
``r`` cycles the state filter (all, Active, Retired). Given a project, the list shows the items
that project adopted. The panel describes the highlighted item: its specification and the
projects that use it with their quantities. Read only: no action is offered, and Enter does
nothing yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.views import MaterialItemView

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.item_text import (
    ITEM_DROP,
    ITEM_KEYS,
    columns_for,
    item_page,
    next_state,
    row_cells,
    summary_line,
)
from tl_tui.layout import Page, Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen

PROJECTS_UNREAD = "Projects could not be read."


class ItemLibraryScreen(LogScreen[MaterialItemView]):
    """The company item library, or the items one project adopted when ``project`` is named."""

    LOG_NAME: ClassVar[str] = "Items"
    KEY_HINTS: ClassVar[str] = ITEM_KEYS  # every key the log has, in one text
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("r state", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("r", "Cycle the state filter: all, Active, Retired"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "state", "State", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str | None = None) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None  # None (all), "Active" or "Retired"
        self.views: list[MaterialItemView] = []  # as listed, before the state and filter boxes

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project or "Company"

    def columns(self) -> Sequence[str]:
        return columns_for(self.rows)

    def drop_order(self) -> Sequence[str]:
        return ITEM_DROP

    def keep_columns(self) -> Sequence[str]:
        return ("Number", "Subject", "State")

    def load_rows(self) -> Sequence[MaterialItemView]:
        self.views = self.client.list_materials_items(project=self.project, limit=MAX_VIEW_ROWS)
        if self.state_filter is None:
            return self.views
        retired = self.state_filter == "Retired"
        return [view for view in self.views if view.retired == retired]

    def row_key(self, row: MaterialItemView) -> str:
        return row.code

    def row_cells(self, row: MaterialItemView) -> Sequence[str]:
        return row_cells(row, self.columns())

    def row_record(self, row: MaterialItemView) -> tuple[str, str]:
        return (row.code, row.title)

    def panel_text(self, row: MaterialItemView | None) -> Panel:
        """The highlighted item with the projects that use it (one call per item)."""
        if row is None:
            return "No item matches."
        technical = mode_of(self.app).technical
        try:
            projects = self.client.list_materials_item_projects(row.code)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return render(_projects_unread(item_page(row, [], technical=technical)))
        return render(item_page(row, projects, technical=technical))

    def actions_for(self, row: MaterialItemView) -> Sequence[LogAction]:
        return []  # read only

    def summary_text(self) -> str:
        return summary_line(
            len(self.shown),
            len(self.views),
            state=self.state_filter,
            project=self.project,
            text=self.filter_text,
        )

    def open_row(self, row: MaterialItemView) -> None:
        """Enter does nothing yet: the record screen comes with the web twin."""

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Cycle the state filter: all, Active, Retired (the rows are read again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = next_state(self.state_filter)
        self.reload()


def _projects_unread(page: Page) -> Page:
    """The panel when the projects could not be read: the Projects note says so, not that none
    use the item."""
    sections = tuple(
        replace(section, note=PROJECTS_UNREAD) if section.heading == "Projects" else section
        for section in page.sections
    )
    return replace(page, sections=sections)
