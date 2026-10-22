"""What an action asks before it runs: a reason, an answer, a choice, or "are you sure" (P1-UX2-S2).

``ActionFormScreen`` collects text and returns it as a dict; it knows no command and sends nothing.
The host builds the command from the dict and sends it with the client, inside
``LogScreen.attempt`` so a refusal reaches the status line. Enter or Ctrl+S sends the form (Enter
adds a line in a multi-line field, so Ctrl+S sends there); Esc returns ``None``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static, TextArea


@dataclass(frozen=True)
class FormField:
    """One thing the form asks. ``name`` is the key in the returned dict."""

    name: str
    label: str
    kind: Literal["line", "text", "choice"] = "line"
    choices: tuple[str, ...] = ()
    required: bool = True
    default: str = ""


class ChoiceField(Static, can_focus=True):
    """One of a few words; Left and Right (or Space) move to the next one and wrap."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "step(-1)", show=False),
        Binding("right", "step(1)", show=False),
        Binding("space", "step(1)", show=False),
    ]

    DEFAULT_CSS = """
    ChoiceField { height: 1; padding: 0 1; }
    ChoiceField:focus { background: $boost; text-style: bold; }
    """

    def __init__(
        self,
        choices: Sequence[str],
        default: str = "",
        *,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__("", markup=False, id=id)
        self.choices = tuple(choices)
        self.index = self.choices.index(default) if default in self.choices else 0
        self._draw()

    @property
    def value(self) -> str:
        return self.choices[self.index] if self.choices else ""

    def action_step(self, by: int) -> None:
        if self.choices:
            self.index = (self.index + by) % len(self.choices)
            self._draw()

    def _draw(self) -> None:
        self.update(f"◂ {self.value} ▸" if len(self.choices) > 1 else self.value)


class ActionFormScreen(ModalScreen[dict[str, str] | None]):
    """Ask for ``fields`` (or, with none, for a yes under the ``confirm`` text)."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "submit", "Send", show=False),
        Binding("enter", "submit", "Send", show=False),
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
    ]

    DEFAULT_CSS = """
    ActionFormScreen { align: center middle; }
    ActionFormScreen > Vertical {
        width: 70; max-width: 100%; height: auto; max-height: 100%;
        border: round $accent; background: $surface; padding: 0 1;
    }
    ActionFormScreen .form-title { text-style: bold; }
    ActionFormScreen .form-label { margin-top: 1; }
    ActionFormScreen TextArea { height: 6; }
    ActionFormScreen #form-reason { height: auto; min-height: 1; color: $error; margin-top: 1; }
    ActionFormScreen #form-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self, title: str, fields: Sequence[FormField] = (), *, confirm: str | None = None
    ) -> None:
        super().__init__()
        self.form_title = title
        self.fields = tuple(fields)
        self.confirm = confirm

    # --- layout ---------------------------------------------------------------------------

    @staticmethod
    def field_id(field: FormField) -> str:
        return f"field-{field.name}"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.form_title, markup=False, classes="form-title")
            if self.confirm:
                yield Static(self.confirm, markup=False, id="form-confirm")
            for field in self.fields:
                yield Static(field.label, markup=False, classes="form-label")
                yield self._editor(field)
            yield Static("", markup=False, id="form-reason")
            yield Static(self._hints(), markup=False, id="form-hints")

    def _editor(self, field: FormField) -> Widget:
        ident = self.field_id(field)
        if field.kind == "choice":
            return ChoiceField(field.choices, field.default, id=ident)
        if field.kind == "text":
            return TextArea(field.default, soft_wrap=True, show_line_numbers=False, id=ident)
        return Input(value=field.default, id=ident)

    def _hints(self) -> str:
        if not self.fields:
            return "Enter or y: yes  Esc or n: no"
        if any(field.kind == "text" for field in self.fields):
            return "Ctrl+S: send  Esc: cancel  (Enter adds a line)"
        return "Enter or Ctrl+S: send  Esc: cancel"

    def on_mount(self) -> None:
        if self.fields:
            self.query_one(f"#{self.field_id(self.fields[0])}").focus()

    # --- answers --------------------------------------------------------------------------

    def value_of(self, field: FormField) -> str:
        """What the person has put in ``field``, trimmed."""
        widget = self.query_one(f"#{self.field_id(field)}")
        if isinstance(widget, ChoiceField):
            return widget.value
        if isinstance(widget, TextArea):
            return widget.text.strip()
        assert isinstance(widget, Input)
        return widget.value.strip()

    def reason(self) -> str:
        """Why the form cannot be sent yet (the first required field left empty), or ``""``."""
        for field in self.fields:
            if field.required and not self.value_of(field):
                if field.kind == "choice":
                    return f"{field.label}: nothing to choose from."
                return f"{field.label} is required."
        return ""

    def _say(self, text: str) -> None:
        self.query_one("#form-reason", Static).update(text)

    # --- keys -----------------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._say("")  # the reason goes once the person types again

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        event.stop()
        self._say("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_submit()

    def action_submit(self) -> None:
        why = self.reason()
        if why:
            self._say(why)
            self._focus_first_missing()
            return
        self.dismiss({field.name: self.value_of(field) for field in self.fields})

    def action_yes(self) -> None:
        if not self.fields:  # with fields, "y" is a letter for the person to type
            self.action_submit()

    def action_no(self) -> None:
        if not self.fields:  # with fields, "n" is a letter for the person to type
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _focus_first_missing(self) -> None:
        for field in self.fields:
            if field.required and not self.value_of(field):
                self.query_one(f"#{self.field_id(field)}").focus()
                return
