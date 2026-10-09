"""Record view: header, Details, Psets, History tabs (brief 10.2, sketch 2).

Esc posts `CloseRecord`, [ and ] post `StepRecord`, h opens the History tab. The view reads only
through `ClientInterface`; it never touches the ledger or services directly.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.widgets import DataTable, Static, TabbedContent, TabPane
from tl_core.ledger import Event

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import CloseRecord, RecordChanged, StatusMessage, StepRecord
from tl_tui.text import EMPTY, conformance_mark, short_hash, timestamp
from tl_tui.widgets.psets_tab import PsetsTab


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _sorted_keys(value: Any) -> str:
    return ", ".join(sorted(str(k) for k in value)) if isinstance(value, dict) else ""


def details_text(record: dict[str, Any]) -> str:
    """The envelope fields, one labelled line each, in the order of sketch 2."""
    rows = [
        ("Key", _or_empty(record.get("key"))),
        ("Type", _or_empty(record.get("type"))),
        ("Title", _or_empty(record.get("title"))),
        ("Description", _or_empty(record.get("description"))),
        ("Status", _or_empty(record.get("status"))),
        ("Scope", _or_empty(record.get("scope"))),
        ("Version", _or_empty(record.get("version"))),
        ("Created", timestamp(record.get("created_at"))),
        ("Updated", timestamp(record.get("updated_at"))),
        ("Conformance", conformance_mark(record.get("conformance"))),
        ("Schema", short_hash(record.get("effective_schema_hash"))),
    ]
    return "\n".join(f"{label:<13}{value}" for label, value in rows)


def event_summary(event: Event) -> str:
    """One line for the History table, by event type. Other event types have no summary."""
    payload = event.payload
    kind = event.event_type
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

    KEY_HINTS: ClassVar[str] = "Esc back  [ ] prev/next  h history"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", show=False),
        Binding("left_square_bracket", "step(-1)", show=False),
        Binding("right_square_bracket", "step(1)", show=False),
        Binding("h", "history", show=False),
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

    def compose(self) -> ComposeResult:
        yield Static("", id="rv-header", markup=False)
        with TabbedContent(initial="tab-details", id="rv-tabs"):
            with TabPane("Details", id="tab-details"):
                with VerticalScroll():
                    yield Static("", id="rv-details", markup=False)
            with TabPane("Psets", id="tab-psets"):
                yield PsetsTab(self.client, self.scope, id="psets-tab")
            with TabPane("History", id="tab-history"):
                yield DataTable(id="rv-history", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#rv-history", DataTable)
        table.add_columns("#", "When", "Event", "Actor", "Summary")
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
        self._draw_header(record)
        self.query_one("#rv-details", Static).update("" if record is None else details_text(record))
        self._draw_history(events)
        if record is None:
            self.post_message(StatusMessage(f"No record {self.key}", "error"))
        else:
            self.query_one("#psets-tab", PsetsTab).show_record(record)

    def _draw_header(self, record: dict[str, Any] | None) -> None:
        header = self.query_one("#rv-header", Static)
        if record is None:
            header.update(f"{self.key} · not found")
            return
        line1 = f"{record['key']} · {record['title']}"
        line2 = (
            f"{_or_empty(record.get('status'))} · v{record['version']} · "
            f"{conformance_mark(record.get('conformance'))}"
        )
        if record.get("voided"):
            line2 += " · voided"
        header.update(f"{line1}\n{line2}")

    def _draw_history(self, events: list[Event]) -> None:
        table = self.query_one("#rv-history", DataTable)
        table.clear()
        for event in reversed(events):
            table.add_row(
                Text(str(event.stream_version)),
                Text(event.recorded_at.strftime("%Y-%m-%d %H:%M:%S")),
                Text(event.event_type),
                Text(event.actor),
                Text(event_summary(event)),
                key=event.event_id,
            )

    def on_record_changed(self, message: RecordChanged) -> None:
        # Not stopped: the message keeps bubbling so the app can refresh the grid.
        if self.record is not None and message.record_id == self.record["id"]:
            self.reload()

    # --- actions (keys) ----------------------------------------------------------------------

    def action_close(self) -> None:
        self.post_message(CloseRecord())

    def action_step(self, delta: int) -> None:
        self.post_message(StepRecord(delta))

    def action_history(self) -> None:
        self.query_one("#rv-tabs", TabbedContent).active = "tab-history"
