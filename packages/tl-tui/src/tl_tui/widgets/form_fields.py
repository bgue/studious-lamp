"""Form field editors generated from field metadata (brief 10.2 forms, 6.3 property attributes).

`FieldEditor` edits one pset or core property. The input widget follows the field kind, the label
carries the unit and the enforcement marker (brief 10.6: never colour alone), and typed text is
validated inline. Saving is the caller's job: the editor reports its parsed value and whether it
changed.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Select, Static, Switch
from tl_schema.forms import FieldKind, FieldMeta

from tl_tui.text import unit_label

PLACEHOLDERS: dict[str, str] = {
    "int": "whole number",
    "decimal": "number",
    "quantity": "number",
    "date": "YYYY-MM-DD",
    "datetime": "YYYY-MM-DDTHH:MM",
    "json": "JSON value",
}

ENFORCEMENT_MARK = {"required": "●", "advisory": "○", "locked": "■"}


@dataclass(frozen=True)
class ParseResult:
    value: Any
    error: str | None = None


def _parse_number(text: str) -> ParseResult:
    try:
        number = float(text)
    except ValueError:
        return ParseResult(None, "Enter a number")
    if not math.isfinite(number):
        return ParseResult(None, "Enter a number")
    return ParseResult(number)


def parse_value(kind: FieldKind, text: str) -> ParseResult:
    """Parse typed text for a field kind; empty text is an unset value, never an error."""
    text = text.strip()
    if not text:
        return ParseResult(None)
    if kind == "int":
        try:
            return ParseResult(int(text))
        except ValueError:
            return ParseResult(None, "Enter a whole number")
    if kind in ("decimal", "quantity"):
        return _parse_number(text)
    if kind == "date":
        try:
            return ParseResult(date.fromisoformat(text).isoformat())
        except ValueError:
            return ParseResult(None, "Use YYYY-MM-DD")
    if kind == "datetime":
        try:
            return ParseResult(datetime.fromisoformat(text).isoformat())
        except ValueError:
            return ParseResult(None, "Use YYYY-MM-DDTHH:MM")
    if kind == "bool":
        lowered = text.lower()
        if lowered in ("true", "yes"):
            return ParseResult(True)
        if lowered in ("false", "no"):
            return ParseResult(False)
        return ParseResult(None, "Enter yes or no")
    if kind == "json":
        try:
            return ParseResult(json.loads(text))
        except json.JSONDecodeError as exc:
            return ParseResult(None, f"Invalid JSON: {exc.msg}")
    return ParseResult(text)


def format_initial(value: Any) -> str:
    """The text an input starts with for a stored value."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def label_text(meta: FieldMeta) -> str:
    """``size_in (in) ● @Design/Installed``: label, unit, enforcement mark, required states."""
    text = meta.label
    if meta.unit:
        text += f" ({unit_label(meta.unit)})"
    if meta.enforcement:
        text += f" {ENFORCEMENT_MARK[meta.enforcement]}"
    if meta.required_in_states:
        text += " @" + "/".join(meta.required_in_states)
    return text


class FieldEditor(Vertical):
    """One editable field: label, input widget (id ``input``), and an inline error line."""

    DEFAULT_CSS = """
    FieldEditor { height: auto; margin-bottom: 1; }
    FieldEditor > .field-error { color: $error; height: auto; }
    """

    class Edited(Message):
        """The user really changed the value (not the mount-time echo)."""

        def __init__(self, editor: FieldEditor) -> None:
            super().__init__()
            self.editor = editor

    def __init__(self, meta: FieldMeta, value: Any = None, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.meta = meta
        self.initial = value
        self._error: str | None = None
        # Child widgets are built in compose: an Input with text needs a running app.
        self._control: Widget
        self._error_static: Static
        # The raw widget value the editor last saw; the mount-time echo matches it and is ignored.
        self._last_raw: Any

    def _build_control(self) -> Widget:
        value = self.initial
        meta = self.meta
        if meta.kind == "bool":
            self._last_raw = bool(value)
            return Switch(bool(value), disabled=meta.readonly, id="input")
        if meta.kind == "enum":
            enum_values = meta.enum_values or []
            codes = [option.code for option in enum_values]
            selected: Any = value if value in codes else Select.NULL
            options = [
                (option.label + (f" → {option.crosswalk}" if option.crosswalk else ""), option.code)
                for option in enum_values
            ]
            self._last_raw = selected
            return Select[str](options, value=selected, disabled=meta.readonly, id="input")
        text = format_initial(value)
        self._last_raw = text
        return Input(
            value=text,
            placeholder=PLACEHOLDERS.get(meta.kind, ""),
            disabled=meta.readonly,
            id="input",
        )

    def compose(self) -> ComposeResult:
        self._control = self._build_control()
        self._error_static = Static("", classes="field-error", markup=False)
        yield Static(label_text(self.meta), classes="field-label", markup=False)
        yield self._control
        yield self._error_static

    @property
    def input_widget(self) -> Widget:
        return self._control

    @property
    def value(self) -> Any:
        control = self._control
        if isinstance(control, Switch):
            return control.value
        if isinstance(control, Select):
            return None if control.is_blank() else control.value
        if isinstance(control, Input):
            return parse_value(self.meta.kind, control.value).value
        return None

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def changed(self) -> bool:
        control = self._control
        if isinstance(control, Input) and parse_value(self.meta.kind, control.value).error:
            return True
        if isinstance(control, Switch) and not control.value and self.initial is None:
            return False
        return self.value != self.initial

    def validate(self) -> bool:
        control = self._control
        if isinstance(control, Input):
            result = parse_value(self.meta.kind, control.value)
            self.set_error(result.error)
        return self._error is None

    def set_error(self, message: str | None) -> None:
        self._error = message
        self._error_static.update(message or "")

    def _raw_changed(self, raw: Any) -> None:
        if raw == self._last_raw:
            return
        self._last_raw = raw
        self.validate()
        self.post_message(self.Edited(self))

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._raw_changed(event.value)

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self._raw_changed(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        event.stop()
        self._raw_changed(event.value)
