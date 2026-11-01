"""Links tab: a record's links grouped by relation, suggestions, and expected-but-missing links.

(P0-I3-T13; brief 7.4, sketch 12.) One table: a header row per group (``▾ raised against (2)``),
then a row per link with the record at the other end, the link's status, its pin and note;
suggestions form the last group. Below the table, one line per expected link the record lacks.
Row keys act on the highlighted link: Enter follows it, a/d accept or decline a suggestion,
u re-pins, v verifies, x retracts. Every command goes through `ClientInterface`; after one
succeeds the tab posts `RecordChanged` so the record view (and the grid) reload.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from tl_core.links.expected import MissingLink
from tl_core.services.link_queries import LinkView
from tl_core.services.links import (
    AcceptLink,
    DeclineLink,
    RepinLink,
    RetractLink,
    VerifyLink,
)

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.links_text import (  # noqa: F401 - the moved names stay importable from here
    SUGGESTED,
    TableRow,
    _header_row,
    _link_row,
    build_rows,
    group_title,
    missing_line,
    pin_text,
    status_text,
)
from tl_tui.messages import OpenRecord, RecordChanged, StatusMessage
from tl_tui.widgets.prompt import PromptScreen

COLUMNS: tuple[str, ...] = ("", "Key", "Title", "Status", "Pin", "Note")


class LinksTab(Vertical, can_focus=True):
    """Shows the links of one record. Row actions call the client and post `RecordChanged`."""

    KEY_HINTS: ClassVar[str] = (
        "Enter follow  l link  R tray  a accept  d decline  u re-pin  v verify  x retract  t trace"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "follow", show=False),
        Binding("a", "accept", show=False),
        Binding("d", "decline", show=False),
        Binding("u", "repin", show=False),
        Binding("v", "verify", show=False),
        Binding("x", "retract", show=False),
    ]

    DEFAULT_CSS = """
    LinksTab { height: auto; }
    LinksTab > DataTable { height: auto; max-height: 18; }
    LinksTab > #links-missing { height: auto; padding: 0 1; }
    LinksTab > #links-note { height: auto; padding: 0 1; }
    """

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
        self.views: dict[str, LinkView] = {}
        self.text = ""  # the last "empty" or "unavailable" note
        self._missing: list[MissingLink] = []  # the last read, redrawn on a mode switch

    def compose(self) -> ComposeResult:
        yield DataTable(id="links-table", cursor_type="row")
        yield Static("", id="links-missing", markup=False)
        yield Static("", id="links-note", markup=False)

    def on_mount(self) -> None:
        self.query_one("#links-table", DataTable).add_columns(*COLUMNS)

    def on_focus(self) -> None:
        self.query_one("#links-table", DataTable).focus()

    def show_record(self, record: dict[str, Any]) -> None:
        self.record = record
        self.reload()

    def reload(self) -> None:
        """Read the links again and redraw. On a client error the display is kept."""
        if self.record is None:
            return
        record_id = self.record["id"]
        try:
            views = self.client.links_of(record_id)
            missing = self.client.expected_links(record_id)
        except NotImplementedError:
            self._note("Links unavailable: the link services are not installed yet")
            return
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.views = {view.link_id: view for view in views}
        table = self.query_one("#links-table", DataTable)
        keep = table.cursor_row
        table.clear()
        rows = build_rows(views)
        for number, row in enumerate(rows):
            table.add_row(
                *(Text(cell) for cell in row.cells),
                key=row.link_id or f"group:{number}",
            )
        if views and keep < len(rows):
            table.move_cursor(row=keep)
        self._missing = list(missing)
        self._draw_missing()
        self._note("" if views else "No links yet. Press l to link this record.")

    def refresh_for_display_mode(self) -> None:
        """Redraw the expected-but-missing lines in the current mode; the table stays."""
        self._draw_missing()

    def _draw_missing(self) -> None:
        technical = mode_of(self.app).technical
        self.query_one("#links-missing", Static).update(
            "\n".join(missing_line(item, technical=technical) for item in self._missing)
        )

    def _note(self, text: str) -> None:
        self.text = text
        self.query_one("#links-note", Static).update(text)

    def _highlighted(self) -> LinkView | None:
        table = self.query_one("#links-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return self.views.get(row_key) if isinstance(row_key, str) else None

    def highlighted_other(self) -> dict[str, Any] | None:
        """The record at the other end of the highlighted link row, or ``None``."""
        view = self._highlighted()
        if view is None:
            return None
        return {
            "id": view.other_id,
            "key": view.other_key,
            "type": view.other_type,
            "title": view.other_title,
        }

    # --- actions -----------------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        self.action_follow()

    def action_follow(self) -> None:
        view = self._highlighted()
        if view is not None and view.other_key:
            self.post_message(OpenRecord(self.scope, view.other_key, follow=True))

    def _need_link(self) -> LinkView | None:
        view = self._highlighted()
        if view is None:
            self.post_message(StatusMessage("Highlight a link first", "warning"))
        return view

    def _run(self, call: Any, done: str) -> None:
        try:
            call()
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.post_message(StatusMessage(done, "info"))
        if self.record is not None:
            self.post_message(RecordChanged(str(self.record["id"])))

    def action_accept(self) -> None:
        view = self._need_link()
        if view is None:
            return
        cmd = AcceptLink(
            actor=self.actor,
            source="tui",
            scope=self.scope,
            link_id=view.link_id,
            expected_version=view.version,
        )
        self._run(lambda: self.client.accept_link(cmd), f"Accepted link to {view.other_key}")

    def action_verify(self) -> None:
        view = self._need_link()
        if view is None:
            return
        cmd = VerifyLink(
            actor=self.actor,
            source="tui",
            scope=self.scope,
            link_id=view.link_id,
            expected_version=view.version,
        )
        self._run(lambda: self.client.verify_link(cmd), f"Verified link to {view.other_key}")

    def action_decline(self) -> None:
        view = self._need_link()
        if view is None:
            return

        def decided(reason: str | None) -> None:
            if reason is None:
                return
            cmd = DeclineLink(
                actor=self.actor,
                source="tui",
                scope=self.scope,
                link_id=view.link_id,
                expected_version=view.version,
                reason=reason or None,
            )
            self._run(lambda: self.client.decline_link(cmd), f"Declined {view.other_key}")

        self.app.push_screen(
            PromptScreen("Decline suggestion", "Reason (optional)", required=False), decided
        )

    def action_repin(self) -> None:
        view = self._need_link()
        if view is None:
            return

        def decided(pin: str | None) -> None:
            if pin is None:
                return
            cmd = RepinLink(
                actor=self.actor,
                source="tui",
                scope=self.scope,
                link_id=view.link_id,
                expected_version=view.version,
                pin=pin or None,
            )
            self._run(lambda: self.client.repin_link(cmd), f"Re-pinned link to {view.other_key}")

        self.app.push_screen(
            PromptScreen(
                "Re-pin link",
                "New pin (blank: floating to the current revision)",
                initial=view.pin or "",
                required=False,
            ),
            decided,
        )

    def action_retract(self) -> None:
        view = self._need_link()
        if view is None:
            return

        def decided(reason: str | None) -> None:
            if reason is None:
                return
            cmd = RetractLink(
                actor=self.actor,
                source="tui",
                scope=self.scope,
                link_id=view.link_id,
                expected_version=view.version,
                reason=reason,
            )
            self._run(lambda: self.client.retract_link(cmd), f"Retracted link to {view.other_key}")

        self.app.push_screen(PromptScreen("Retract link", "Reason"), decided)
