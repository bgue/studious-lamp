"""Footer: key hints of the focused context, a status line, and the selection count (brief 10.1).

STUB (P0-I2-T12): `hints_for`, `DEFAULT_HINTS` and the public methods are final; the rendering is
replaced by the ticket.
"""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

from tl_tui.messages import Severity

DEFAULT_HINTS = "F2 nav  F3 context  F6 panels  Ctrl+Q quit"


def hints_for(widget: Widget | None) -> str:
    """Key hints of ``widget``: the first ``KEY_HINTS`` class attribute on it or its ancestors."""
    node: Widget | None = widget
    while node is not None:
        hints = getattr(node, "KEY_HINTS", None)
        if isinstance(hints, str):
            return hints
        parent = node.parent
        node = parent if isinstance(parent, Widget) else None
    return DEFAULT_HINTS


class TlFooter(Static):
    """Two lines: key hints; then status text on the left and ``N selected`` on the right."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self.hints = DEFAULT_HINTS
        self.status = ""
        self.severity: Severity = "info"
        self.selection_count = 0

    def on_mount(self) -> None:
        self._redraw()

    def set_hints(self, text: str) -> None:
        self.hints = text
        self._redraw()

    def show_status(self, text: str, severity: Severity = "info") -> None:
        self.status = text
        self.severity = severity
        self._redraw()

    def set_selection_count(self, count: int) -> None:
        self.selection_count = count
        self._redraw()

    def _redraw(self) -> None:
        self.update(f"{self.hints}\n{self.status}")
