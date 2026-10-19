# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedVariable=false
"""The review queue: values an enricher proposed, waiting for a person (P1-I7-T05c; brief 18.9).

A full-size modal opened with ``Ctrl+R``. The table lists the proposed values (``s`` switches to
every value, decided ones included); the panel under it describes the highlighted one: record,
property, the proposed value, the confidence and the enricher. ``a`` accepts the highlighted value
and ``x`` rejects it after asking for a reason. The service decides what is allowed (the target
type must allow ``SetPsetValues``, a value that is no longer waiting cannot be decided): a refusal
is shown in the status line and nothing changes. Every change is one client call
(``AcceptEnrichment`` or ``RejectEnrichment``) and the list is read again afterwards; nothing is
stored here.


STUB (P1-I7): the methods below whose body is `raise NotImplementedError` are yours;
everything else is final. Remove this paragraph, the two lint-silencing lines at the top of the
file, the STEPS paragraphs and `NotImplementedError` when you implement them.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.integration_text import COLUMNS, cells, detail_lines
from tl_tui.widgets.prompt import PromptScreen

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
        self.query_one("#review-table", DataTable).add_columns(*COLUMNS["enrichments"])
        self.reload()
        self.query_one("#review-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted value where it is.

        STEPS: remember `keep = self.current()`. Read
        `self.client.list_integration("enrichments", state=None if self.show_all else
        WAITING)` into `self.values`. On a `CLIENT_ERRORS` error set `self.values = []`,
        call `self._fill(None)`, say `describe_error(exc)` with `error=True` and return.
        Otherwise call `self._fill(keep["value_id"] if keep is not None else None)`.
        """
        raise NotImplementedError

    def _fill(self, keep: str | None) -> None:
        """Show `self.values` in the table, the title and the detail panel.

        STEPS: query `#review-table` (a `DataTable`), `clear()` it, and add one row per
        value: `Text(cell)` for each cell of `cells("enrichments", value)`, with
        `key=value["value_id"]`. When there are values, `move_cursor(row=...)` to the index
        of `keep` (a value id) if it is among them, else to row 0. Set the `#review-title`
        Static to `f"{what} ({len(self.values)})   s switches"` where `what` is `"All
        values"` when `self.show_all` else `"Values waiting for review"` (three spaces
        before `s switches`). Finish with `self._describe()`.
        """
        raise NotImplementedError

    def current(self) -> dict[str, Any] | None:
        """The highlighted value, or `None` when there is none.

        STEPS: read `cursor_row` of `#review-table`; return `self.values[cursor_row]` when
        `self.values` is not empty and the row is in range, else `None`.
        """
        raise NotImplementedError

    def _describe(self) -> None:
        """Fill the panel under the table with the highlighted value.

        STEPS: query the `#review-detail` Static. With no highlighted value, set it to
        `"Nothing is waiting for review."` (when `self.show_all` is false) or `"No
        values."`. Otherwise set it to the lines of `detail_lines("enrichments", value)`
        joined with newlines.
        """
        raise NotImplementedError

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#review-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def _waiting(self) -> dict[str, Any] | None:
        """The highlighted value when a person can still decide it, else say why not."""
        value = self.current()
        if value is None:
            return None
        if value["acceptance_state"] != WAITING:
            self._say(f"This value is already {value['acceptance_state']}.")
            return None
        return value

    def action_accept(self) -> None:
        """Accept the highlighted value.

        STEPS: take the value from `self._waiting()` and stop when it is `None`. Call
        `self.client.integration_command("AcceptEnrichment", self.scope,
        value_id=value["value_id"])`. On a `CLIENT_ERRORS` error call `self.reload()` (to
        show what the value really is now), then `self._say(describe_error(exc),
        error=True)` and return. On success call `self.reload()` and `self._say(f"Accepted
        {value['property_path']}")`.
        """
        raise NotImplementedError

    def action_reject(self) -> None:
        """Reject the highlighted value after asking for a reason.

        STEPS: take the value from `self._waiting()` and stop when it is `None`. Define
        `apply(reason: str | None)`: it returns at once when `reason is None` (cancelled,
        nothing changes); otherwise it calls
        `self.client.integration_command("RejectEnrichment", self.scope,
        value_id=value["value_id"], reason=reason)`; on a `CLIENT_ERRORS` error it calls
        `self.reload()` then `self._say(describe_error(exc), error=True)` and returns; on
        success it calls `self.reload()` and `self._say(f"Rejected
        {value['property_path']}")`. Push `PromptScreen(f"Reject {value['property_path']}",
        "Reason", required=True)` on the app with `apply` as the callback
        (`self.app.push_screen(...)`).
        """
        raise NotImplementedError

    def action_toggle_all(self) -> None:
        """Switch between the waiting values and all of them.

        STEPS: flip `self.show_all` and call `self.reload()`.
        """
        raise NotImplementedError

    def action_reload(self) -> None:
        self.reload()
        self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)
