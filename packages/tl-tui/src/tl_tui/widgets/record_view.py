"""Record view: header, Details, Psets, History tabs (brief 10.2, sketch 2).

STUB (P0-I2-T14): the constructor and the messages it posts are final; the content is replaced by
the ticket.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from tl_tui.client import ClientInterface


class RecordView(Vertical, can_focus=True):
    """Opened by the app for ``OpenRecord``. Posts `CloseRecord` on Esc and `StepRecord` on [ ]."""

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

    def compose(self) -> ComposeResult:
        yield Static(f"Record {self.key}", markup=False)
