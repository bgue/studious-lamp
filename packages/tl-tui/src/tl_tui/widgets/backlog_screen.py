"""The backlog tile: a full-size ``LogScreen`` with two views of the same IWP list (P2-I2 T08;
spec §8, ``tui-layout``).

``b`` (default) shows the backlog weeks per foreman; ``z`` shows the sizing list, the IWPs whose
estimated hours are outside ``awp.iwp.size_hours``. Both views come from ``tl_tui.backlog_text``;
this screen only reads the IWP list and the two settings, once per load (F5), and keeps the view.
No action is offered, and Enter opens nothing: the tile is a view.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input

from tl_tui.backlog_text import (
    BACKLOG_COLUMNS,
    SIZING_COLUMNS,
    BacklogRow,
    SizedIwpRow,
    backlog_cells,
    backlog_panel,
    backlog_rows,
    backlog_summary,
    sizing_cells,
    sizing_panel,
    sizing_rows,
    sizing_summary,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen

if TYPE_CHECKING:
    from tl_mod_awp.iwp_views import IwpRow

    from tl_tui.client import ClientInterface

TARGET_SETTING = "awp.backlog.target_weeks"
SIZE_SETTING = "awp.iwp.size_hours"
BACKLOG = "backlog"
SIZING = "sizing"

BacklogLine = BacklogRow | SizedIwpRow


class BacklogScreen(LogScreen[BacklogLine]):
    """The backlog of ``project``: the IWPs of the project, in the view the key chose."""

    LOG_NAME: ClassVar[str] = "Backlog"
    KEY_HINTS: ClassVar[str] = "b backlog  z sizing  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("b backlog", "z sizing")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("b", "Show the backlog weeks per foreman (Ready and Issued IWPs)"),
        ("z", "Show the IWPs whose estimated hours are outside the size bounds"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("b", "backlog", "Backlog", show=False),
        Binding("z", "sizing", "Sizing", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.view = BACKLOG
        self.iwps: list[IwpRow] = []  # as listed; the two views are computed from it
        self.target = 0  # awp.backlog.target_weeks, read on each load
        self.bounds = (Decimal(0), Decimal(0))  # awp.iwp.size_hours as [low, high], read on load

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return SIZING_COLUMNS if self.view == SIZING else BACKLOG_COLUMNS

    def keep_columns(self) -> Sequence[str]:
        """Both views have a few short columns: all of them always show."""
        return self.columns()

    def load_rows(self) -> Sequence[BacklogLine]:
        """Read the settings once, then the IWPs (off the UI thread)."""
        target = self.client.get_setting(TARGET_SETTING, project=self.project).effective.value
        low, high = self.client.get_setting(SIZE_SETTING, project=self.project).effective.value
        self.target = int(target)
        self.bounds = (Decimal(str(low)), Decimal(str(high)))
        self.iwps = self.client.list_iwps(self.project)
        return self._filtered()

    def row_key(self, row: BacklogLine) -> str:
        if isinstance(row, SizedIwpRow):
            return row.number
        return "-" if row.foreman is None else row.foreman

    def row_cells(self, row: BacklogLine) -> Sequence[str]:
        if isinstance(row, SizedIwpRow):
            return sizing_cells(row, None)
        return backlog_cells(row, None)

    def row_record(self, row: BacklogLine) -> tuple[str, str]:
        if isinstance(row, SizedIwpRow):
            return (row.number, row.title)
        return (self.row_key(row), f"{row.weeks} weeks")

    def panel_text(self, row: BacklogLine | None) -> str:
        """The heading and the summary of the view (the rows are the view's own)."""
        if self.view == SIZING:
            return sizing_panel(self.iwps, *self.bounds)
        return backlog_panel(self.iwps, self.target)

    def actions_for(self, row: BacklogLine) -> Sequence[LogAction]:
        """The tile offers no action."""
        return []

    def summary_text(self) -> str:
        if self.view == SIZING:
            return sizing_summary(self.iwps, *self.bounds)
        return backlog_summary(self.iwps, self.target)

    def open_row(self, row: BacklogLine) -> None:
        """Enter opens nothing from the tile: the IWP log opens the records."""

    # --- the log's own keys --------------------------------------------------------------

    def action_backlog(self) -> None:
        """Show the backlog weeks per foreman."""
        self._switch(BACKLOG)

    def action_sizing(self) -> None:
        """Show the IWPs outside the size bounds."""
        self._switch(SIZING)

    # --- helpers -------------------------------------------------------------------------

    def _filtered(self) -> list[BacklogLine]:
        """The rows of the current view, computed from the IWPs already held (no read)."""
        if self.view == SIZING:
            low, high = self.bounds
            return list(sizing_rows(self.iwps, low, high))
        return list(backlog_rows(self.iwps, self.target))

    def _switch(self, view: str) -> None:
        if isinstance(self.focused, Input):
            return  # the key is text
        self.view = view
        self.rows = self._filtered()
        self._fill(self._key())
