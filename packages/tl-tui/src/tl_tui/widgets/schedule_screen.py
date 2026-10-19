"""The schedules of a project: their snapshots, the look-ahead and the orphaned links (P1-I4).

A full-size modal opened with ``F12``. The upper table lists the project's schedules; the lower
table lists the snapshots of the highlighted one, newest first, with the current one marked. The
panel under them describes the highlighted snapshot, or shows the look-ahead (``l``) or the links
whose activity left the schedule (``o``). ``c`` compares the highlighted snapshot with the one
before it, ``a`` opens its activities, and ``p`` publishes it (a document controller or an admin:
the service decides). Everything is read and written through the client; the screen shows what the
module found and decides nothing.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.views import ScheduleDetailView, ScheduleView, SnapshotView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schedule_text import (
    SCHEDULE_COLUMNS,
    SNAPSHOT_COLUMNS,
    look_ahead_lines,
    orphan_lines,
    schedule_cells,
    schedule_detail_lines,
    schedules_summary,
    snapshot_cells,
    snapshot_detail_lines,
    snapshot_page_line,
)
from tl_tui.widgets.activity_screen import ActivityScreen
from tl_tui.widgets.compare_screen import CompareScreen

PANELS = ("snapshot", "look_ahead", "orphans")
SNAPSHOT_PAGE = 50  # snapshots read at a time (the service allows 200)


class ScheduleScreen(ModalScreen[None]):
    """The schedules of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "Tab table  c compare  a activities  l look-ahead  o orphans  p publish  "
        "n/b snapshot pages  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "next_snapshots", "Next snapshots", show=False),
        Binding("b", "previous_snapshots", "Previous snapshots", show=False),
        Binding("c", "compare", "Compare", show=False),
        Binding("a", "activities", "Activities", show=False),
        Binding("l", "look_ahead", "Look-ahead", show=False),
        Binding("o", "orphans", "Orphans", show=False),
        Binding("p", "publish", "Publish", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    ScheduleScreen { background: $surface; }
    ScheduleScreen > Vertical { padding: 0 1; }
    ScheduleScreen #sc-title { text-style: bold; height: 1; }
    ScheduleScreen #sc-filter { height: 3; }
    ScheduleScreen #sc-schedules { height: 7; }
    ScheduleScreen #sc-snapshots { height: 9; }
    ScheduleScreen #sc-detail { height: 1fr; border-top: solid $accent; padding: 0 1; }
    ScheduleScreen #sc-status { height: 1; }
    ScheduleScreen #sc-hints { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, project: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.text = ""
        self.panel = "snapshot"  # one of PANELS
        self.page_start = 0  # the first snapshot of the page shown, newest first
        self.views: list[ScheduleView] = []  # as listed, before the filter
        self.shown: list[ScheduleView] = []
        self.detail: ScheduleDetailView | None = None  # the highlighted schedule, in full

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Schedules of {self.project}", markup=False, id="sc-title")
            yield Input(placeholder="Filter by code or title", id="sc-filter")
            yield DataTable[str](id="sc-schedules", cursor_type="row", zebra_stripes=True)
            yield DataTable[str](id="sc-snapshots", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="sc-detail")
            yield Static("", markup=False, id="sc-status")
            yield Static(self.KEY_HINTS, markup=False, id="sc-hints")

    def on_mount(self) -> None:
        self.query_one("#sc-schedules", DataTable).add_columns(*SCHEDULE_COLUMNS)
        self.query_one("#sc-snapshots", DataTable).add_columns(*SNAPSHOT_COLUMNS)
        self.reload()
        self.query_one("#sc-schedules", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the schedules again and keep the highlighted schedule and snapshot in place."""
        keep = self._code()
        keep_snapshot = self._number()
        try:
            self.views = self.client.list_schedules(self.project)
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep, keep_snapshot)

    def _fill(self, keep: str | None = None, keep_snapshot: int | None = None) -> None:
        """Apply the filter to ``self.views``, fill the schedule table and load the highlighted."""
        needle = self.text.strip().lower()
        self.shown = [
            v
            for v in self.views
            if not needle or needle in v.code.lower() or needle in v.title.lower()
        ]
        table = self.query_one("#sc-schedules", DataTable)
        table.clear()
        for view in self.shown:
            # Text, not str: a cell is read as markup, and a title such as [a, b] is not markup
            table.add_row(*(Text(cell) for cell in schedule_cells(view)), key=view.code)
        if self.shown:
            codes = [v.code for v in self.shown]
            table.move_cursor(row=codes.index(keep) if keep in codes else 0)
        self.query_one("#sc-status", Static).update(
            schedules_summary(len(self.shown), len(self.views), text=self.text)
        )
        self._load_schedule(keep_snapshot)

    def _code(self) -> str | None:
        view = self.current_schedule()
        return view.code if view is not None else None

    def _number(self) -> int | None:
        view = self.current_snapshot()
        return view.number if view is not None else None

    def current_schedule(self) -> ScheduleView | None:
        table = self.query_one("#sc-schedules", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def current_snapshot(self) -> SnapshotView | None:
        table = self.query_one("#sc-snapshots", DataTable)
        if self.detail is None or not 0 <= table.cursor_row < len(self.detail.snapshots):
            return None
        return self.detail.snapshots[table.cursor_row]

    def _load_schedule(self, keep_snapshot: int | None = None) -> None:
        """Read the highlighted schedule with its snapshots and fill the snapshot table."""
        table = self.query_one("#sc-snapshots", DataTable)
        table.clear()
        view = self.current_schedule()
        if view is None:
            self.detail = None
            self.query_one("#sc-detail", Static).update("No schedule matches.")
            return
        if self.detail is None or view.code != self.detail.code:
            self.page_start = 0  # another schedule starts at its newest snapshots
        try:
            self.detail = self.client.get_schedule(
                self.project, view.code, limit=SNAPSHOT_PAGE, offset=self.page_start
            )
        except CLIENT_ERRORS as exc:
            self.detail = None
            message = describe_error(exc)
            self.query_one("#sc-detail", Static).update(message)
            self._say(message, error=True)
            return
        for snap in self.detail.snapshots:
            table.add_row(*(Text(cell) for cell in snapshot_cells(snap)), key=str(snap.number))
        numbers = [s.number for s in self.detail.snapshots]
        if numbers:
            table.move_cursor(row=numbers.index(keep_snapshot) if keep_snapshot in numbers else 0)
        self._describe()

    def _describe(self) -> None:
        """The panel: the highlighted snapshot, the look-ahead, or the orphaned links."""
        panel = self.query_one("#sc-detail", Static)
        detail = self.detail
        if detail is None:
            panel.update("No schedule matches.")
            return
        snap = self.current_snapshot()
        lines = schedule_detail_lines(detail)
        page = snapshot_page_line(self.page_start, len(detail.snapshots), detail.snapshot_count)
        if page is not None:
            lines.append(page)
        try:
            if self.panel == "look_ahead" and snap is not None:
                answer = self.client.get_look_ahead(self.project, detail.code, snapshot=snap.number)
                lines += ["", *look_ahead_lines(answer)]
            elif self.panel == "orphans":
                links = self.client.list_orphaned_links(self.project, detail.code)
                lines += ["", *orphan_lines(links)]
            elif snap is not None:
                lines += ["", *snapshot_detail_lines(snap)]
        except CLIENT_ERRORS as exc:
            lines += ["", describe_error(exc)]
        panel.update("\n".join(lines))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#sc-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        if event.data_table.id != "sc-schedules":
            self._describe()
            return
        # Filling the table raises this event again, after `_fill` has loaded the schedule and put
        # the snapshot cursor back: only a schedule other than the loaded one is loaded now.
        view = self.current_schedule()
        if view is not None and (self.detail is None or view.code != self.detail.code):
            self._load_schedule()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self._fill(self._code(), self._number())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#sc-schedules", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def action_next_snapshots(self) -> None:
        """Show the next page of older snapshots."""
        if isinstance(self.focused, Input) or self.detail is None:
            return  # the key is text
        if self.page_start + len(self.detail.snapshots) >= self.detail.snapshot_count:
            self._say("These are the oldest snapshots.")
            return
        self.page_start += SNAPSHOT_PAGE
        self._load_schedule()

    def action_previous_snapshots(self) -> None:
        """Show the previous page, towards the newest snapshots."""
        if isinstance(self.focused, Input) or self.detail is None:
            return  # the key is text
        if self.page_start == 0:
            self._say("These are the newest snapshots.")
            return
        self.page_start = max(0, self.page_start - SNAPSHOT_PAGE)
        self._load_schedule()

    def action_compare(self) -> None:
        """Open the comparison of the highlighted snapshot with the one before it."""
        if isinstance(self.focused, Input):
            return  # the key is text
        snap = self.current_snapshot()
        if self.detail is None or snap is None:
            self._say("No snapshot is highlighted.")
            return
        self.app.push_screen(
            CompareScreen(self.client, self.project, self.detail.code, snap.number)
        )

    def action_activities(self) -> None:
        """Open the activities of the highlighted snapshot."""
        if isinstance(self.focused, Input):
            return  # the key is text
        snap = self.current_snapshot()
        if self.detail is None or snap is None:
            self._say("No snapshot is highlighted.")
            return
        self.app.push_screen(
            ActivityScreen(self.client, self.project, self.detail.code, snap.number)
        )

    def action_look_ahead(self) -> None:
        """Show the look-ahead of the highlighted snapshot in the panel, or go back."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.panel = "snapshot" if self.panel == "look_ahead" else "look_ahead"
        self._describe()

    def action_orphans(self) -> None:
        """Show the links whose activity left the schedule in the panel, or go back."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.panel = "snapshot" if self.panel == "orphans" else "orphans"
        self._describe()

    def action_publish(self) -> None:
        """Make the highlighted snapshot the current one (the service checks the role)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        snap = self.current_snapshot()
        if snap is None:
            self._say("No snapshot is highlighted.")
            return
        try:
            self.client.publish_schedule_snapshot(
                PublishScheduleSnapshot(
                    actor=self.actor,
                    source="tui",
                    scope=f"project:{self.project}",
                    snapshot_id=snap.id,
                )
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say(f"Published {snap.key}.")  # last: the reload rewrites the line

    def action_filter(self) -> None:
        self.query_one("#sc-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#sc-filter", Input).value = ""
            self.query_one("#sc-schedules", DataTable).focus()
            return
        self.dismiss(None)
