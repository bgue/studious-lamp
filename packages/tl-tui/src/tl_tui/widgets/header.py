"""Header bar: breadcrumb on the left, connection and user on the right (brief 10.1, sketch 1).

`header_line` is the pure layout; `TlHeader` renders it at the widget's current width and redraws
on mount, on resize, and when the view changes.
"""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from textual import events
from textual.widgets import Static

FALLBACK_WIDTH = 80


def header_line(company: str, scope: str, view: str, mode: str, actor: str, width: int) -> str:
    """Return the header line, exactly ``width`` terminal cells wide.

    The right part (``● mode · user``) is kept when it fits beside the breadcrumb, dropped when it
    does not, and the breadcrumb is cut with an ellipsis when even it does not fit.
    """
    if width <= 0:
        return ""
    project = scope.removeprefix("project:")
    user = actor.removeprefix("user:")
    left = f" {company} ▸ {project} ▸ {view}"
    right = f"● {mode} · {user} "
    if cell_len(left) + 1 + cell_len(right) <= width:
        gap = width - cell_len(left) - cell_len(right)
        return left + " " * gap + right
    if cell_len(left) <= width:
        return left + " " * (width - cell_len(left))
    return set_cell_size(left, width - 1) + "…"


class TlHeader(Static):
    """``Company ▸ Project ▸ View`` plus ``● embedded · user`` right-aligned."""

    def __init__(
        self,
        *,
        company: str,
        scope: str,
        view: str = "Records",
        mode: str = "embedded",
        actor: str = "user:dev",
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(markup=False, id=id)
        self.company = company
        self.scope = scope
        self.view = view
        self.mode = mode
        self.actor = actor

    def on_mount(self) -> None:
        self._redraw()

    def on_resize(self, event: events.Resize) -> None:
        self._redraw()

    def set_view(self, view: str) -> None:
        """Change the last breadcrumb element (for example ``Records`` or ``FV-1001``)."""
        self.view = view
        self._redraw()

    def _redraw(self) -> None:
        width = self.size.width or FALLBACK_WIDTH
        self.update(header_line(self.company, self.scope, self.view, self.mode, self.actor, width))
