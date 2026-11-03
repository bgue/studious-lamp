"""The movement log: every stock movement of a project, in ledger order (P2-I3-T06f).

A read-only ``LogScreen``, unregistered (no nav entry; the registry glue comes later). The rows and
the summary are ``tl_tui.materials_text``. ``p`` steps the period (``period_range`` of today gives
the ``since`` and ``until`` the server reads); ``k`` steps the kind through the kinds the rows read
for the period, so the kind filter is applied on the screen to the rows already read. The panel
shows the highlighted movement as property lines; there is no detail call for a movement.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.views import MovementView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.layout import Page, Panel, Section, identity_line, prop, render
from tl_tui.materials_text import (
    MOVEMENT_DROP,
    MOVEMENT_KEYS,
    movement_cells,
    movement_columns_for,
    movement_summary,
    next_kind,
    next_period,
    period_range,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen

#: The movement properties of the panel, in order (the table columns of the log, plus Qty).
PANEL_COLUMNS: tuple[str, ...] = ("Date", "Kind", "Lot", "Item", "Qty", "For", "From", "To", "By")


class MovementLogScreen(LogScreen[MovementView]):
    """The movements of ``project``, optionally of one lot (``lot``, a lot key)."""

    LOG_NAME: ClassVar[str] = "Movements"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    KEY_HINTS: ClassVar[str] = MOVEMENT_KEYS
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("k kind", "p period")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("k", "Show the next kind of the rows read: all, then each kind"),
        ("p", "Show the next period: all, the last 7 days, the last 30 days, this month"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("k", "kind_filter", "Kind", show=False),
        Binding("p", "period_filter", "Period", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str, *, lot: str | None = None) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.lot = lot  # the server filter: one lot's movements
        self.kind: str | None = None  # the screen's filter: one kind, None for all
        self.period = "all"  # the server filter, a key of ``PERIODS``
        self.views: list[MovementView] = []  # as read for the period, every kind (before ``kind``)
        self.labels = Labels()
        self._columns_of: list[MovementView] | None = None  # the rows the columns are for
        self._columns: tuple[str, ...] = movement_columns_for([])

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        if self._columns_of is not self.rows:  # worked out once per read, not once per cell
            self._columns_of = self.rows
            self._columns = movement_columns_for(self.rows)
        return self._columns

    def drop_order(self) -> Sequence[str]:
        return MOVEMENT_DROP

    def keep_columns(self) -> Sequence[str]:
        """The movement log has no State column: Date and Kind always show."""
        return list(self.columns())[:2]

    def load_rows(self) -> Sequence[MovementView]:
        since, until = period_range(self.period, date.today().isoformat())
        self.views = self.client.list_materials_movements(
            self.project, lot=self.lot, since=since, until=until, limit=MAX_VIEW_ROWS
        )
        return [view for view in self.views if self.kind is None or view.kind == self.kind]

    def row_key(self, row: MovementView) -> str:
        return str(row.seq)

    def row_cells(self, row: MovementView) -> Sequence[str]:
        technical = mode_of(self.app).technical
        return movement_cells(row, self.columns(), self.labels, technical=technical)

    def row_record(self, row: MovementView) -> tuple[str, str]:
        return (f"#{row.seq}", _kind_word(row))

    def panel_text(self, row: MovementView | None) -> Panel:
        """The highlighted movement as property lines (no call: the row holds all of it)."""
        if row is None:
            return "No movements"
        cells = movement_cells(row, PANEL_COLUMNS, self.labels)
        props = [prop(name, cell) for name, cell in zip(PANEL_COLUMNS, cells, strict=True)]
        props.append(prop("Reason", row.reason))
        props.append(prop("Person", row.person))
        page = Page(
            identity=identity_line(f"#{row.seq}", _kind_word(row)),
            sections=(Section("", tuple(props)),),
        )
        return render(page)

    def actions_for(self, row: MovementView) -> Sequence[LogAction]:
        return []  # read only

    def summary_text(self) -> str:
        return movement_summary(
            len(self.shown),
            len(self.views),
            kind=self.kind,
            period=self.period,
            lot=self.lot,
        )

    def open_row(self, row: MovementView) -> None:
        """Read only: Enter does nothing (a movement has no record screen)."""

    # --- the log's own keys --------------------------------------------------------------

    def action_kind_filter(self) -> None:
        """Show the next kind of the rows read for the period, then all kinds again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        kinds = sorted({view.kind for view in self.views})
        self.kind = next_kind(self.kind, kinds)
        self.reload()

    def action_period_filter(self) -> None:
        """Show the next period: all, the last 7 days, the last 30 days, this month, all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.period = next_period(self.period)
        self.reload()


def _kind_word(row: MovementView) -> str:
    """The kind of a movement as its word (``Issue``, ``Receipt``)."""
    return movement_cells(row, ("Kind",))[0]
