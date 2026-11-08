"""Activity tab of the record view (P2-INS, INS-A3): what happened around a record, as a table.

Full mode shows ``client.activity`` newest first, with the related records' rows (``r``). Revisions
only (``v``) shows the record's own History as before, oldest first. ``/`` filters the full mode,
``o`` reads the next page, and Enter on a related row opens the record it came from.

The tab reads only through `ClientInterface` and draws the cells of `tl_tui.record_activity_text`
(full mode) and `tl_tui.record_text` (revisions); it decides nothing about what a row means.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static
from tl_core.insights.types import ActivityPage, ActivityRow
from tl_core.intent import NOT_AVAILABLE, Intent

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.intent_text import intent_lines
from tl_tui.labels_load import load_labels
from tl_tui.messages import OpenRecord, StatusMessage
from tl_tui.record_activity_text import (
    activity_cells,
    activity_columns,
    filter_title,
    page_has_why,
    row_matches,
)
from tl_tui.record_text import history_cells, history_columns

PAGE_SIZE = 120


class ActivityTab(Vertical, can_focus=True):
    """Shows ``client.activity(record id)``; ``show_record`` loads the first page."""

    KEY_HINTS: ClassVar[str] = "v revisions only · r related · / filter · o older · Enter follow"

    DEFAULT_CSS = """
    ActivityTab #activity-table {
        height: 1fr;
    }
    ActivityTab #activity-why {
        height: auto;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("v", "revisions", "Revisions", show=False),
        Binding("r", "related", "Related", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("o", "older", "Older", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        actor: str = "user:dev",
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.actor = actor
        self.record: dict[str, Any] | None = None
        self.rows: list[ActivityRow] = []  # every row read so far, newest first
        self.shown: list[ActivityRow] = []  # the rows of the table, in the table's order
        self.next_before_seq: int | None = None
        self.revisions_only = False
        self.related = True
        self.text = ""
        self.labels = Labels()
        self._names: dict[str, str] = {}  # record id -> key, for the ids of intents

    def compose(self) -> ComposeResult:
        yield Static("", id="activity-title", markup=False)
        yield Input(placeholder="Filter", id="activity-filter")
        yield DataTable(id="activity-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="activity-why", markup=False)
        yield Static("Nothing recorded yet.", id="activity-empty", markup=False)
        yield Static("", id="activity-hint", markup=False)

    def on_mount(self) -> None:
        """The service labels once per tab; a failed read leaves the labels empty."""
        self.labels = load_labels(self.client, self.scope, ())

    def refresh_for_display_mode(self) -> None:
        """Draw the table again from the rows held; no read."""
        self._draw()

    def show_record(self, record: dict[str, Any]) -> None:
        """Keep the record, drop the last one's rows and filter, and load the first page."""
        self.record = record
        self.rows = []
        self.next_before_seq = None
        self.text = ""
        self.query_one("#activity-filter", Input).value = ""
        self.reload()

    def reload(self) -> None:
        """Read the first page again. A failed read keeps the rows on screen."""
        if self.record is None:
            return
        try:
            page = self._read(self.record["id"])
        except NotImplementedError:
            # A client with no activity: the tab stays empty.
            self.rows = []
            self.next_before_seq = None
            self._draw()
            return
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.rows = list(page.rows)
        self.next_before_seq = page.next_before_seq
        self._draw()

    def _read(self, record_id: str, before_seq: int | None = None) -> ActivityPage:
        """One page of the record's activity in the current mode (revisions read no related)."""
        if before_seq is None:
            return self.client.activity(
                record_id,
                revisions_only=self.revisions_only,
                related=self.related and not self.revisions_only,
                limit=PAGE_SIZE,
            )
        return self.client.activity(
            record_id,
            revisions_only=self.revisions_only,
            related=self.related and not self.revisions_only,
            before_seq=before_seq,
            limit=PAGE_SIZE,
        )

    def _draw(self) -> None:
        technical = mode_of(self.app).technical
        if self.revisions_only:
            columns = history_columns(technical)
            shown = list(reversed(self.rows))
            cells = [history_cells(row.event, self.labels, technical=technical) for row in shown]
        else:
            columns = activity_columns(self.rows, technical=technical)
            shown = [
                row
                for row in self.rows
                if not self.text or row_matches(row, self.text, self.labels)
            ]
            with_why = page_has_why(self.rows)
            cells = [
                activity_cells(row, self.labels, technical=technical, with_why=with_why)
                for row in shown
            ]
        self.shown = shown
        table = self.query_one("#activity-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*(Text(name) for name in columns))
        for row_cells in cells:
            table.add_row(*(Text(cell) for cell in row_cells))

        self._show_why(table.cursor_row if shown else -1)

        order = " · oldest first" if self.revisions_only else " · newest first"
        title = filter_title(self.revisions_only, self.related, self.text) + order
        self.query_one("#activity-title", Static).update(title)
        self.query_one("#activity-empty", Static).display = not self.rows
        more = "  o older" if self.next_before_seq is not None else ""
        hint = "v revisions only · r related · / filter" + more
        self.query_one("#activity-hint", Static).update(hint)

    # --- intent of the highlighted row ------------------------------------------------------

    def _names_for(self, intent: Intent) -> dict[str, str]:
        """Keys of the records an intent names; a failed read leaves the id shown."""
        ids = [i.target for i in intent.next if i.target]
        if intent.toward is not None:
            ids.append(intent.toward.target)
        for record_id in ids:
            if record_id in self._names or record_id == NOT_AVAILABLE:
                continue
            try:
                found = self.client.get_record_by_id(record_id)
            except (*CLIENT_ERRORS, NotImplementedError):
                continue
            if found is not None and found.get("key"):
                self._names[record_id] = str(found["key"])
        return self._names

    def _show_why(self, index: int) -> None:
        """The intent of the event of row ``index``; empty and hidden when it has none."""
        intent = self.shown[index].event.intent if 0 <= index < len(self.shown) else None
        technical = mode_of(self.app).technical
        names = None if intent is None or technical else self._names_for(intent)
        lines = intent_lines(intent, technical=technical, names=names)
        panel = self.query_one("#activity-why", Static)
        panel.update("\n".join(lines))
        panel.display = bool(lines)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._show_why(event.cursor_row)

    # --- keys -----------------------------------------------------------------------------

    def action_revisions(self) -> None:
        self.revisions_only = not self.revisions_only
        self.reload()

    def action_related(self) -> None:
        self.related = not self.related
        self.reload()

    def action_filter(self) -> None:
        self.query_one("#activity-filter", Input).focus()

    def action_older(self) -> None:
        """Read the page before the oldest row held and add it below."""
        if self.record is None or self.next_before_seq is None:
            return
        try:
            page = self._read(self.record["id"], before_seq=self.next_before_seq)
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.rows.extend(page.rows)
        self.next_before_seq = page.next_before_seq
        self._draw()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "activity-filter":
            return
        event.stop()
        self.text = event.value
        self._draw()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "activity-filter":
            return
        event.stop()
        self.query_one("#activity-table", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a related row opens the record it came from; on any other row nothing."""
        event.stop()
        index = event.cursor_row
        if not 0 <= index < len(self.shown):
            return
        row = self.shown[index]
        if row.related and row.from_key:
            self.post_message(OpenRecord(self.scope, row.from_key, follow=True))
