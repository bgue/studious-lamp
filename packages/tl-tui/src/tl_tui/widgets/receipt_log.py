"""The receipts log: a project's goods receipts, their state and MTR, and their panel (P2-I3-T06b).

A ``LogScreen`` (precedent ``widgets/tag_register.py``), read only and unregistered: no nav entry,
no app change. The list shows the receipts by number; the panel describes the highlighted one
(``receipt_text.receipt_page``). ``o`` shows the receipts not yet decided, ``m`` the receipts whose
required MTR is missing; both are the route's flags, so the screen reads the list again. ``/``
filters the rows held. Enter opens nothing yet (the record screens come with the web twins).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.views import ReceiptView

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, render
from tl_tui.receipt_text import (
    KEYS,
    RECEIPT_DROP,
    columns_for,
    receipt_page,
    row_cells,
    summary_line,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen


class ReceiptLogScreen(LogScreen[ReceiptView]):
    """The receipts of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Receipts"
    KEY_HINTS: ClassVar[str] = KEYS  # every key the log has, in one text (walking tests read it)
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("o open only", "m missing MTR", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("o", "Only the receipts not yet decided (not Accepted, Rejected or Void)"),
        ("m", "Only the receipts whose required MTR is missing"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("o", "open_only", "Open only", show=False),
        Binding("m", "missing_mtr", "Missing MTR", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.open_only = False
        self.missing_mtr = False
        self._columns_rows: list[ReceiptView] | None = None  # rows the columns were worked out for
        self._column_names: tuple[str, ...] = columns_for([])

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        """The columns of the rows held: ``columns_for`` worked out once per read of the rows."""
        if self._columns_rows is not self.rows:
            self._columns_rows = self.rows
            self._column_names = columns_for(self.rows)
        return self._column_names

    def keep_columns(self) -> Sequence[str]:
        return ("Number", "Subject", "State")

    def drop_order(self) -> Sequence[str]:
        return RECEIPT_DROP

    def load_rows(self) -> Sequence[ReceiptView]:
        return self.client.list_materials_receipts(
            self.project,
            open_only=self.open_only,
            missing_mtr=self.missing_mtr,
            limit=MAX_VIEW_ROWS,
        )

    def row_key(self, row: ReceiptView) -> str:
        return row.number

    def row_cells(self, row: ReceiptView) -> Sequence[str]:
        return row_cells(row, self.columns())

    def row_record(self, row: ReceiptView) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: ReceiptView | None) -> Panel:
        """The highlighted receipt: its lines, delivery, inspection and files (one call each)."""
        if row is None:
            return "No receipt matches."
        try:
            detail = self.client.get_materials_receipt(self.project, row.number)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return ""
        technical = mode_of(self.app).technical
        return render(receipt_page(detail, technical=technical))

    def actions_for(self, row: ReceiptView) -> Sequence[LogAction]:
        return []  # read only

    def summary_text(self) -> str:
        return summary_line(
            len(self.shown),
            len(self.rows),
            open_only=self.open_only,
            missing_mtr=self.missing_mtr,
            text=self.filter_text,
        )

    def open_row(self, row: ReceiptView) -> None:
        """Enter on a row does nothing yet: the receipt's record screen comes with the web twin."""

    # --- the log's own keys --------------------------------------------------------------

    def action_open_only(self) -> None:
        """Show the receipts not yet decided, or all again (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.open_only = not self.open_only
        self.reload()

    def action_missing_mtr(self) -> None:
        """Show the receipts whose required MTR is missing, or all again (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.missing_mtr = not self.missing_mtr
        self.reload()
