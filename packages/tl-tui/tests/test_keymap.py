"""Key map data, the help screen, and `F1`/`?` (P0-I2-T17b). Provided; do not edit."""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.binding import Binding
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.keymap import CONTEXTS, KEYMAP, KeyEntry, help_text
from tl_tui.widgets.edit_form import EditForm
from tl_tui.widgets.footer import DEFAULT_HINTS
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.help_screen import HelpScreen
from tl_tui.widgets.link_picker import LinkPicker
from tl_tui.widgets.links_tab import LinksTab
from tl_tui.widgets.new_record_form import NewRecordForm
from tl_tui.widgets.palette import CommandPalette
from tl_tui.widgets.record_view import RecordView
from tl_tui.widgets.ref_tray import ReferenceTrayScreen
from tl_tui.widgets.trace_tab import TraceTab
from tl_tui.widgets.workflow_menu import WorkflowMenu

OWNERS: dict[str, Any] = {
    "TlApp": TlApp,
    "RecordGrid": RecordGrid,
    "RecordView": RecordView,
    "EditForm": EditForm,
    "NewRecordForm": NewRecordForm,
    "LinksTab": LinksTab,
    "TraceTab": TraceTab,
    "CommandPalette": CommandPalette,
    "LinkPicker": LinkPicker,
    "ReferenceTrayScreen": ReferenceTrayScreen,
    "WorkflowMenu": WorkflowMenu,
}


def _binding_keys(owner: Any) -> set[str]:
    keys: set[str] = set()
    for binding in owner.BINDINGS:
        if isinstance(binding, Binding):
            keys.update(binding.key.split(","))
        else:
            keys.update(binding[0].split(","))
    return keys


def test_every_documented_binding_exists_on_its_owner() -> None:
    for entry in KEYMAP:
        if entry.owner is None:
            assert entry.binding is None
            continue
        assert entry.binding is not None
        assert entry.binding in _binding_keys(OWNERS[entry.owner]), entry


def test_every_context_has_entries_and_every_entry_has_a_known_context() -> None:
    assert CONTEXTS == (
        "App",
        "Grid",
        "Record view",
        "Links tab",
        "Trace tab",
        "Palette",
        "Link picker",
        "Reference tray",
        "Workflow menu",
        "Forms",
    )
    assert {e.context for e in KEYMAP} == set(CONTEXTS)
    assert all(isinstance(e, KeyEntry) and e.keys and e.description for e in KEYMAP)


def test_the_brief_keys_that_exist_today_are_documented() -> None:
    documented = " ".join(e.keys for e in KEYMAP)
    keys = ("n", "e", "Ctrl+S", "Esc", "Enter", "Space", "Ctrl+A", "F6", "[  ]", "F1")
    for key in (*keys, "Ctrl+P", "l", "R", "F4", "w", "t", "Alt+Left"):
        assert key in documented


def test_help_text_has_a_heading_per_context_and_one_line_per_entry() -> None:
    lines = help_text().splitlines()
    assert [line for line in lines if line and not line.startswith(" ")] == list(CONTEXTS)
    assert len([line for line in lines if line.startswith("  ")]) == len(KEYMAP)
    assert "  F1  ?                         Show this key map" in lines
    assert "  Space                         Select or unselect the row" in lines


def test_default_hints_mention_help() -> None:
    assert DEFAULT_HINTS.startswith("F1 help")


def test_f1_and_question_mark_open_the_help_screen_and_escape_closes_it() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        for key in ("f1", "question_mark"):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            text = screen_text(app)
            assert "Key map" in text and "Select all loaded rows" in text
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)

    run_pilot(app, scenario, size=(120, 50))


def test_help_screen_closes_with_the_same_key_and_does_not_stack() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert len(app.screen_stack) == 1

    run_pilot(app, scenario, size=(120, 50))


def test_question_mark_does_not_open_help_over_a_form() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, NewRecordForm)
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, NewRecordForm)

    run_pilot(app, scenario, size=(120, 50))
