# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""The schedules of a project: their snapshots, the look-ahead and the orphaned links (P1-I4).

A full-size modal opened with ``F12``. The upper table lists the project's schedules; the lower
table lists the snapshots of the highlighted one, newest first, with the current one marked. The
panel under them describes the highlighted snapshot, or shows the look-ahead (``l``) or the links
whose activity left the schedule (``o``). ``c`` compares the highlighted snapshot with the one
before it, ``a`` opens its activities, and ``p`` publishes it (a document controller or an admin:
the service decides). Everything is read and written through the client; the screen shows what the
module found and decides nothing.


STUB (P1-I4-T09a1): `reload`, `_fill`, `_load_schedule`, `_describe` and `action_publish` are
`NotImplementedError`; the layout, the bindings, the event handlers, the other actions and the text
helpers (`tl_tui/schedule_text.py`) are written. The ticket fills the five bodies by their STEPS
comments.
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
)
from tl_tui.widgets.activity_screen import ActivityScreen
from tl_tui.widgets.compare_screen import CompareScreen

PANELS = ("snapshot", "look_ahead", "orphans")


class ScheduleScreen(ModalScreen[None]):
    """The schedules of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "Tab table  c compare  a activities  l look-ahead  o orphans  p publish  / filter  "
        "F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
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
        # STEPS
        # 1. `keep = self._code()` and `keep_snapshot = self._number()`: the highlighted
        #    schedule and snapshot, to put the cursors back.
        # 2. Read `self.views = self.client.list_schedules(self.project)`. On
        #    `CLIENT_ERRORS` say `describe_error(exc)` with `self._say(..., error=True)`
        #    and return (keep what is shown).
        # 3. Call `self._fill(keep, keep_snapshot)`.
        raise NotImplementedError

    def _fill(self, keep: str | None = None, keep_snapshot: int | None = None) -> None:
        """Apply the filter to ``self.views``, fill the schedule table and load the highlighted."""
        # STEPS
        # 1. `needle = self.text.strip().lower()`; `self.shown` is the views whose code
        #    or title holds the needle in any case (all of them when the needle is
        #    empty).
        # 2. Fill `#sc-schedules`: `table.clear()`, then one `add_row` per shown
        #    schedule with `Text(cell)` for each cell of `schedule_cells(view)` (a cell
        #    is read as markup, a `Text` is not) and `key=view.code`.
        # 3. Put the cursor on the row of `keep` when it is still shown, else on row 0
        #    (`table.move_cursor(row=...)`), when there are rows.
        # 4. Write `schedules_summary(len(self.shown), len(self.views), text=self.text)`
        #    to `#sc-status` and call `self._load_schedule(keep_snapshot)`.
        raise NotImplementedError

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
        # STEPS
        # 1. Clear `#sc-snapshots`. The highlighted schedule is
        #    `self.current_schedule()`; with none, set `self.detail = None`, write `No
        #    schedule matches.` to `#sc-detail` and return.
        # 2. Read `self.detail = self.client.get_schedule(self.project, view.code)`. On
        #    `CLIENT_ERRORS` set `self.detail = None`, write `describe_error(exc)` to
        #    `#sc-detail` and (as an error) to the status line, and return.
        # 3. Add one row per snapshot of `self.detail.snapshots` (newest first, as
        #    given) with `Text(cell)` for each cell of `snapshot_cells(snap)` and
        #    `key=str(snap.number)`.
        # 4. Put the cursor on the row of `keep_snapshot` when it is among the
        #    snapshots, else on row 0, when there are rows. Then call
        #    `self._describe()`.
        raise NotImplementedError

    def _describe(self) -> None:
        """The panel: the highlighted snapshot, the look-ahead, or the orphaned links."""
        # STEPS
        # 1. `panel` is `#sc-detail`. With no `self.detail` write `No schedule matches.`
        #    and return.
        # 2. `snap = self.current_snapshot()`; `lines =
        #    schedule_detail_lines(self.detail)`.
        # 3. In a `try` that catches `CLIENT_ERRORS`: when `self.panel == "look_ahead"`
        #    and there is a snapshot, append an empty line and
        #    `look_ahead_lines(self.client.get_look_ahead(self.project,
        #    self.detail.code, snapshot=snap.number))`; when `self.panel == "orphans"`
        #    append an empty line and
        #    `orphan_lines(self.client.list_orphaned_links(self.project,
        #    self.detail.code))`; otherwise, with a snapshot, append an empty line and
        #    `snapshot_detail_lines(snap)`.
        # 4. On a client failure append an empty line and `describe_error(exc)` instead.
        #    Write the lines joined by newlines to the panel.
        raise NotImplementedError

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
        # STEPS
        # 1. The key is text while an `Input` has focus: `if isinstance(self.focused,
        #    Input): return` first.
        # 2. `snap = self.current_snapshot()`; with none say `No snapshot is
        #    highlighted.` and return.
        # 3. Send `PublishScheduleSnapshot(actor=self.actor, source="tui",
        #    scope=f"project:{self.project}", snapshot_id=snap.id)` with
        #    `self.client.publish_schedule_snapshot(...)`. On `CLIENT_ERRORS` say
        #    `describe_error(exc)` as an error and return: the service decides who may
        #    publish (the screen checks no role) and nothing was sent.
        # 4. Read again with `self.reload()`, then say `Published <snap.key>.` (last:
        #    the reload rewrites the status line).
        raise NotImplementedError

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
