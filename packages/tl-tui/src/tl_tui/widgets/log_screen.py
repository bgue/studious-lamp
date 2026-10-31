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
from typing import Any, ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, state_style
from tl_tui.log_text import (
    MIN_FLEX,
    SEPARATOR,
    actions_text,
    breadcrumb_text,
    fit_cell,
    flex_index,
    free_width,
    is_wide,
    keys_row,
    plan_columns,
    table_width,
)

STATE_COLUMNS = frozenset(
    {"State", "Status", "Timing", "Bar", "Conformance", "Number check"}
)  # cells that take a state colour
RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "escape",
        "enter",
        "slash",
        "f5",
        "up",
        "down",
        "pageup",
        "pagedown",
        "home",
        "end",
        "space",
        "tab",
    }
)  # list navigation is never an action key
CRUMB_PADDING = 2  # the screen's left and right padding
#: The table holds this many rows at first and takes the next chunk when the cursor comes within
#: ``EDGE_ROWS`` of the last one: Textual measures every cell of every row it is given (about
#: 0.1 ms a row), so 5,000 rows cost half a second whether or not they are on screen. The screen
#: still holds, filters and counts every row it was given; only the table is filled as needed.
WINDOW_ROWS = 120
CHUNK_ROWS = 240
EDGE_ROWS = 40


class LogTable(DataTable[str]):
    """The list. ``Ctrl+End`` goes to the very last row, whether or not it is in the table yet."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fill_all: Callable[[], None] | None = None
        self.fill_more: Callable[[], None] | None = None  # the view reached the last rows held

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if (
            self.fill_more is not None
            and new_value + self.size.height >= self.row_count - EDGE_ROWS
        ):
            self.fill_more()  # the wheel or a scroll bar moved the view near the last row held

    def action_scroll_bottom(self) -> None:
        if self.fill_all is not None:
            self.fill_all()
        super().action_scroll_bottom()


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
    KEY_HINTS: ClassVar[str] = "/ filter  F5 reload  Esc back"  # every key, in one text
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter",)  # the keys row after Up/Down move
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = ()  # the log's other keys, for F1

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
        Binding("f1", "help", "Help", show=False),
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

    def panel_text(self, row: Row | None) -> Panel:
        """The panel of ``row``: a plain string, or a styled ``Text`` from ``layout.render``."""
        raise NotImplementedError

    def keep_columns(self) -> Sequence[str]:
        """The columns that always show. Any other column whose value is the same in every
        shown row (two or more) is hidden, and comes back when two values appear."""
        names = list(self.columns())
        flex = flex_index(names)
        return [*names[:1], "State", *([names[flex]] if flex is not None else [])]

    def drop_order(self) -> Sequence[str]:
        """The columns to leave out, least needed first, when the list would otherwise scroll
        sideways or squeeze the subject."""
        return []

    def shrink_columns(self) -> Sequence[str]:
        """The columns that shorten (with ``…``) before the subject does."""
        return ("With",)

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

    def filter_changed(self, text: str) -> None:
        """The filter box changed (before the list follows it). A log that holds only the first
        page of its rows reads the rest here."""

    def rows_exhausted(self) -> None:
        """The cursor is near the last row held. A log that holds only the first page of its rows
        reads the rest here."""

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
        self._cells: dict[int, tuple[Row, tuple[str, ...], str]] = {}  # row -> cells, search text
        self._drawn_width = -1  # the width the table was last planned for
        self._in_table = 0  # the first rows of ``shown`` that the table holds
        self._row_due = False  # a deferred panel and bar are waiting for the list to be drawn
        self._row_force = False
        self._planned_names: list[str] = []
        self._planned_cells: list[list[str]] = []

    # --- layout ---------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="log-crumb")
            yield Input(placeholder="Filter", id="log-filter")
            with Container(id="log-body"):
                yield LogTable(id="log-table", cursor_type="row", zebra_stripes=True)
                with VerticalScroll(id="log-panel"):
                    yield Static("", markup=False, id="log-panel-text")
            yield Static("", markup=False, id="log-actions")
            yield Static("", markup=False, id="log-keys")
            yield Static("", markup=False, id="log-status")

    def on_mount(self) -> None:
        table = self.query_one("#log-table", LogTable)
        table.fill_all = self._fill_all
        table.fill_more = self._fill_more
        table.add_columns(*self.columns())
        self._set_layout(self.size.width)
        self._show_keys()
        self._show_row()
        self.reload()
        self.query_one("#log-table", DataTable).focus()

    def on_resize(self, event: events.Resize) -> None:
        self._set_layout(event.size.width)
        self._show_keys()
        self._show_crumb()
        if self._alive() and event.size.width != self._drawn_width:
            self._draw_table(self._key())  # the subject column shortens to the width it has

    def _set_layout(self, width: int) -> None:
        self.set_class(is_wide(width), "-wide")

    def _show_keys(self) -> None:
        """The keys row, cut to one line at the screen's width (the rest is on the help screen)."""
        width = self.size.width or 80
        self.query_one("#log-keys", Static).update(keys_row(self.KEY_CELLS, width))

    def action_help(self) -> None:
        """F1: the key map, with this log's keys first."""
        from tl_tui.widgets.help_screen import HelpScreen  # noqa: PLC0415

        self.app.push_screen(HelpScreen(f"{self.LOG_NAME} keys", self.help_keys()))

    def help_keys(self) -> tuple[tuple[str, str], ...]:
        """Every key of this log: the ones every log has, then its own."""
        return (
            ("Up  Down  PgUp  PgDn", "Move in the list"),
            ("Enter", "Open the record"),
            ("/", "Filter the list by text (Enter or Esc leaves the box)"),
            ("F5", "Read the list again"),
            ("Esc", "Clear the filter, then close"),
            *self.HELP_KEYS,
        )

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
        self._cells.clear()
        self._fill(self._key(), reread=True)

    def _cells_of(self, row: Row) -> tuple[str, ...]:
        """The row's cells, worked out once per read of the rows (and per display mode)."""
        return self._cached(row)[0]

    def _cached(self, row: Row) -> tuple[tuple[str, ...], str]:
        found = self._cells.get(id(row))
        if found is not None and found[0] is row:
            return found[1], found[2]
        cells = tuple(self.row_cells(row))
        search = " ".join(cells).lower()
        self._cells[id(row)] = (row, cells, search)
        return cells, search

    def _fill(self, keep: str | None = None, *, reread: bool = False) -> None:
        """Apply the filter box to ``self.rows`` and fill the table; the cursor stays on ``keep``.

        ``reread``: the rows were just read again, so the bar asks for the row's actions again.
        The filter works on the rows already held: no key reads the log again.
        """
        needle = self.filter_text.strip().lower()
        self.shown = [row for row in self.rows if not needle or needle in self._cached(row)[1]]
        self._draw_table(keep)
        self.say(self.summary_text())
        self._show_row(force=reread, defer=True)

    def _draw_table(self, keep: str | None) -> None:
        """Fill the table from ``self.shown``: the columns that vary (``keep_columns`` always),
        the subject shortened with ``…`` to the width left after the other columns; the cursor
        stays on ``keep``. The table gets the first ``WINDOW_ROWS`` rows (more, to reach ``keep``)
        and takes the rest as the cursor comes near the end."""
        names = list(self.columns())
        cells = [list(self._cells_of(row)) for row in self.shown]
        width = self.size.width
        self._drawn_width = width
        total = table_width(width, wide=is_wide(width)) if width > 0 else 10_000
        plan = plan_columns(
            names,
            cells,
            self.keep_columns(),
            total,
            drop=self.drop_order(),
            shrink=self.shrink_columns(),
        )
        shown_names = [names[i] for i in plan.columns]
        shown_cells = [
            [fit_cell(row[i], plan.caps[i]) if i in plan.caps else row[i] for i in plan.columns]
            for row in cells
        ]
        flex = flex_index(shown_names)
        if flex is not None and width > 0:
            room = max(free_width(total, shown_names, shown_cells, flex), MIN_FLEX)
            shown_cells = [
                [fit_cell(cell, room) if i == flex else cell for i, cell in enumerate(row)]
                for row in shown_cells
            ]
        self._planned_names, self._planned_cells = shown_names, shown_cells
        table = self.query_one("#log-table", DataTable)
        self._in_table = 0
        table.clear(columns=True)
        table.add_columns(*shown_names)
        keys = [self.row_key(row) for row in self.shown]
        at = keys.index(keep) if keep in keys else 0
        self._add_rows(max(WINDOW_ROWS, at + EDGE_ROWS + 1))
        if self.shown:
            table.move_cursor(row=at)

    def _add_rows(self, stop: int) -> None:
        """Put rows ``_in_table`` up to ``stop`` of ``shown`` into the table."""
        stop = min(stop, len(self.shown))
        table = self.query_one("#log-table", DataTable)
        names = self._planned_names
        if stop <= self._in_table or len(table.columns) != len(names):
            return  # nothing more to add, or the table is between two sets of columns
        for index in range(self._in_table, stop):
            # Text, not str: a cell is read as markup, and a title such as [a, b] is not markup
            table.add_row(
                *(
                    Text(cell, style=state_style(cell) if name in STATE_COLUMNS else "")
                    for name, cell in zip(names, self._planned_cells[index], strict=True)
                ),
                key=self.row_key(self.shown[index]),
            )
        self._in_table = stop

    def _fill_more(self) -> None:
        """The next chunk of ``shown`` into the table (the view is near the last row held)."""
        if not self.shown:
            return
        if self._in_table < len(self.shown):
            self._add_rows(self._in_table + CHUNK_ROWS)
        else:
            self.rows_exhausted()

    def _fill_all(self) -> None:
        """Every row of ``shown`` into the table (Ctrl+End)."""
        self._add_rows(len(self.shown))
        self.rows_exhausted()

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

    def _show_row(self, *, force: bool = False, defer: bool = False) -> None:
        """Breadcrumb, panel and (when the row changed, or ``force``) a fresh actions bar.

        ``defer``: the list has just been filled (rows read, a filter key). The breadcrumb is
        drawn now; the panel and the bar follow once the list is on screen, for the row that is
        highlighted then, so a run of filter keys reads one panel and not one for each key."""
        self._show_crumb()
        if not defer:
            self._finish_row(force)
            return
        self._row_force = self._row_force or force
        if not self._row_due:
            self._row_due = True
            self.call_after_refresh(self._finish_deferred_row)

    def _finish_deferred_row(self) -> None:
        if not self._row_due:
            return
        self._row_due = False
        force, self._row_force = self._row_force, False
        if self._alive():
            self._show_crumb()
            self._finish_row(force)

    def _finish_row(self, force: bool) -> None:
        row = self.current()
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
        if event.cursor_row >= self._in_table - EDGE_ROWS:
            self._add_rows(self._in_table + CHUNK_ROWS)  # the cursor is near the end of the table
            if (
                self._in_table >= len(self.shown)
                and event.cursor_row >= len(self.shown) - EDGE_ROWS
            ):
                self.rows_exhausted()
        self._show_row()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row opens the record; Esc there returns to this row."""
        event.stop()
        if 0 <= event.cursor_row < len(self.shown):
            self.open_row(self.shown[event.cursor_row])

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.filter_text = event.value
        self.filter_changed(event.value)
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
        self._cells.clear()  # the cells read the mode
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
