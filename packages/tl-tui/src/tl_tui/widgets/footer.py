"""Footer: key hints of the focused context, a status line, and the selection count (brief 10.1).

`footer_lines` is the pure layout; `TlFooter` renders it at the widget's current width and redraws
on mount, on resize, and whenever its state changes.
"""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from textual import events
from textual.widget import Widget
from textual.widgets import Static

from tl_tui.messages import Severity

DEFAULT_HINTS = "F1 help  F2 nav  F3 context  F6 panels  Ctrl+Q quit"
FALLBACK_WIDTH = 80
_SEVERITY_PREFIX: dict[Severity, str] = {"info": "", "warning": "! ", "error": "✗ "}


def _cut(text: str, width: int) -> str:
    """Return ``text`` cut to ``width`` cells, ending in an ellipsis when it was longer."""
    if cell_len(text) <= width:
        return text
    if width <= 0:
        return ""
    return set_cell_size(text, width - 1) + "…"


def footer_lines(
    hints: str, status: str, severity: Severity, selection_count: int, width: int
) -> tuple[str, str]:
    """Return the two footer lines. The first is the key hints; the second is the status on the
    left and ``N selected`` right-aligned. Lines are cut to ``width`` cells, never padded except
    the second line when a selection count sits on its right.
    """
    first = _cut(f" {hints}", width)
    left = f" {_SEVERITY_PREFIX[severity]}{status}" if status else ""
    right = f"{selection_count} selected " if selection_count > 0 else ""
    if not right:
        return first, _cut(left, width)
    if cell_len(right) > width:
        return first, _cut(right.rstrip(), width)  # no room for both: the count wins
    left = _cut(left, width - cell_len(right) - 1)
    gap = max(0, width - cell_len(left) - cell_len(right))
    return first, left + " " * gap + right


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
        super().__init__(markup=False, id=id)
        self.hints = DEFAULT_HINTS
        self.status = ""
        self.severity: Severity = "info"
        self.selection_count = 0

    def on_mount(self) -> None:
        self._redraw()

    def on_resize(self, event: events.Resize) -> None:
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
        width = self.size.width or FALLBACK_WIDTH
        first, second = footer_lines(
            self.hints, self.status, self.severity, self.selection_count, width
        )
        self.update(f"{first}\n{second}")
