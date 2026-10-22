"""The full record screen a register opens from a row (P1-UX-S2).

``open_record`` is the one call a register makes on Enter. The screen finds the record by its id
through the viewer-filtered read, so a hidden record and a missing one read the same: "No record",
never an id. It hosts a ``RecordView`` (tabs Details, Properties, Links, History, Trace, Thread,
and Files when the record has files) and closes with ``dismiss(None)`` so the register's callback
runs and the register keeps its row (``pop_screen`` would not run it).
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen, Screen
from textual.widgets import Static

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.messages import CloseRecord, OpenRecord, StepRecord
from tl_tui.widgets.record_view import RecordView

NO_RECORD = "No record"


class RecordScreen(ModalScreen[None]):
    """One record in full. Esc closes it; following a link inside it re-targets the view."""

    KEY_HINTS: ClassVar[str] = "Esc back  1-6 tabs  T thread  e edit  l link  w workflow  t trace"

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = """
    RecordScreen { background: $surface; }
    RecordScreen #rs-missing { padding: 1 2; }
    RecordScreen RecordView { height: 1fr; }
    """

    def __init__(
        self, client: ClientInterface, scope: str, project: str, record_id: str, actor: str
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.project = project
        self.record_id = record_id
        self.actor = actor
        self.view: RecordView | None = None

    # --- layout --------------------------------------------------------------------------

    def _find(self) -> dict[str, Any] | None:
        try:
            return self.client.get_record_by_id(self.record_id)
        except CLIENT_ERRORS:
            return None

    def compose(self) -> ComposeResult:
        record = self._find()
        if record is None:
            yield Static(NO_RECORD, id="rs-missing", markup=False)
            return
        self.view = RecordView(
            self.client, str(record.get("scope") or self.scope), str(record["key"]), id="rs-view"
        )
        yield self.view

    def on_mount(self) -> None:
        if self.view is not None:
            self.view.focus()

    # --- keys and messages ---------------------------------------------------------------

    def action_close(self) -> None:
        self.dismiss(None)

    def on_close_record(self, message: CloseRecord) -> None:
        message.stop()
        self.dismiss(None)

    def on_step_record(self, message: StepRecord) -> None:
        message.stop()  # there is no neighbour list here

    async def on_open_record(self, message: OpenRecord) -> None:
        """A followed link (Links, Trace) shows that record here; the app does not see it."""
        message.stop()
        if self.view is None:
            return
        await self.view.remove()
        self.view = RecordView(self.client, message.scope, message.key, id="rs-view")
        await self.mount(self.view)
        self.view.focus()

    def refresh_for_display_mode(self) -> None:
        if self.view is not None:
            self.view.refresh_for_display_mode()


def open_record(
    screen: Screen[Any],
    client: ClientInterface,
    scope: str,
    project: str,
    actor: str,
    record_id: str,
) -> None:
    """Open the full record screen over ``screen`` (what a register calls on Enter)."""
    screen.app.push_screen(RecordScreen(client, scope, project, record_id, actor))
