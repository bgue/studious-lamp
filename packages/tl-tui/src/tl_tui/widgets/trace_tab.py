"""Trace tab: the n-hop tree of records reachable through links (brief 7.5, sketch 12).

(P0-I3-T14.) STUB: constructor and attributes are final; the bodies are the ticket.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tl_tui.client import ClientInterface


class TraceTab(Vertical, can_focus=True):
    """Shows the trace of one record; Enter follows, + and - change the depth."""

    KEY_HINTS: ClassVar[str] = "Enter follow  +/- depth  o direction  Esc back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("plus", "depth(1)", show=False),
        Binding("minus", "depth(-1)", show=False),
        Binding("o", "direction", show=False),
    ]

    def __init__(self, client: ClientInterface, scope: str, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record: dict[str, Any] | None = None
        self.depth = 2

    def compose(self) -> ComposeResult:
        yield Static("Trace (not implemented yet)", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        self.record = record
