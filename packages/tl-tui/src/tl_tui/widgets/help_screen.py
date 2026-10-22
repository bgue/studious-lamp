"""Help screen: the key map from `tl_tui.keymap`, opened with `F1` or `?` (brief 10.3).

The screen only renders the key map. `Esc`, `F1` or `?` closes it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from tl_tui.keymap import help_text


class HelpScreen(ModalScreen[None]):
    """Modal that lists every documented key. It dismisses with ``None``."""

    KEY_HINTS: ClassVar[str] = "Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("f1", "close", "Close", show=False),
        Binding("question_mark", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > Vertical {
        width: 90%;
        max-width: 100;
        height: 90%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    HelpScreen #help-title { text-style: bold; }
    HelpScreen #help-scroll { height: 1fr; }
    """

    def __init__(self, title: str = "", keys: Sequence[tuple[str, str]] = ()) -> None:
        """``keys`` are the keys of the screen it was opened from, listed above the key map."""
        super().__init__()
        self.title_text = title
        self.screen_keys = tuple(keys)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Key map", id="help-title", markup=False)
            with VerticalScroll(id="help-scroll"):
                yield Static(self.body(), id="help-body", markup=False)

    def body(self) -> str:
        """The screen's own keys (when there are some), then the key map."""
        if not self.screen_keys:
            return help_text()
        own = "\n".join(f"  {keys:<30}{what}" for keys, what in self.screen_keys)
        return f"{self.title_text}\n{own}\n\n{help_text()}"

    def action_close(self) -> None:
        self.dismiss(None)
