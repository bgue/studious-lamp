"""The history of one setting, with undo of the latest change at a layer (P0-I8-S19; brief 30.3).

A modal table of every change of the key, oldest first: number, layer, time, actor, old and new
value, reason. ``u`` undoes the highlighted change when it is the latest at its layer (the service
refuses any other), asking for a reason when the key needs one. Dismisses with ``True`` when
something was undone, so the list behind it reloads.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_core.settings.types import SettingChange

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.settings_text import (
    HISTORY_COLUMNS,
    TECHNICAL_HISTORY_COLUMNS,
    history_cells,
    layer_label,
)
from tl_tui.widgets.setting_form import SettingForm


class SettingHistory(ModalScreen[bool]):
    """The changes of ``key``. Dismisses with whether anything was undone."""

    KEY_HINTS: ClassVar[str] = "Up/Down choose  u undo the latest change at its layer  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("u", "undo", "Undo", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    SettingHistory { align: center middle; }
    SettingHistory > Vertical {
        width: 110; max-width: 98%; height: 24; max-height: 95%;
        border: round $accent; background: $surface; padding: 1 2;
    }
    SettingHistory #history-title { text-style: bold; }
    SettingHistory DataTable { height: 1fr; }
    SettingHistory #history-status { height: auto; }
    """

    def __init__(self, client: ClientInterface, key: str) -> None:
        super().__init__()
        self.client = client
        self.key = key
        self.changes: list[SettingChange] = []
        self.changed = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"History of {self.key}", markup=False, id="history-title")
            yield DataTable[str](id="history-table", cursor_type="row", zebra_stripes=True)
            yield Static(self.KEY_HINTS, markup=False, id="history-status")

    def on_mount(self) -> None:
        self._columns()
        self.reload()
        self.query_one("#history-table", DataTable).focus()

    def _columns(self) -> None:
        """The columns for the mode now: the change number is technical only."""
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=True)
        technical = mode_of(self.app).technical
        table.add_columns(*(TECHNICAL_HISTORY_COLUMNS if technical else HISTORY_COLUMNS))

    def refresh_for_display_mode(self) -> None:
        """Show or hide the change numbers for the mode now, keeping the highlighted change."""
        table = self.query_one("#history-table", DataTable)
        row = table.cursor_row
        self._columns()
        self.reload()
        if self.changes:
            table.move_cursor(row=min(row, len(self.changes) - 1))

    def reload(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear()
        try:
            self.changes = self.client.setting_history(self.key)
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc))
            return
        technical = mode_of(self.app).technical
        for change in self.changes:
            cells = history_cells(change, technical=technical)
            table.add_row(*(Text(c) for c in cells), key=str(change.seq))
        if not self.changes:
            self._say("No changes yet: the value is the platform default.")
        else:
            table.move_cursor(row=len(self.changes) - 1)

    def _say(self, text: str) -> None:
        self.query_one("#history-status", Static).update(text)

    def _highlighted(self) -> SettingChange | None:
        table = self.query_one("#history-table", DataTable)
        if not self.changes or table.cursor_row >= len(self.changes):
            return None
        return self.changes[table.cursor_row]

    def action_undo(self) -> None:
        change = self._highlighted()
        if change is None:
            return
        latest = [c for c in self.changes if c.layer == change.layer][-1]
        if latest.seq != change.seq:
            if mode_of(self.app).technical:
                self._say(
                    f"Only the latest change at {change.layer} can be undone (#{latest.seq})."
                )
            else:
                self._say(f"Only the latest change at {layer_label(change.layer)} can be undone.")
            return
        try:
            view = self.client.get_setting(self.key)
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc))
            return

        def done(result: bool | None) -> None:
            if result:
                self.changed = True
                self.reload()
                self._say(self._undone_text(change))

        self.app.push_screen(
            SettingForm(self.client, view, "revert", change.layer, seq=change.seq), done
        )

    def _undone_text(self, change: SettingChange) -> str:
        """The change number is technical only; plain mode says what happened."""
        if mode_of(self.app).technical:
            return f"Undid #{change.seq}."
        return "Undid the change."

    def action_close(self) -> None:
        self.dismiss(self.changed)
