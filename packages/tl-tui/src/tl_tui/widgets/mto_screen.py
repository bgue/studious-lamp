"""The MTO lines log: take-off lines with what is reserved, issued and short (P2-I3-T06d).

A full-size modal, a ``LogScreen`` that is not in the navigation yet. The list shows the lines by
key (``For`` and ``Need by`` leave the table when every row has the same value); ``Short`` is what
no reservation and no issue covers. The panel describes the highlighted line: its source, its
coverage, the lot reservations against it and the receipts of its item that are not yet decided.
``1`` shows every line, ``2`` only the short ones (the server filters both). Read only: no action
is offered, and Enter does nothing yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.views import MtoLineView

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, render
from tl_tui.mto_text import (
    KEYS,
    MTO_DROP,
    columns_for,
    mto_page,
    row_cells,
    summary_line,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen


class MtoLinesScreen(LogScreen[MtoLineView]):
    """The take-off lines of ``project``, or of one work package when ``work_package`` is named."""

    LOG_NAME: ClassVar[str] = "MTO lines"
    KEY_HINTS: ClassVar[str] = KEYS  # every key the log has, in one text
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("1 all lines", "2 short only", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("1", "Show all the take-off lines"),
        ("2", "Show only the lines not covered by reservations and issues"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "all_lines", "All lines", show=False),
        Binding("2", "short_only", "Short only", show=False),
    ]

    def __init__(
        self, client: ClientInterface, project: str, *, work_package: str | None = None
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.work_package = work_package
        self.short_only = False
        self.views: list[MtoLineView] = []  # as listed, before the filter box

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return columns_for(self.rows)

    def drop_order(self) -> Sequence[str]:
        return MTO_DROP

    def keep_columns(self) -> Sequence[str]:
        return ("Number", "Subject")

    def load_rows(self) -> Sequence[MtoLineView]:
        self.views = self.client.list_materials_mto_lines(
            self.project,
            work_package=self.work_package,
            short_only=self.short_only,
            limit=MAX_VIEW_ROWS,
        )
        return self.views

    def row_key(self, row: MtoLineView) -> str:
        return row.key

    def row_cells(self, row: MtoLineView) -> Sequence[str]:
        return row_cells(row, self.columns())

    def row_record(self, row: MtoLineView) -> tuple[str, str]:
        return (row.key, row.item_title)

    def panel_text(self, row: MtoLineView | None) -> Panel:
        """The highlighted line with its reservations and open receipts (one call per line)."""
        if row is None:
            return "No take-off line matches."
        try:
            detail = self.client.get_materials_mto_line(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This take-off line could not be read."
        technical = mode_of(self.app).technical
        return render(mto_page(detail, technical=technical))

    def actions_for(self, row: MtoLineView) -> Sequence[LogAction]:
        return []  # read only

    def summary_text(self) -> str:
        return summary_line(
            len(self.shown),
            len(self.views),
            short_only=self.short_only,
            work_package=self.work_package,
            text=self.filter_text,
        )

    def open_row(self, row: MtoLineView) -> None:
        """Enter does nothing yet: the record screen comes with the web twin."""

    # --- the log's own keys --------------------------------------------------------------

    def action_all_lines(self) -> None:
        """Show every take-off line (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.short_only = False
        self.reload()

    def action_short_only(self) -> None:
        """Show only the lines not covered by reservations and issues (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.short_only = True
        self.reload()
