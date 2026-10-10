"""A one-line prompt modal: ask for a reason or a note, return the text or ``None`` (brief 10.3).

Used where a command needs a reason (retract, flag, decline, a workflow transition). Enter accepts,
Esc cancels. With ``required`` an empty answer stays open and shows a message.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class PromptScreen(ModalScreen[str | None]):
    """Dismisses with the entered text (stripped), or ``None`` when cancelled."""

    KEY_HINTS: ClassVar[str] = "Enter accept  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    PromptScreen { align: center middle; }
    PromptScreen > Vertical {
        width: 60%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    PromptScreen #prompt-title { text-style: bold; }
    PromptScreen #prompt-error { color: $error; height: auto; }
    """

    def __init__(self, title: str, label: str, *, initial: str = "", required: bool = True) -> None:
        super().__init__()
        self.title_text = title
        self.label = label
        self.initial = initial
        self.required = required

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.title_text, id="prompt-title", markup=False)
            yield Static(self.label, id="prompt-label", markup=False)
            yield Input(value=self.initial, id="prompt-input")
            yield Static("", id="prompt-error", markup=False)

    def on_mount(self) -> None:
        self.query_one("#prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        answer = event.value.strip()
        if self.required and not answer:
            self.query_one("#prompt-error", Static).update("Required")
            return
        self.dismiss(answer)

    def action_cancel(self) -> None:
        self.dismiss(None)
