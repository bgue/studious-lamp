"""The review queue: values an enricher proposed, waiting for a person (P1-I7-T05c; brief 18.9).

A full-size modal opened with ``Ctrl+R``. The table lists the proposed values (``s`` switches to
every value, decided ones included); the panel under it describes the highlighted one: record,
property, the proposed value, the confidence and the enricher. ``a`` accepts the highlighted value
and ``x`` rejects it after asking for a reason. The service decides what is allowed (the target
type must allow ``SetPsetValues``, a value that is no longer waiting cannot be decided): a refusal
is shown in the status line and nothing changes. Every change is one client call
(``AcceptEnrichment`` or ``RejectEnrichment``) and the list is read again afterwards; nothing is
stored here.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_core.settings.layers import project_of_scope

from tl_tui.client import ClientInterface
from tl_tui.display import humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.integration_text import cells, columns, detail_lines, property_words
from tl_tui.widgets.prompt import PromptScreen
from tl_tui.widgets.record_screen import open_record

WAITING = "proposed"


class ReviewQueueScreen(ModalScreen[None]):
    """The proposed values of an enricher for ``scope``, to accept or reject."""

    KEY_HINTS: ClassVar[str] = "a accept  x reject  s waiting/all  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "accept", "Accept", show=False),
        Binding("x", "reject", "Reject", show=False),
        Binding("s", "toggle_all", "Waiting or all", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    ReviewQueueScreen { background: $surface; }
    ReviewQueueScreen > Vertical { padding: 0 1; }
    ReviewQueueScreen #review-title { text-style: bold; height: 1; }
    ReviewQueueScreen #review-table { height: 1fr; min-height: 6; }
    ReviewQueueScreen #review-detail { height: 10; border-top: solid $accent; padding: 0 1; }
    ReviewQueueScreen #review-status { height: 1; }
    ReviewQueueScreen #review-hints { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, scope: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.show_all = False
        self.values: list[dict[str, Any]] = []

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="review-title")
            yield DataTable[str](id="review-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="review-detail")
            yield Static("", markup=False, id="review-status")
            yield Static(self.KEY_HINTS, markup=False, id="review-hints")

    def on_mount(self) -> None:
        self.reload()
        self.query_one("#review-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted value where it is."""
        keep = self.current()
        try:
            self.values = self.client.list_integration(
                "enrichments", state=None if self.show_all else WAITING
            )
        except CLIENT_ERRORS as exc:
            self.values = []
            self._fill(None)
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep["value_id"] if keep is not None else None)

    def _fill(self, keep: str | None) -> None:
        """Show `self.values` in the table, the title and the detail panel, in the display mode."""
        technical = mode_of(self.app).technical
        table = self.query_one("#review-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns("enrichments", technical=technical))
        for value in self.values:
            row = (Text(cell) for cell in cells("enrichments", value, technical=technical))
            table.add_row(*row, key=value["value_id"])
        if self.values:
            ids = [value["value_id"] for value in self.values]
            table.move_cursor(row=ids.index(keep) if keep in ids else 0)
        what = "All values" if self.show_all else "Values waiting for review"
        self.query_one("#review-title", Static).update(f"{what} ({len(self.values)})   s switches")
        self._describe()

    def current(self) -> dict[str, Any] | None:
        """The highlighted value, or `None` when there is none."""
        row = self.query_one("#review-table", DataTable).cursor_row
        if not self.values or not 0 <= row < len(self.values):
            return None
        return self.values[row]

    def _describe(self) -> None:
        """Fill the panel under the table with the highlighted value."""
        detail = self.query_one("#review-detail", Static)
        value = self.current()
        if value is None:
            detail.update("No values." if self.show_all else "Nothing is waiting for review.")
            return
        technical = mode_of(self.app).technical
        detail.update("\n".join(detail_lines("enrichments", value, technical=technical)))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#review-status", Static).update(("! " if error else "") + text)

    def _property(self, value: dict[str, Any]) -> str:
        """The property as the display mode shows it: its words in plain, the path in technical."""
        if mode_of(self.app).technical:
            return value["property_path"]
        return property_words(value["property_path"])

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter opens the full record the value is about; Esc there comes back to this row."""
        event.stop()
        if not 0 <= event.cursor_row < len(self.values):
            return
        target = self.values[event.cursor_row].get("target")
        if not isinstance(target, dict) or not target.get("id"):
            return  # a value with no record to open (guarded; reported)
        open_record(
            self,
            self.client,
            self.scope,
            project_of_scope(self.scope) or "",
            self.actor,
            str(target["id"]),
        )

    def refresh_for_display_mode(self) -> None:
        """The technical toggle changed: rebuild the columns, rows and panel, keeping the row."""
        value = self.current()
        self._fill(value["value_id"] if value is not None else None)

    # --- actions -------------------------------------------------------------------------

    def _waiting(self) -> dict[str, Any] | None:
        """The highlighted value when a person can still decide it, else say why not."""
        value = self.current()
        if value is None:
            return None
        state = value["acceptance_state"]
        if state != WAITING:
            shown = state if mode_of(self.app).technical else humanize(state)
            self._say(f"This value is already {shown}.")
            return None
        return value

    def action_accept(self) -> None:
        """Accept the highlighted value."""
        value = self._waiting()
        if value is None:
            return
        try:
            self.client.integration_command(
                "AcceptEnrichment", self.scope, value_id=value["value_id"]
            )
        except CLIENT_ERRORS as exc:
            self.reload()  # show what the value really is now
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say(f"Accepted {self._property(value)}")

    def action_reject(self) -> None:
        """Reject the highlighted value after asking for a reason."""
        value = self._waiting()
        if value is None:
            return

        def apply(reason: str | None) -> None:
            if reason is None:  # cancelled: nothing is changed
                return
            try:
                self.client.integration_command(
                    "RejectEnrichment", self.scope, value_id=value["value_id"], reason=reason
                )
            except CLIENT_ERRORS as exc:
                self.reload()  # show what the value really is now
                self._say(describe_error(exc), error=True)
                return
            self.reload()
            self._say(f"Rejected {self._property(value)}")

        self.app.push_screen(
            PromptScreen(f"Reject {self._property(value)}", "Reason", required=True), apply
        )

    def action_toggle_all(self) -> None:
        """Switch between the waiting values and all of them."""
        self.show_all = not self.show_all
        self.reload()

    def action_reload(self) -> None:
        self.reload()
        self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)
