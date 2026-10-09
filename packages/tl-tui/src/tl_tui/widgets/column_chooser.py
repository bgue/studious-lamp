"""Column chooser modal: pick the grid columns to show (brief 10.2, P0-I2-T13b).

The modal lists every available column with a check box. Apply dismisses with the checked keys,
in the order they were offered; cancel dismisses with ``None``. It reads no records and writes
nothing; the grid applies the result.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, SelectionList, Static
from textual.widgets.selection_list import Selection

from tl_tui.widgets.grid import GridColumn


class ColumnChooser(ModalScreen[list[str] | None]):
    """Check boxes for every available column. Apply returns the checked keys, or ``None``."""

    KEY_HINTS: ClassVar[str] = "Space toggle  Ctrl+S apply  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "apply", "Apply", show=False),
    ]

    DEFAULT_CSS = """
    ColumnChooser { align: center middle; }
    ColumnChooser > Vertical {
        width: 50; height: auto; max-height: 90%;
        border: round $accent; background: $surface; padding: 1 2;
    }
    ColumnChooser #columns { height: auto; max-height: 24; }
    ColumnChooser #chooser-error { height: auto; color: $error; }
    ColumnChooser Horizontal { height: auto; align-horizontal: right; }
    ColumnChooser Button { margin-left: 1; }
    """

    def __init__(self, available: list[GridColumn], shown: list[str]) -> None:
        super().__init__()
        self.available = list(available)
        self.shown = list(shown)

    def compose(self) -> ComposeResult:
        options = [
            Selection(column.label, column.key, column.key in self.shown)
            for column in self.available
        ]
        with Vertical():
            yield Static("Choose columns", markup=False, id="chooser-title")
            yield SelectionList[str](*options, id="columns")
            yield Static("", markup=False, id="chooser-error")
            with Horizontal():
                yield Button("Apply", id="apply", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            self._apply()
        elif event.button.id == "cancel":
            self.dismiss(None)

    def action_apply(self) -> None:
        self._apply()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _apply(self) -> None:
        checked = set(self.query_one("#columns", SelectionList).selected)
        keys = [column.key for column in self.available if column.key in checked]
        if not keys:
            self.query_one("#chooser-error", Static).update("Choose at least one column")
            return
        self.dismiss(keys)
