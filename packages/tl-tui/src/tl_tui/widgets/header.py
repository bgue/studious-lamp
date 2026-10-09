"""Header bar: breadcrumb on the left, connection and user on the right (brief 10.1, sketch 1).

STUB (P0-I2-T12): the public interface is final; the rendering is replaced by the ticket.
"""

from __future__ import annotations

from textual.widgets import Static


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
        super().__init__(id=id)
        self.company = company
        self.scope = scope
        self.view = view
        self.mode = mode
        self.actor = actor

    def on_mount(self) -> None:
        self.update(f"{self.company} ▸ {self.scope} ▸ {self.view}")

    def set_view(self, view: str) -> None:
        """Change the last breadcrumb element (for example ``Records`` or ``FV-1001``)."""
        self.view = view
        self.update(f"{self.company} ▸ {self.scope} ▸ {self.view}")
