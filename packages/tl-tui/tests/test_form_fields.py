"""Form field editors: parsing, widgets per kind, inline validation (P0-I2-T16a). Provided."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import valve_form_metadata
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Select, Switch
from tl_schema.forms import EnumValue, FieldKind, FieldMeta
from tl_tui.widgets.form_fields import (
    FieldEditor,
    ParseResult,
    format_initial,
    label_text,
    parse_value,
)


def _meta(kind: str, **extra: Any) -> FieldMeta:
    base: dict[str, Any] = {
        "path": "psets.p.f",
        "label": "f",
        "description": "d",
        "kind": kind,
        "layer": "standard",
        "group": "p",
        "order": 1,
    }
    base.update(extra)
    return FieldMeta.model_validate(base)


@pytest.mark.parametrize(
    ("kind", "text", "value", "error"),
    [
        ("int", "42", 42, None),
        ("int", " 7 ", 7, None),
        ("int", "4.5", None, "Enter a whole number"),
        ("decimal", "6.5", 6.5, None),
        ("decimal", "abc", None, "Enter a number"),
        ("decimal", "nan", None, "Enter a number"),
        ("decimal", "inf", None, "Enter a number"),
        ("quantity", "2", 2.0, None),
        ("date", "2026-10-09", "2026-10-09", None),
        ("date", "09/10/2026", None, "Use YYYY-MM-DD"),
        ("datetime", "2026-10-09T09:30", "2026-10-09T09:30:00", None),
        ("datetime", "tomorrow", None, "Use YYYY-MM-DDTHH:MM"),
        ("bool", "Yes", True, None),
        ("bool", "no", False, None),
        ("bool", "maybe", None, "Enter yes or no"),
        ("json", '{"a": 1}', {"a": 1}, None),
        ("string", "  hello ", "hello", None),
        ("text", "line", "line", None),
        ("ref", "@party:acme", "@party:acme", None),
        ("int", "", None, None),
        ("decimal", "   ", None, None),
    ],
)
def test_parse_value(kind: FieldKind, text: str, value: Any, error: str | None) -> None:
    assert parse_value(kind, text) == ParseResult(value, error)


def test_parse_value_json_error_names_the_problem() -> None:
    result = parse_value("json", "{oops")
    assert result.value is None
    assert result.error is not None and result.error.startswith("Invalid JSON: ")


def test_format_initial() -> None:
    assert format_initial(None) == ""
    assert format_initial(6.0) == "6.0"
    assert format_initial(True) == "yes"
    assert format_initial({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert format_initial("x") == "x"


def test_label_text_has_unit_marker_and_states() -> None:
    size = valve_form_metadata().psets[0].fields[0]
    assert label_text(size) == "size_in (in) ● @Design/Installed"
    assert label_text(_meta("string")) == "f"
    assert label_text(_meta("string", enforcement="locked")) == "f ■"
    assert label_text(_meta("string", enforcement="advisory", unit="furlong")) == "f (furlong) ○"


class Host(App[None]):
    def __init__(self, *editors: FieldEditor) -> None:
        super().__init__()
        self.editors = editors
        self.edited: list[FieldEditor] = []

    def compose(self) -> ComposeResult:
        yield from self.editors

    def on_field_editor_edited(self, message: FieldEditor.Edited) -> None:
        self.edited.append(message.editor)


def test_decimal_editor_validates_inline_and_tracks_changes() -> None:
    editor = FieldEditor(_meta("decimal", unit="[in_i]"), 6.0)
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        field = editor.query_one(Input)
        assert field.value == "6.0" and field.placeholder == "number"
        assert editor.value == 6.0 and not editor.changed and editor.error is None
        field.value = "6.5"
        await pilot.pause()
        assert editor.value == 6.5 and editor.changed and editor.error is None
        field.value = "abc"
        await pilot.pause()
        assert editor.value is None and editor.changed
        assert editor.error == "Enter a number" and not editor.validate()
        assert "Enter a number" in screen_text(app)
        field.value = "6.0"
        await pilot.pause()
        assert not editor.changed and editor.error is None and editor.validate()
        assert "Enter a number" not in screen_text(app)
        assert len(app.edited) == 3 and all(e is editor for e in app.edited)

    run_pilot(app, scenario, size=(80, 12))


def test_clearing_an_input_means_unset_without_an_error() -> None:
    editor = FieldEditor(_meta("int"), 5)
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        editor.query_one(Input).value = ""
        await pilot.pause()
        assert editor.value is None and editor.error is None and editor.changed

    run_pilot(app, scenario, size=(80, 12))


def test_set_error_shows_a_server_side_message() -> None:
    editor = FieldEditor(_meta("string"), "a")
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        editor.set_error("locked by company standard")
        await pilot.pause()
        assert editor.error == "locked by company standard"
        assert "locked by company standard" in screen_text(app)
        editor.set_error(None)
        await pilot.pause()
        assert editor.error is None

    run_pilot(app, scenario, size=(80, 12))


def test_bool_editor_uses_a_switch() -> None:
    editor = FieldEditor(_meta("bool"), None)
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        switch = editor.query_one(Switch)
        assert editor.value is False and not editor.changed
        switch.value = True
        await pilot.pause()
        assert editor.value is True and editor.changed

    run_pilot(app, scenario, size=(80, 12))


def test_enum_editor_uses_a_select_with_crosswalk_labels() -> None:
    meta = valve_form_metadata().psets[0].fields[1]  # body_material, extensible list
    editor = FieldEditor(meta, "SS316L")
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        select = editor.query_one(Select)
        assert editor.value == "SS316L" and not editor.changed
        select.value = "SS316L-NACE"
        await pilot.pause()
        assert editor.value == "SS316L-NACE" and editor.changed
        select.clear()
        await pilot.pause()
        assert editor.value is None and editor.changed

    run_pilot(app, scenario, size=(80, 12))


def test_enum_with_an_unknown_initial_code_starts_blank() -> None:
    meta = _meta("enum", enum_values=[EnumValue(code="A", label="Alpha")])
    editor = FieldEditor(meta, "ZZZ")
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert editor.value is None

    run_pilot(app, scenario, size=(80, 12))


def test_readonly_fields_are_disabled() -> None:
    editor = FieldEditor(_meta("string", readonly=True, layer="enrichment"), "ai")
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert editor.input_widget.disabled
        assert editor.value == "ai" and not editor.changed

    run_pilot(app, scenario, size=(80, 12))


def test_label_is_shown_literally() -> None:
    editor = FieldEditor(_meta("string", label="[odd] label"), None)
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "[odd] label" in screen_text(app)

    run_pilot(app, scenario, size=(80, 12))


def test_empty_and_unknown_initial_values_start_unchanged() -> None:
    text_editor = FieldEditor(_meta("string"), "")
    enum_editor = FieldEditor(
        _meta("enum", enum_values=[EnumValue(code="A", label="Alpha")]), "ZZZ"
    )
    app = Host(text_editor, enum_editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert text_editor.initial is None and not text_editor.changed
        assert enum_editor.initial is None and not enum_editor.changed

    run_pilot(app, scenario, size=(80, 16))


def test_select_option_labels_are_not_parsed_as_markup() -> None:
    meta = _meta("enum", enum_values=[EnumValue(code="A", label="[bold]Alpha[/bold]")])
    editor = FieldEditor(meta, "A")
    app = Host(editor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "[bold]Alpha[/bold]" in screen_text(app)

    run_pilot(app, scenario, size=(80, 16))
