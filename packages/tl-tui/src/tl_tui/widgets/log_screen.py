"""The shared log screen: every log is this layout with its own rows, panel and actions (P1-UX2-S2).

Top to bottom: the breadcrumb, a filter box, the list, the panel of the selected record (below the
list, or to its right from 160 columns), the actions bar, the keys row and the status line. A log
subclasses ``LogScreen`` and fills in the hooks (what its rows, panel and actions are); it never
lays anything out. The screen decides nothing: ``LogAction.run`` calls the command the host chose
and the service refuses or allows (a refusal lands in the status line).

``load_rows`` and ``actions_for`` run off the UI thread; the base applies their answers on the UI
thread and drops an answer for a row that is no longer highlighted.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.log_text import SEPARATOR, actions_text, breadcrumb_text, is_wide

RESERVED_KEYS: frozenset[str] = frozenset({"escape", "enter", "slash", "f5"})
CRUMB_PADDING = 2  # the screen's left and right padding


@dataclass(frozen=True)
class LogAction:
    """One thing a person may do to the highlighted record, as the host offers it."""

    key: str  # textual key name, "a", "ctrl+e", "f6"
    label: str  # plain words; shown in the bar
    run: Callable[[], None]  # runs the existing command or form; may raise CLIENT_ERRORS


def check_action_keys(actions: Sequence[LogAction], reserved: frozenset[str]) -> None:
    """Raise ``ValueError`` when two actions share a key or one uses a reserved key."""
    seen: set[str] = set()
    for action in actions:
        if action.key in reserved:
            raise ValueError(f"action {action.label!r}: key {action.key!r} is reserved")
        if action.key in seen:
            raise ValueError(f"action {action.label!r}: key {action.key!r} is offered twice")
        seen.add(action.key)


def usable_actions(actions: Sequence[LogAction], reserved: frozenset[str]) -> list[LogAction]:
    """The actions whose key is free: the first of a repeated key, none on a reserved key."""
    seen: set[str] = set()
    kept: list[LogAction] = []
    for action in actions:
        if action.key in reserved or action.key in seen:
            continue
        seen.add(action.key)
        kept.append(action)
    return kept


class LogScreen[Row](ModalScreen[None]):
    """The base of every log. Esc closes it (it clears the filter first when it has text)."""

    LOG_NAME: ClassVar[str] = "Log"
    KEY_HINTS: ClassVar[str] = "/ filter  F5 reload  Esc back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    LogScreen { background: $surface; }
    LogScreen > Vertical { padding: 0 1; }
    LogScreen #log-crumb { height: 1; text-style: bold; }
    LogScreen #log-filter, LogScreen #log-filter:focus { height: 3; }
    LogScreen #log-body { height: 1fr; layout: vertical; }
    LogScreen #log-table { height: 1fr; min-height: 5; }
    LogScreen #log-panel { height: 12; border-top: solid $accent; padding: 0 1; }
    LogScreen #log-actions { height: auto; min-height: 1; }
    LogScreen #log-keys { height: 1; color: $text-muted; }
    LogScreen #log-status { height: 1; }
    LogScreen.-wide #log-body { layout: horizontal; }
    LogScreen.-wide #log-table { width: 3fr; height: 1fr; }
    LogScreen.-wide #log-panel {
        width: 2fr; height: 1fr; border-top: none; border-left: solid $accent;
    }
    """

    # --- the host fills these in ----------------------------------------------------------

    def log_project(self) -> str:
        raise NotImplementedError

    def columns(self) -> Sequence[str]:
        raise NotImplementedError

    def load_rows(self) -> Sequence[Row]:
        """Read the rows (called off the UI thread); may raise ``CLIENT_ERRORS``."""
        raise NotImplementedError

    def row_key(self, row: Row) -> str:
        raise NotImplementedError

    def row_cells(self, row: Row) -> Sequence[str]:
        """Plain text per column, never raw codes (read the mode with ``mode_of(self.app)``)."""
        raise NotImplementedError

    def row_record(self, row: Row) -> tuple[str, str]:
        """``(number, title)`` of the record, for the breadcrumb."""
        raise NotImplementedError

    def panel_text(self, row: Row | None) -> str:
        raise NotImplementedError

    def actions_for(self, row: Row) -> Sequence[LogAction]:
        """What the viewer may do to ``row`` now (called off the UI thread); may raise
        ``CLIENT_ERRORS``."""
        raise NotImplementedError

    def summary_text(self) -> str:
        """The count or summary line; ``""`` when the log has none."""
        return ""

    def open_row(self, row: Row) -> None:
        """Enter on a row; normally ``open_record(self, client, scope, project, actor, id)``."""
        raise NotImplementedError

    # --- state ----------------------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Row] = []  # as loaded, before the filter box
        self.shown: list[Row] = []
        self.filter_text = ""
        self.offered: list[LogAction] = []  # the actions of the highlighted row, once known
        self._acted_for: str | None = None  # the row key the bar was last asked about
        self._actions_gen = 0
        self._rows_gen = 0

    # --- layout ---------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="log-crumb")
            yield Input(placeholder="Filter", id="log-filter")
            with Container(id="log-body"):
                yield DataTable[str](id="log-table", cursor_type="row", zebra_stripes=True)
                with VerticalScroll(id="log-panel"):
                    yield Static("", markup=False, id="log-panel-text")
            yield Static("", markup=False, id="log-actions")
            yield Static(self.KEY_HINTS, markup=False, id="log-keys")
            yield Static("", markup=False, id="log-status")

    def on_mount(self) -> None:
        self.query_one("#log-table", DataTable).add_columns(*self.columns())
        self._set_layout(self.size.width)
        self._show_row()
        self.reload()
        self.query_one("#log-table", DataTable).focus()

    def on_resize(self, event: events.Resize) -> None:
        self._set_layout(event.size.width)
        self._show_crumb()

    def _set_layout(self, width: int) -> None:
        self.set_class(is_wide(width), "-wide")

    # --- rows -----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the rows again (off the UI thread) and keep the highlighted row where it is."""
        self._rows_gen += 1
        self.run_worker(self._load(self._rows_gen), group="log-rows", exclusive=True)

    def _alive(self) -> bool:
        """False once the screen is closed or taken apart (a late answer must not touch it)."""
        return self.is_attached and bool(self.query("#log-table"))

    async def _load(self, gen: int) -> None:
        try:
            rows = await asyncio.to_thread(self.load_rows)
        except CLIENT_ERRORS as exc:
            if gen == self._rows_gen and self._alive():
                self.say(describe_error(exc), error=True)
            return
        if gen != self._rows_gen or not self._alive():  # superseded, or the screen was closed
            return
        self.rows = list(rows)
        self._fill(self._key(), reread=True)

    def _fill(self, keep: str | None = None, *, reread: bool = False) -> None:
        """Apply the filter box to ``self.rows`` and fill the table; the cursor stays on ``keep``.

        ``reread``: the rows were just read again, so the bar asks for the row's actions again.
        """
        needle = self.filter_text.strip().lower()
        self.shown = [
            row
            for row in self.rows
            if not needle or needle in " ".join(self.row_cells(row)).lower()
        ]
        table = self.query_one("#log-table", DataTable)
        table.clear()
        for row in self.shown:
            # Text, not str: a cell is read as markup, and a title such as [a, b] is not markup
            table.add_row(*(Text(cell) for cell in self.row_cells(row)), key=self.row_key(row))
        if self.shown:
            keys = [self.row_key(row) for row in self.shown]
            table.move_cursor(row=keys.index(keep) if keep in keys else 0)
        self.say(self.summary_text())
        self._show_row(force=reread)

    def current(self) -> Row | None:
        table = self.query_one("#log-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _key(self) -> str | None:
        row = self.current()
        return self.row_key(row) if row is not None else None

    # --- the highlighted row --------------------------------------------------------------

    def _show_crumb(self) -> None:
        row = self.current()
        number, title = self.row_record(row) if row is not None else (None, None)
        width = max(self.size.width - CRUMB_PADDING, 1)
        line = breadcrumb_text(self.log_project(), self.LOG_NAME, number, title, width)
        text = Text(line)
        head = f"{self.log_project()}{SEPARATOR}{self.LOG_NAME}"
        if len(line) > len(head):
            text.stylize("bold reverse", len(head) + len(SEPARATOR))  # the record part stands out
        self.query_one("#log-crumb", Static).update(text)

    def _show_row(self, *, force: bool = False) -> None:
        """Breadcrumb, panel and (when the row changed, or ``force``) a fresh actions bar."""
        row = self.current()
        self._show_crumb()
        self.query_one("#log-panel-text", Static).update(self.panel_text(row))
        key = self.row_key(row) if row is not None else None
        if force or key != self._acted_for:
            self._acted_for = key
            self._ask_actions(row)

    def _ask_actions(self, row: Row | None) -> None:
        self._actions_gen += 1
        self.offered = []
        self._draw_actions()
        if row is not None:
            self.run_worker(self._fetch_actions(self._actions_gen, row), group="log-actions")

    async def _fetch_actions(self, gen: int, row: Row) -> None:
        try:
            actions = await asyncio.to_thread(self.actions_for, row)
        except CLIENT_ERRORS as exc:
            if (
                gen == self._actions_gen and self._alive()
            ):  # an answer for a row no longer highlighted is dropped
                self.offered = []
                self._draw_actions(failed=True)
                self.say(describe_error(exc), error=True)
            return
        if gen != self._actions_gen or not self._alive():
            return
        self._apply_actions(actions)

    def _apply_actions(self, actions: Sequence[LogAction]) -> None:
        reserved = RESERVED_KEYS | frozenset(self._bindings.key_to_bindings)
        if self.app.is_headless:
            check_action_keys(actions, reserved)  # a test run refuses a colliding key
        self.offered = usable_actions(actions, reserved)
        self._draw_actions()

    def _draw_actions(self, *, failed: bool = False) -> None:
        bar = self.query_one("#log-actions", Static)
        if failed or self.current() is None:
            bar.update("")
            return
        bar.update(actions_text(self.offered, can_open=True))

    # --- events ---------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._show_row()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row opens the record; Esc there returns to this row."""
        event.stop()
        if 0 <= event.cursor_row < len(self.shown):
            self.open_row(self.shown[event.cursor_row])

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.filter_text = event.value
        self._fill(self._key())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#log-table", DataTable).focus()

    def on_key(self, event: events.Key) -> None:
        """A key an offered action uses runs that action (never while a box takes the text)."""
        if isinstance(self.focused, Input):
            return
        for action in self.offered:
            if action.key == event.key:
                event.stop()
                event.prevent_default()
                self.attempt(action.run)
                return

    # --- what the host may call -----------------------------------------------------------

    def say(self, text: str, *, error: bool = False) -> None:
        """Write the status line; an error is marked ``! ``."""
        self.query_one("#log-status", Static).update(("! " if error else "") + text)

    def attempt(self, run: Callable[[], None]) -> bool:
        """Run a command; a refusal goes to the status line. On success read the rows again.

        An action that opens a form calls this from the form's callback with the command.
        """
        try:
            run()
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return False
        self.reload()  # the rows and the bar follow what the command changed
        return True

    def refresh_for_display_mode(self) -> None:
        """The technical toggle changed: rebuild the rows and the panel, keeping the row."""
        self._fill(self._key())

    # --- keys -----------------------------------------------------------------------------

    def action_filter(self) -> None:
        self.query_one("#log-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        box = self.query_one("#log-filter", Input)
        if box.value:
            box.value = ""
            self.query_one("#log-table", DataTable).focus()
            return
        self.dismiss(None)
