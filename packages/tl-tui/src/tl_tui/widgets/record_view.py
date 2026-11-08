"""Record view: header and the Details, Properties, Links, Activity, Trace, Thread, Files and
Insights tabs.

Esc posts `CloseRecord`, [ and ] post `StepRecord`, h opens the Activity tab, 9 the Insights
tab. The view reads only through `ClientInterface`; it never touches the ledger or services
directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane
from tl_core.services.psets import SetPsetValues
from tl_core.settings.layers import project_of_scope
from tl_mod_schemareg.handlers.adoption import AdoptSchemaSet

from tl_tui.client import ClientInterface
from tl_tui.details import details_for, rows_page
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import forget_labels, load_labels
from tl_tui.layout import render, state_style
from tl_tui.messages import CloseRecord, RecordChanged, StatusMessage, StepRecord
from tl_tui.reads import Reads
from tl_tui.record_text import (  # noqa: F401 - the moved names stay importable from here
    _EVENT_WORDS,
    _or_empty,
    _plain_keys,
    _sorted_keys,
    badges_text,
    details_lines,
    event_label,
    event_summary,
    header_parts,
    history_cells,
    history_columns,
)
from tl_tui.widgets.activity_tab import ActivityTab
from tl_tui.widgets.file_panel import FilePanel
from tl_tui.widgets.insights_tab import InsightsTab
from tl_tui.widgets.links_tab import LinksTab
from tl_tui.widgets.psets_tab import PsetsTab
from tl_tui.widgets.thread_tab import ThreadTab
from tl_tui.widgets.trace_tab import TraceTab

__all__ = [
    "RecordView",
    "TABS",
    "badges_text",
    "details_lines",
    "event_label",
    "event_summary",
    "header_parts",
    "history_cells",
    "history_columns",
]

TABS: dict[str, str] = {
    "details": "tab-details",
    "psets": "tab-psets",
    "links": "tab-links",
    "activity": "tab-activity",  # P2-INS INS-A3: where History was (h, 4)
    "trace": "tab-trace",
    "thread": "tab-thread",  # P1-I7 WS-B
    "files": "tab-files",  # P1-UX2-S4: only while the record has files
    "insights": "tab-insights",  # P2-INS: the Insights pane (9)
}


class RecordView(Vertical, can_focus=True):
    """Opened by the app for ``OpenRecord``. Posts `CloseRecord` on Esc and `StepRecord` on [ ]."""

    DEFAULT_CSS = """
    RecordView #rv-banner { height: auto; display: none; background: $warning 35%; padding: 0 1; }
    """

    KEY_HINTS: ClassVar[str] = (
        "Esc back  [ ] prev/next  1-6 tabs  T thread  9 insights  e edit  "
        "+ add property (Properties tab)  l link  w workflow  t trace  R tray"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", show=False),
        Binding("left_square_bracket", "step(-1)", show=False),
        Binding("right_square_bracket", "step(1)", show=False),
        Binding("h", "history", show=False),
        Binding("e", "edit", show=False),
        Binding("plus", "add_property", show=False),
        Binding("1", "tab('details')", show=False),
        Binding("2", "tab('psets')", show=False),
        Binding("3", "tab('links')", show=False),
        Binding("4", "tab('activity')", show=False),
        Binding("5", "tab('trace')", show=False),
        Binding("T", "tab('thread')", show=False),
        Binding("6", "tab('files')", show=False),
        Binding("9", "tab('insights')", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        key: str,
        *,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.key = key
        self.record: dict[str, Any] | None = None
        self._labels: Labels | None = None
        self._badges_text: str = ""  # the last header badges, redrawn on a mode switch
        self.details: str = ""  # the Details tab as text (for tests and the screen tickets)
        self.has_files = False  # the Files tab is shown only then

    def compose(self) -> ComposeResult:
        yield Static("", id="rv-header", markup=False)
        yield Static("", id="rv-banner", markup=False)
        with TabbedContent(initial="tab-details", id="rv-tabs"):
            with TabPane("Details", id="tab-details"):
                with VerticalScroll():
                    yield Static("", id="rv-details", markup=False)
            with TabPane("Properties", id="tab-psets"):
                yield PsetsTab(self.client, self.scope, id="psets-tab")
            with TabPane("Links", id="tab-links"):
                yield LinksTab(self.client, self.scope, actor=self._actor(), id="links-tab")
            with TabPane("Activity", id="tab-activity"):
                yield ActivityTab(self.client, self.scope, actor=self._actor(), id="activity-tab")
            with TabPane("Trace", id="tab-trace"):
                yield TraceTab(self.client, self.scope, id="trace-tab")
            with TabPane("Thread", id="tab-thread"):
                yield ThreadTab(self.client, self.scope, actor=self._actor(), id="thread-tab")
            with TabPane("Files", id="tab-files"):  # hidden until the record has files
                yield FilePanel(self.client, id="files-tab")
            with TabPane("Insights", id="tab-insights"):
                yield InsightsTab(id="insights-tab")

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))

    def on_mount(self) -> None:
        self.query_one("#rv-tabs", TabbedContent).hide_tab("tab-files")
        self.reload()

    def reload(self) -> None:
        """Re-read the record, then redraw. On a client error, keep the display.

        Details and header are drawn at once. A tab that needs reads of its own (Properties,
        Links, Activity, Trace, Thread, Insights) reads them when it is first shown, and again
        after the next ``reload`` if it is the tab on show; the Files list is read in the
        background."""
        reads = Reads(self.client)
        try:
            record = reads.get_record(self.scope, self.key)
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.record = record
        self._badges_text = self._badges(record, reads)
        self._draw_header(record, self._badges_text)
        self._draw_details(record, reads)
        self._tabs_read = set()
        if record is None:
            self.post_message(StatusMessage(f"No record {self.key}", "error"))
        else:
            self._read_tab(self.query_one("#rv-tabs", TabbedContent).active)
            self.query_one("#files-tab", FilePanel).show(str(record["id"]))

    def _read_tab(self, pane: str) -> None:
        """Give the tab ``pane`` the current record, once (a ``reload`` makes it read again)."""
        record = self.record
        if record is None or pane in self._tabs_read:
            return
        tab = {
            TABS["psets"]: "#psets-tab",
            TABS["links"]: "#links-tab",
            TABS["trace"]: "#trace-tab",
            TABS["thread"]: "#thread-tab",
            TABS["activity"]: "#activity-tab",
            TABS["insights"]: "#insights-tab",
        }.get(pane)
        if tab is None:
            return
        self._tabs_read.add(pane)
        self.query_one(tab).show_record(record)  # pyright: ignore[reportAttributeAccessIssue]

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        event.stop()
        if event.pane.id is not None:
            self._read_tab(event.pane.id)

    def _labels_for(self, record: dict[str, Any]) -> Labels:
        """The labels, loaded once per view (a retarget makes a new view)."""
        if self._labels is None:
            self._labels = load_labels(self.client, self.scope, ("core.Record", record["type"]))
        return self._labels

    def _draw_details(self, record: dict[str, Any] | None, client: Any = None) -> None:
        """The Details tab: the type's rows, technical rows only in technical mode. ``client`` is
        what the rows read through (a ``Reads`` for the length of one refresh)."""
        body = self.query_one("#rv-details", Static)
        if record is None:
            self.details = ""
            body.update("")
            return
        rows = details_for(
            client if client is not None else self.client,
            project_of_scope(self.scope) or "",
            record,
            self._labels_for(record),
            mode_of(self.app),
        )
        page = rows_page(rows, technical=True)  # the rows are already filtered for the mode
        self.details = details_lines(rows)
        body.update(render(page, identity=False))

    def _current_labels(self) -> Labels:
        """The labels for the shown record; no labels before a record is read."""
        return Labels() if self.record is None else self._labels_for(self.record)

    def refresh_for_display_mode(self) -> None:
        """Draw the header, Details, Activity and Properties again; the tab stays."""
        if self.record is None:
            return
        self._draw_header(self.record, self._badges_text)
        self._draw_details(self.record)
        self.query_one("#activity-tab", ActivityTab).refresh_for_display_mode()
        self.query_one("#psets-tab", PsetsTab).refresh_for_display_mode()

    def _badges(self, record: dict[str, Any] | None, client: Any = None) -> str:
        """``since <time>`` (workflow state) and link counts for the header; empty when unknown.

        Both come from joins in the services (`workflow_status`, `link_counts`). A client that
        cannot answer, or a record without a workflow, just leaves the badges out.
        """
        if record is None:
            return ""
        entered: str | None = None
        try:
            entered = (client or self.client).workflow_status(record["id"]).entered_at
        except (*CLIENT_ERRORS, NotImplementedError):
            pass
        try:
            counts = self.client.link_counts([record["id"]]).get(record["id"])
        except (*CLIENT_ERRORS, NotImplementedError):
            counts = None
        return badges_text(entered, counts)

    def _draw_header(self, record: dict[str, Any] | None, badges: str = "") -> None:
        header = self.query_one("#rv-header", Static)
        if record is None:
            header.update(f"{self.key} · not found")
            return
        parts = header_parts(record, badges, technical=mode_of(self.app).technical)
        text = Text(f"{parts.identity}\n")
        text.append(
            parts.status, style=state_style(parts.status) or None
        )  # the state colour (skill tui-layout)
        text.append(f"{parts.version} · ")
        text.append(parts.mark, style=state_style(parts.mark) or None)
        text.append(parts.rest)
        header.update(text)

    def note_remote_update(self, actor: str, version: int, when: datetime | None = None) -> None:
        """Show "! Updated by <actor> (now v<n>)" under the header (someone else changed it).

        With ``when`` the line also says at what time. A later call replaces the line.
        """
        at = f" at {when:%H:%M:%S}" if when is not None else ""
        banner = self.query_one("#rv-banner", Static)
        banner.update(f"! Updated by {actor}{at} (now v{version})")
        banner.display = True

    def clear_remote_update(self) -> None:
        """Hide the "Updated by" line."""
        banner = self.query_one("#rv-banner", Static)
        banner.update("")
        banner.display = False

    def on_record_changed(self, message: RecordChanged) -> None:
        # Not stopped: the message keeps bubbling so the app can refresh the grid.
        if self.record is not None and message.record_id == self.record["id"]:
            self.clear_remote_update()  # the user's own change: the notice is about older news
            self.reload()

    # --- actions (keys) ----------------------------------------------------------------------

    def action_close(self) -> None:
        self.post_message(CloseRecord())

    def action_step(self, delta: int) -> None:
        self.post_message(StepRecord(delta))

    def action_history(self) -> None:
        self.show_tab("activity")

    def action_tab(self, name: str) -> None:
        if name == "files" and not self.has_files:
            return  # the tab is not there while the record has no files
        self.show_tab(name)

    def on_file_panel_listed(self, message: FilePanel.Listed) -> None:
        """The record's files were read: the Files tab is there when there are any."""
        message.stop()
        tabs = self.query_one("#rv-tabs", TabbedContent)
        self.has_files = message.count > 0
        if self.has_files:
            tabs.show_tab("tab-files")
        else:
            if tabs.active == "tab-files":
                tabs.active = "tab-details"
            tabs.hide_tab("tab-files")

    def on_file_panel_note(self, message: FilePanel.Note) -> None:
        message.stop()
        self.post_message(StatusMessage(message.text, "error" if message.error else "info"))

    def show_tab(self, name: str) -> None:
        """Make the tab named in ``TABS`` active (``details``, ``psets``, ... ``thread``)."""
        self.query_one("#rv-tabs", TabbedContent).active = TABS[name]
        if name == "files":  # its keys (Up, Down, v, Enter) are the panel's
            self.query_one("#files-tab", FilePanel).call_after_refresh(self._focus_files)

    def _focus_files(self) -> None:
        self.query_one("#files-tab", FilePanel).focus()

    def _edit_body(self, record: dict[str, Any]) -> bool:
        """Open the body edit form when ``record`` is an object-backed extension record."""
        from tl_tui.extension_columns import form_for_record_type  # noqa: PLC0415
        from tl_tui.widgets.extension_edit_form import ExtensionEditForm  # noqa: PLC0415

        form = form_for_record_type(self.client, record["type"])
        if form is None or form.storage_mode != "object-backed":
            return False
        try:
            stored = self.client.get_record_body(record["id"])
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return True

        def saved(done: bool | None) -> None:
            if done:
                self.post_message(RecordChanged(record["id"]))

        self.app.push_screen(
            ExtensionEditForm(self.client, self.scope, record, form, stored.body), saved
        )
        return True

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """``+`` adds a property on the Properties tab only (other tabs bind it to their own)."""
        if action == "add_property":
            return self.query_one("#rv-tabs", TabbedContent).active == TABS["psets"]
        return True

    def action_add_property(self) -> None:
        """Open the Add property form; the form sends nothing, this sends its command."""
        record = self.record
        if record is None:
            return
        from tl_tui.widgets.add_property_form import open_add_property  # noqa: PLC0415
        from tl_tui.widgets.schema_screen import SchemaWorkbenchScreen  # noqa: PLC0415

        actor = self._actor()

        def send(cmd: SetPsetValues) -> None:
            try:
                self.client.set_pset_values(cmd)
            except CLIENT_ERRORS as exc:
                self.post_message(StatusMessage(describe_error(exc), "error"))
                return
            self.post_message(StatusMessage("Property added", "info"))
            self.post_message(RecordChanged(record["id"]))

        def workbench(package: str) -> None:
            self.app.push_screen(
                SchemaWorkbenchScreen(self.client, self.scope, actor, package=package)
            )

        def adopt(cmd: AdoptSchemaSet) -> bool:
            try:
                self.client.schemareg_command("AdoptSchemaSet", cmd)
            except CLIENT_ERRORS as exc:
                self.post_message(StatusMessage(describe_error(exc), "error"))
                return False
            forget_labels(self.client)  # an adopted package can move code lists and labels
            self.post_message(StatusMessage(f"Adopted {cmd.pset} for {cmd.project}", "info"))
            return True

        try:
            open_add_property(
                self,
                self.client,
                scope=self.scope,
                record_id=record["id"],
                actor=actor,
                is_admin=bool(getattr(self.app, "is_admin", False)),
                send=send,
                workbench=workbench,
                adopt=adopt,
            )
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))

    def action_edit(self) -> None:
        record = self.record
        if record is None:
            return
        from tl_tui.widgets.edit_form import EditForm  # new module; imported here on purpose

        if self._edit_body(record):  # an object-backed extension record: its body is the content
            return
        try:
            meta = self.client.form_metadata(self.scope, record["type"])
        except NotImplementedError:
            self.post_message(StatusMessage("Editing needs the pset services", "warning"))
            return
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        actor = str(getattr(self.app, "actor", "user:dev"))

        def saved(done: bool | None) -> None:
            if done:
                self.post_message(RecordChanged(record["id"]))

        self.app.push_screen(EditForm(self.client, self.scope, record, meta, actor=actor), saved)
