"""The activities of a schedule snapshot, one activity with its neighbours and float trend (P1-I4).

A full-size modal opened from the schedule screen with ``a``. The table lists the activities of
the snapshot in file order, a page at a time; the panel under it describes the highlighted one:
its dates, float, the relationships that name it and how its float moved through the published
snapshots. ``c`` keeps only the critical activities, ``/`` filters by id or name, ``n`` and ``b``
page forward and back. Everything is read through the client; the screen shows what the module
found and decides nothing.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_schedule.registry import ActivityRow
from tl_mod_schedule.views import ActivityPage

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schedule_text import (
    ACTIVITY_COLUMNS,
    activity_cells,
    activity_detail_lines,
    page_line,
    trend_lines,
)

PAGE = 200


class ActivityScreen(ModalScreen[None]):
    """The activities of snapshot ``number`` of schedule ``code`` (``None``: the current one)."""

    KEY_HINTS: ClassVar[str] = (
        "c critical only  n next page  b previous page  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "critical", "Critical", show=False),
        Binding("n", "next_page", "Next page", show=False),
        Binding("b", "previous_page", "Previous page", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    ActivityScreen { background: $surface; }
    ActivityScreen > Vertical { padding: 0 1; }
    ActivityScreen #ac-title { text-style: bold; height: 1; }
    ActivityScreen #ac-filter { height: 3; }
    ActivityScreen #ac-table { height: 1fr; min-height: 6; }
    ActivityScreen #ac-detail { height: 18; border-top: solid $accent; padding: 0 1; }
    ActivityScreen #ac-status { height: 1; }
    ActivityScreen #ac-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self, client: ClientInterface, project: str, code: str, number: int | None = None
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.code = code
        self.number = number
        self.text = ""
        self.critical_only = False
        self.first = 0
        self.page: ActivityPage | None = None
        self.shown: list[ActivityRow] = []

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Activities of {self.code}", markup=False, id="ac-title")
            yield Input(placeholder="Filter by activity id or name", id="ac-filter")
            yield DataTable[str](id="ac-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="ac-detail")
            yield Static("", markup=False, id="ac-status")
            yield Static(self.KEY_HINTS, markup=False, id="ac-hints")

    def on_mount(self) -> None:
        self.query_one("#ac-table", DataTable).add_columns(*ACTIVITY_COLUMNS)
        self.reload()
        self.query_one("#ac-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the page again and keep the highlighted activity where it is."""
        keep = self._current_id()
        try:
            self.page = self.client.list_activities(
                self.project,
                self.code,
                snapshot=self.number,
                critical=True if self.critical_only else None,
                q=self.text.strip() or None,
                limit=PAGE,
                offset=self.first,
            )
        except CLIENT_ERRORS as exc:
            self.page = None
            self.shown = []
            self.query_one("#ac-table", DataTable).clear()
            self.query_one("#ac-detail", Static).update(describe_error(exc))
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep)

    def _fill(self, keep: str | None = None) -> None:
        """Fill the table from ``self.page`` and describe the highlighted activity."""
        page = self.page
        if page is None:
            return
        self.shown = list(page.rows)
        table = self.query_one("#ac-table", DataTable)
        table.clear()
        for a in self.shown:
            # Text, not str: a cell is read as markup, and a name such as [a, b] is not markup
            table.add_row(*(Text(cell) for cell in activity_cells(a)), key=a.activity_id)
        if self.shown:
            ids = [a.activity_id for a in self.shown]
            table.move_cursor(row=ids.index(keep) if keep in ids else 0)
        self.query_one("#ac-title", Static).update(f"Activities of {page.snapshot_key}")
        self._say(page_line(page, critical=self.critical_only, text=self.text))
        self._describe()

    def _current_id(self) -> str | None:
        row = self.current()
        return row.activity_id if row is not None else None

    def current(self) -> ActivityRow | None:
        table = self.query_one("#ac-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """The highlighted activity with its relationships and its float trend."""
        panel = self.query_one("#ac-detail", Static)
        row = self.current()
        if row is None:
            panel.update("No activity matches.")
            return
        try:
            detail = self.client.get_schedule_activity(
                self.project, self.code, row.activity_id, snapshot=self.number
            )
        except CLIENT_ERRORS as exc:
            message = describe_error(exc)
            panel.update(message)
            self._say(message, error=True)
            return
        lines = activity_detail_lines(detail)
        try:
            trend = self.client.get_activity_trend(self.project, self.code, row.activity_id)
            lines.append("")
            lines.extend(trend_lines(trend))
        except CLIENT_ERRORS as exc:
            lines.append("")
            lines.append(describe_error(exc))
        panel.update("\n".join(lines))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#ac-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self.first = 0
        self.reload()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#ac-table", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def action_critical(self) -> None:
        """Show only the critical activities, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.critical_only = not self.critical_only
        self.first = 0
        self.reload()

    def action_next_page(self) -> None:
        """The next page, when there is one."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.page is None or self.first + PAGE >= self.page.total:
            self._say("This is the last page.")
            return
        self.first += PAGE
        self.reload()

    def action_previous_page(self) -> None:
        """The previous page, when there is one."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.first == 0:
            self._say("This is the first page.")
            return
        self.first = max(0, self.first - PAGE)
        self.reload()

    def action_filter(self) -> None:
        self.query_one("#ac-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#ac-filter", Input).value = ""
            self.query_one("#ac-table", DataTable).focus()
            return
        self.dismiss(None)
