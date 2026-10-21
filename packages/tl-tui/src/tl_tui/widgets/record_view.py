"""Record view: header, Details, Properties, Links, History, Trace and Thread tabs (brief 10.2).

Esc posts `CloseRecord`, [ and ] post `StepRecord`, h opens the History tab. The view reads only
through `ClientInterface`; it never touches the ledger or services directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.widgets import DataTable, Static, TabbedContent, TabPane
from tl_core.ledger import Event
from tl_core.settings.layers import project_of_scope

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, details_for
from tl_tui.display import Labels, actor_label, humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
from tl_tui.messages import CloseRecord, RecordChanged, StatusMessage, StepRecord
from tl_tui.text import EMPTY, conformance_mark, timestamp
from tl_tui.widgets.links_tab import LinksTab
from tl_tui.widgets.psets_tab import PsetsTab
from tl_tui.widgets.thread_tab import ThreadTab
from tl_tui.widgets.trace_tab import TraceTab

TABS: dict[str, str] = {
    "details": "tab-details",
    "psets": "tab-psets",
    "links": "tab-links",
    "history": "tab-history",
    "trace": "tab-trace",
    "thread": "tab-thread",  # P1-I7 WS-B
}


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _sorted_keys(value: Any) -> str:
    return ", ".join(sorted(str(k) for k in value)) if isinstance(value, dict) else ""


def details_lines(rows: list[DetailRow]) -> str:
    """The Details rows, one labelled line each, values lined up after the longest label."""
    width = max((len(row.label) for row in rows), default=0) + 2
    return "\n".join(f"{row.label:<{width}}{row.value}" for row in rows)


_EVENT_WORDS: dict[str, str] = {
    "Record.Created": "Created",
    "Record.Updated": "Changed",
    "Record.Corrected": "Corrected",
    "Record.Voided": "Voided",
    "Pset.ValuesSet": "Properties set",
}


def event_label(event_type: str) -> str:
    """The History "What" column in plain mode: a word for each known event type."""
    return _EVENT_WORDS.get(event_type) or humanize(event_type)


def _plain_keys(value: Any) -> str:
    """The sorted keys of a dict as words (``size_in`` becomes ``Size in``), joined by commas."""
    if not isinstance(value, dict):
        return ""
    return ", ".join(humanize(str(k)) for k in sorted(str(k) for k in value))


def event_summary(event: Event, labels: Labels | None = None, *, technical: bool = True) -> str:
    """One line for the History table, by event type. Other event types have no summary.

    ``technical=True`` (the default, and what the tests pin) is the raw text; plain mode uses
    words for the property names and the pset, and no layer.
    """
    payload = event.payload
    kind = event.event_type
    if not technical:
        if kind == "Record.Created":
            return f"created: {payload.get('title') or ''}"
        if kind == "Record.Updated":
            return f"changed: {_plain_keys(payload.get('changes'))}"
        if kind == "Record.Corrected":
            return f"corrected: {_plain_keys(payload.get('changes'))}"
        if kind == "Record.Voided":
            return f"voided: {payload.get('reason') or ''}"
        if kind == "Pset.ValuesSet":
            pset = humanize(str(payload.get("pset") or ""))
            return f"{pset}: {_plain_keys(payload.get('values'))}"
        return ""
    if kind == "Record.Created":
        return f"created: {payload.get('title') or ''}"
    if kind == "Record.Updated":
        return f"changed: {_sorted_keys(payload.get('changes'))}"
    if kind == "Record.Corrected":
        return f"corrected: {_sorted_keys(payload.get('changes'))}"
    if kind == "Record.Voided":
        return f"voided: {payload.get('reason') or ''}"
    if kind == "Pset.ValuesSet":
        pset = payload.get("pset") or ""
        layer = payload.get("layer") or ""
        return f"{pset} ({layer}): {_sorted_keys(payload.get('values'))}"
    return ""


class RecordView(Vertical, can_focus=True):
    """Opened by the app for ``OpenRecord``. Posts `CloseRecord` on Esc and `StepRecord` on [ ]."""

    DEFAULT_CSS = """
    RecordView #rv-banner { height: auto; display: none; background: $warning 35%; padding: 0 1; }
    """

    KEY_HINTS: ClassVar[str] = (
        "Esc back  [ ] prev/next  1-5 tabs  T thread  e edit  l link  w workflow  t trace  R tray"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", show=False),
        Binding("left_square_bracket", "step(-1)", show=False),
        Binding("right_square_bracket", "step(1)", show=False),
        Binding("h", "history", show=False),
        Binding("e", "edit", show=False),
        Binding("1", "tab('details')", show=False),
        Binding("2", "tab('psets')", show=False),
        Binding("3", "tab('links')", show=False),
        Binding("4", "tab('history')", show=False),
        Binding("5", "tab('trace')", show=False),
        Binding("T", "tab('thread')", show=False),
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
        self._events: list[Event] = []  # the last read history, redrawn on a mode switch
        self._badges_text: str = ""  # the last header badges, redrawn on a mode switch
        self.details: str = ""  # the Details tab as text (for tests and the screen tickets)

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
            with TabPane("History", id="tab-history"):
                yield DataTable(id="rv-history", cursor_type="row")
            with TabPane("Trace", id="tab-trace"):
                yield TraceTab(self.client, self.scope, id="trace-tab")
            with TabPane("Thread", id="tab-thread"):
                yield ThreadTab(self.client, self.scope, actor=self._actor(), id="thread-tab")

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))

    def on_mount(self) -> None:
        self.reload()

    def reload(self) -> None:
        """Re-read the record and its history, then redraw. On a client error, keep the display."""
        try:
            record = self.client.get_record(self.scope, self.key)
            events = [] if record is None else self.client.history(record["id"])
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.record = record
        self._events = events
        self._badges_text = self._badges(record)
        self._draw_header(record, self._badges_text)
        self._draw_details(record)
        self._draw_history(events)
        if record is None:
            self.post_message(StatusMessage(f"No record {self.key}", "error"))
        else:
            self.query_one("#psets-tab", PsetsTab).show_record(record)
            self.query_one("#links-tab", LinksTab).show_record(record)
            self.query_one("#trace-tab", TraceTab).show_record(record)
            self.query_one("#thread-tab", ThreadTab).show_record(record)

    def _labels_for(self, record: dict[str, Any]) -> Labels:
        """The labels, loaded once per view (a retarget makes a new view)."""
        if self._labels is None:
            self._labels = load_labels(self.client, self.scope, ("core.Record", record["type"]))
        return self._labels

    def _draw_details(self, record: dict[str, Any] | None) -> None:
        """The Details tab: the type's rows, technical rows only in technical mode."""
        body = self.query_one("#rv-details", Static)
        if record is None:
            self.details = ""
            body.update("")
            return
        rows = details_for(
            self.client,
            project_of_scope(self.scope) or "",
            record,
            self._labels_for(record),
            mode_of(self.app),
        )
        self.details = details_lines(rows)
        body.update(self.details)

    def _current_labels(self) -> Labels:
        """The labels for the shown record; no labels before a record is read."""
        return Labels() if self.record is None else self._labels_for(self.record)

    def refresh_for_display_mode(self) -> None:
        """Draw the header, Details, History and Properties again; the tab stays."""
        if self.record is None:
            return
        self._draw_header(self.record, self._badges_text)
        self._draw_details(self.record)
        self._draw_history(self._events)
        self.query_one("#psets-tab", PsetsTab).refresh_for_display_mode()

    def _badges(self, record: dict[str, Any] | None) -> str:
        """``since <time>`` (workflow state) and link counts for the header; empty when unknown.

        Both come from joins in the services (`workflow_status`, `link_counts`). A client that
        cannot answer, or a record without a workflow, just leaves the badges out.
        """
        if record is None:
            return ""
        parts: list[str] = []
        try:
            entered = self.client.workflow_status(record["id"]).entered_at
            parts.append(f"since {timestamp(entered)}")
        except (*CLIENT_ERRORS, NotImplementedError):
            pass
        try:
            counts = self.client.link_counts([record["id"]]).get(record["id"])
        except (*CLIENT_ERRORS, NotImplementedError):
            counts = None
        if counts is not None:
            if counts.active:
                parts.append(f"{counts.active} link{'' if counts.active == 1 else 's'}")
            for label, number in (
                ("stale", counts.stale),
                ("broken", counts.broken),
                ("suggested", counts.suggested),
            ):
                if number:
                    parts.append(f"{number} {label}")
        return " · ".join(parts)

    def _draw_header(self, record: dict[str, Any] | None, badges: str = "") -> None:
        header = self.query_one("#rv-header", Static)
        if record is None:
            header.update(f"{self.key} · not found")
            return
        line1 = f"{record['key']} · {record['title']}"
        technical = mode_of(self.app).technical
        version = f" · v{record['version']}" if technical else ""  # D20: the version is technical
        line2 = (
            f"{_or_empty(record.get('status'))}{version} · "
            f"{conformance_mark(record.get('conformance'))}"
        )
        if record.get("voided"):
            line2 += " · voided"
        if badges:
            line2 += f" · {badges}"
        header.update(f"{line1}\n{line2}")

    def _draw_history(self, events: list[Event]) -> None:
        """The History table: technical columns in technical mode, plain words otherwise."""
        table = self.query_one("#rv-history", DataTable)
        technical = mode_of(self.app).technical
        labels = self._current_labels()
        table.clear(columns=True)
        if technical:
            table.add_columns("#", "When", "Event", "Actor", "Summary")
        else:
            table.add_columns("When", "What", "By", "Summary")
        for event in reversed(events):
            when = Text(event.recorded_at.strftime("%Y-%m-%d %H:%M:%S"))
            if technical:
                table.add_row(
                    Text(str(event.stream_version)),
                    when,
                    Text(event.event_type),
                    Text(event.actor),
                    Text(event_summary(event)),
                    key=event.event_id,
                )
            else:
                table.add_row(
                    when,
                    Text(event_label(event.event_type)),
                    Text(actor_label(labels, event.actor)),
                    Text(event_summary(event, labels, technical=False)),
                    key=event.event_id,
                )

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
        self.show_tab("history")

    def action_tab(self, name: str) -> None:
        self.show_tab(name)

    def show_tab(self, name: str) -> None:
        """Make the tab named in ``TABS`` active (``details``, ``psets``, ... ``thread``)."""
        self.query_one("#rv-tabs", TabbedContent).active = TABS[name]

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
