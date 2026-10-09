"""Reference tray screen: tick collected records and link them to the current record in one action.

(P0-I3-T13b; brief 7.2, sketch 12.) STUB: constructor and bindings are final; the bodies are the
ticket.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Static

from tl_tui.client import ClientInterface
from tl_tui.tray import ReferenceTray


class ReferenceTrayScreen(ModalScreen[int | None]):
    """Dismisses with the number of links created, or ``None`` when closed without linking."""

    KEY_HINTS: ClassVar[str] = "Space tick  Del remove  Enter link ticked  c clear  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("space", "toggle_select", show=False),
        Binding("delete", "remove", show=False),
        Binding("c", "clear", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        tray: ReferenceTray,
        target: dict[str, Any] | None,
        *,
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.tray = tray
        self.target = target
        self.actor = actor

    def compose(self) -> ComposeResult:
        yield Static("Reference tray (not implemented yet)", markup=False)
