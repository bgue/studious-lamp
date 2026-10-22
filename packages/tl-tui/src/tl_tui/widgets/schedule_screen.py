"""The schedules of a project: their snapshots, the look-ahead and the orphaned links (P1-I4).

A full-size modal opened with ``F12``, a ``LogScreen`` (P1-UX2-S3). The list shows the project's
schedules; the panel under it (right of it from 160 columns) holds the table of the snapshots of
the highlighted schedule, newest first, with the current one marked, and describes the highlighted
snapshot, or shows the look-ahead (``l``) or the links whose activity left the schedule (``o``).
The actions bar offers ``c`` compare (the highlighted snapshot with the one before it), ``a``
activities and ``p`` publish (a document controller or an admin: the service decides). Everything
is read and written through the client; the screen shows what the module found and decides nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Input
from tl_core.services.errors import ServiceError
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.views import ScheduleDetailView, ScheduleView, SnapshotView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
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
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

PANELS = ("snapshot", "look_ahead", "orphans")
SNAPSHOT_PAGE = 50  # snapshots read at a time (the service allows 200)
LABEL_TYPES = ("schedule.Schedule", "schedule.ScheduleSnapshot")
NO_SNAPSHOT = "No snapshot is highlighted."


class ScheduleScreen(LogScreen[ScheduleView]):
    """The schedules of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Schedules"
    KEY_HINTS: ClassVar[str] = (
        "Tab table  l look-ahead  o orphans  n/b snapshot pages  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "next_snapshots", "Next snapshots", show=False),
        Binding("b", "previous_snapshots", "Previous snapshots", show=False),
        Binding("l", "look_ahead", "Look-ahead", show=False),
        Binding("o", "orphans", "Orphans", show=False),
    ]

    DEFAULT_CSS = """
    ScheduleScreen #log-table { height: 6; min-height: 4; }
    ScheduleScreen #log-panel { height: 1fr; }
    ScheduleScreen #sc-snapshots { height: 6; }
    ScheduleScreen #log-panel-text { height: auto; }
    """

    def __init__(self, client: ClientInterface, project: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.panel = "snapshot"  # one of PANELS
        self.page_start = 0  # the first snapshot of the page shown, newest first
        self.detail: ScheduleDetailView | None = None  # the highlighted schedule, in full
        self.labels = Labels()  # the plain words of the types and people, loaded with the rows
        self._labelled = False
        self._stale = True  # the snapshots must be read again before they are shown
        self._keep_snapshot: int | None = None
        self._flash = ""  # a note for the status line that the reload would replace

    @property
    def views(self) -> list[ScheduleView]:
        """The schedules as listed, before the filter box."""
        return self.rows

    # --- layout: the snapshot table sits in the panel -------------------------------------

    async def on_mount(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        panel = self.query_one("#log-panel")
        panel.can_focus = False  # Tab goes from the list to the snapshots
        table = DataTable[Any](id="sc-snapshots", cursor_type="row", zebra_stripes=True)
        table.add_columns(*SNAPSHOT_COLUMNS)
        await panel.mount(table, before=0)

    def snapshot_table(self) -> DataTable[Any]:
        return self.query_one("#sc-snapshots", DataTable)

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return SCHEDULE_COLUMNS

    def load_rows(self) -> Sequence[ScheduleView]:
        if not self._labelled:
            self.labels = load_labels(self.client, f"project:{self.project}", LABEL_TYPES)
            self._labelled = True
        found = self.client.list_schedules(self.project)
        self._stale = True  # the highlighted schedule's snapshots may have changed too
        return found

    def reload(self) -> None:
        self._keep_snapshot = self._number()
        super().reload()

    def row_key(self, row: ScheduleView) -> str:
        return row.code

    def row_cells(self, row: ScheduleView) -> Sequence[str]:
        return schedule_cells(row)

    def row_record(self, row: ScheduleView) -> tuple[str, str]:
        return (row.code, row.title)

    def summary_text(self) -> str:
        if self._flash:
            flash, self._flash = self._flash, ""
            return flash
        return schedules_summary(len(self.shown), len(self.rows), text=self.filter_text)

    def open_row(self, row: ScheduleView) -> None:
        open_record(self, self.client, f"project:{self.project}", self.project, self.actor, row.id)

    # --- the snapshots -------------------------------------------------------------------

    def current_schedule(self) -> ScheduleView | None:
        return self.current()

    def current_snapshot(self) -> SnapshotView | None:
        table = self.snapshot_table()
        if self.detail is None or not 0 <= table.cursor_row < len(self.detail.snapshots):
            return None
        return self.detail.snapshots[table.cursor_row]

    def _number(self) -> int | None:
        if not self.query("#sc-snapshots"):
            return None
        snap = self.current_snapshot()
        return snap.number if snap is not None else None

    def _sync(self, view: ScheduleView | None) -> str | None:
        """Make the snapshot table the highlighted schedule's; the error text if unreadable."""
        table = self.snapshot_table()
        if view is None:
            self.detail = None
            table.clear()
            return None
        if self.detail is not None and view.code == self.detail.code and not self._stale:
            return None
        if self.detail is None or view.code != self.detail.code:
            self.page_start = 0  # another schedule starts at its newest snapshots
            self._keep_snapshot = None
        self._stale = False
        table.clear()
        try:
            self.detail = self.client.get_schedule(
                self.project, view.code, limit=SNAPSHOT_PAGE, offset=self.page_start
            )
        except CLIENT_ERRORS as exc:
            self.detail = None
            message = describe_error(exc)
            self.say(message, error=True)
            return message
        for snap in self.detail.snapshots:
            table.add_row(*(Text(cell) for cell in snapshot_cells(snap)), key=str(snap.number))
        numbers = [s.number for s in self.detail.snapshots]
        if numbers:
            keep = self._keep_snapshot
            table.move_cursor(row=numbers.index(keep) if keep in numbers else 0)
        return None

    def panel_text(self, row: ScheduleView | None) -> str:
        """The panel: the highlighted snapshot, the look-ahead, or the orphaned links."""
        failed = self._sync(row)
        if failed is not None:
            return failed
        detail = self.detail
        if detail is None:
            return "No schedule matches."
        snap = self.current_snapshot()
        technical = mode_of(self.app).technical
        lines = schedule_detail_lines(detail, self.labels, technical=technical)
        page = snapshot_page_line(self.page_start, len(detail.snapshots), detail.snapshot_count)
        if page is not None:
            lines.append(page)
        try:
            if self.panel == "look_ahead" and snap is not None:
                answer = self.client.get_look_ahead(self.project, detail.code, snapshot=snap.number)
                lines += ["", *look_ahead_lines(answer, technical=technical)]
            elif self.panel == "orphans":
                links = self.client.list_orphaned_links(self.project, detail.code)
                lines += ["", *orphan_lines(links, technical=technical)]
            elif snap is not None:
                lines += ["", *snapshot_detail_lines(snap, self.labels, technical=technical)]
        except CLIENT_ERRORS as exc:
            lines += ["", describe_error(exc)]
        return "\n".join(lines)

    # --- the actions bar: the keys the screen has always enabled ------------------------------

    def actions_for(self, row: ScheduleView) -> Sequence[LogAction]:
        return [
            LogAction("c", "Compare with the one before", self._compare),
            LogAction("a", "Activities", self._activities),
            LogAction("p", "Publish", self._publish),
        ]

    def _snapshot(self) -> tuple[ScheduleDetailView, SnapshotView]:
        snap = self.current_snapshot()
        if self.detail is None or snap is None:
            raise ServiceError(NO_SNAPSHOT)
        return self.detail, snap

    def _compare(self) -> None:
        """Open the comparison of the highlighted snapshot with the one before it."""
        detail, snap = self._snapshot()
        self.app.push_screen(CompareScreen(self.client, self.project, detail.code, snap.number))

    def _activities(self) -> None:
        """Open the activities of the highlighted snapshot."""
        detail, snap = self._snapshot()
        self.app.push_screen(ActivityScreen(self.client, self.project, detail.code, snap.number))

    def _publish(self) -> None:
        """Make the highlighted snapshot the current one (the service checks the role)."""
        _, snap = self._snapshot()
        self.client.publish_schedule_snapshot(
            PublishScheduleSnapshot(
                actor=self.actor,
                source="tui",
                scope=f"project:{self.project}",
                snapshot_id=snap.id,
            )
        )
        self._flash = f"Published {snap.key}."  # shown once, in place of the reload's summary

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """A schedule (the list) or a snapshot (the panel) was highlighted: draw the panel."""
        event.stop()
        event.prevent_default()  # the base would do the same once, for the list alone
        self._show_row()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a schedule or a snapshot opens its full record; Esc there comes back here."""
        event.stop()
        event.prevent_default()
        row = event.cursor_row
        record_id: str | None = None
        if event.data_table.id == "log-table":
            if 0 <= row < len(self.shown):
                record_id = self.shown[row].id
        elif self.detail is not None and 0 <= row < len(self.detail.snapshots):
            record_id = self.detail.snapshots[row].id
        if record_id is None:
            return
        open_record(
            self, self.client, f"project:{self.project}", self.project, self.actor, record_id
        )

    # --- the log's own keys --------------------------------------------------------------

    def action_next_snapshots(self) -> None:
        """Show the next page of older snapshots."""
        if isinstance(self.focused, Input) or self.detail is None:
            return  # the key is text
        if self.page_start + len(self.detail.snapshots) >= self.detail.snapshot_count:
            self.say("These are the oldest snapshots.")
            return
        self.page_start += SNAPSHOT_PAGE
        self._stale = True
        self._keep_snapshot = None
        self._show_row()

    def action_previous_snapshots(self) -> None:
        """Show the previous page, towards the newest snapshots."""
        if isinstance(self.focused, Input) or self.detail is None:
            return  # the key is text
        if self.page_start == 0:
            self.say("These are the newest snapshots.")
            return
        self.page_start = max(0, self.page_start - SNAPSHOT_PAGE)
        self._stale = True
        self._keep_snapshot = None
        self._show_row()

    def action_look_ahead(self) -> None:
        """Show the look-ahead of the highlighted snapshot in the panel, or go back."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.panel = "snapshot" if self.panel == "look_ahead" else "look_ahead"
        self._show_row()

    def action_orphans(self) -> None:
        """Show the links whose activity left the schedule in the panel, or go back."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.panel = "snapshot" if self.panel == "orphans" else "orphans"
        self._show_row()
