"""The stock log: the balances by lot and location, with the lot panel (P2-I3-T06f).

A read-only ``LogScreen``, unregistered (no nav entry; the registry glue comes later). The rows and
the lot panel are ``tl_tui.materials_text`` (the same text the web twin shows). The keys ``l``,
``i`` and ``h`` narrow the rows on the server (``list_materials_stock``) to the highlighted row's
lot, item or heat, and a second press clears that filter; ``z`` widens the location given to the
places below it. ``/`` filters the rows on the screen. The panel is the lot of the highlighted row.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.views import MTR_SLOT, StockRowView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, render
from tl_tui.materials_text import (
    STOCK_DROP,
    STOCK_KEYS,
    lot_page,
    stock_cells,
    stock_columns_for,
    stock_summary,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen


class StockScreen(LogScreen[StockRowView]):
    """The stock of ``project``, optionally of one location (``location``, a location code)."""

    LOG_NAME: ClassVar[str] = "Stock"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    KEY_HINTS: ClassVar[str] = STOCK_KEYS
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "l lot", "i item", "h heat", "z subtree")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("l", "Only the highlighted row's lot; again for all lots"),
        ("i", "Only the highlighted row's item; again for all items"),
        ("h", "Only the highlighted row's heat; again for all heats"),
        ("z", "The location and the places below it; again for the location only"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("l", "lot_filter", "Lot", show=False),
        Binding("i", "item_filter", "Item", show=False),
        Binding("h", "heat_filter", "Heat", show=False),
        Binding("z", "subtree", "Subtree", show=False),
    ]

    def __init__(
        self, client: ClientInterface, project: str, *, location: str | None = None
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.location = location  # the location code the rows are of; None for all
        self.lot: str | None = None  # the server filters, set by the keys
        self.item: str | None = None
        self.heat: str | None = None
        self.subtree = False  # with ``location``: the places below it as well
        self.labels = Labels()
        self._columns_of: list[StockRowView] | None = None  # the rows the columns are for
        self._columns: tuple[str, ...] = stock_columns_for([])

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        if self._columns_of is not self.rows:  # worked out once per read, not once per cell
            self._columns_of = self.rows
            self._columns = stock_columns_for(self.rows)
        return self._columns

    def drop_order(self) -> Sequence[str]:
        return STOCK_DROP

    def keep_columns(self) -> Sequence[str]:
        """The stock log has no State column: Lot and Subject always show."""
        return list(self.columns())[:2]

    def load_rows(self) -> Sequence[StockRowView]:
        return self.client.list_materials_stock(
            self.project,
            lot=self.lot,
            location=self.location,
            item=self.item,
            heat=self.heat,
            subtree=self.subtree,
            limit=MAX_VIEW_ROWS,
        )

    def row_key(self, row: StockRowView) -> str:
        return f"{row.lot}@{row.location}"

    def row_cells(self, row: StockRowView) -> Sequence[str]:
        technical = mode_of(self.app).technical
        return stock_cells(row, self.columns(), self.labels, technical=technical)

    def row_record(self, row: StockRowView) -> tuple[str, str]:
        return (row.heat_no or row.lot, row.item_title)

    def panel_text(self, row: StockRowView | None) -> Panel:
        """The lot of the highlighted row (one ``get_materials_lot`` call per row)."""
        if row is None:
            return "No stock on hand"
        try:
            detail = self.client.get_materials_lot(self.project, row.lot)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return ""
        technical = mode_of(self.app).technical
        return render(
            lot_page(
                detail,
                row,
                self.labels,
                mtr=self._mtr_of(detail.receipt),
                technical=technical,
            )
        )

    def actions_for(self, row: StockRowView) -> Sequence[LogAction]:
        return []  # read only

    def summary_text(self) -> str:
        return stock_summary(
            len(self.shown),
            len(self.rows),
            item=self.item,
            location=self.location,
            heat=self.heat,
            lot=self.lot,
            subtree=self.subtree,
        )

    def open_row(self, row: StockRowView) -> None:
        """Read only: Enter does nothing yet (the record screens come with the web twins)."""

    # --- the log's own keys --------------------------------------------------------------

    def action_lot_filter(self) -> None:
        """Only the highlighted row's lot, or all lots again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.lot is not None:
            self.lot = None
        else:
            row = self.current()
            if row is None:
                return
            self.lot = row.lot
        self.reload()

    def action_item_filter(self) -> None:
        """Only the highlighted row's item, or all items again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.item is not None:
            self.item = None
        else:
            row = self.current()
            if row is None:
                return
            self.item = row.item_code
        self.reload()

    def action_heat_filter(self) -> None:
        """Only the highlighted row's heat, or all heats again (a row with no heat has none)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.heat is not None:
            self.heat = None
        else:
            row = self.current()
            if row is None or row.heat_no is None:
                return
            self.heat = row.heat_no
        self.reload()

    def action_subtree(self) -> None:
        """The places below the location as well, or the location only again (only with one)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.location is None:
            return
        self.subtree = not self.subtree
        self.reload()

    # --- the lot's manufacturer receipt -----------------------------------------------------

    def _mtr_of(self, receipt: str | None) -> str | None:
        """The filename of the receipt's MTR file; None when there is none or it cannot be read."""
        if receipt is None:
            return None
        try:
            detail = self.client.get_materials_receipt(self.project, receipt)
        except CLIENT_ERRORS:
            return None
        for file in detail.files:
            if file.slot == MTR_SLOT:
                return file.filename
        return None
