"""Command palette: fuzzy scoring, rows and the modal (P0-I3-T11; brief 10.2, sketch 3)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, OptionList
from tl_core.services.link_queries import LinkTarget
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS, AppCommand
from tl_tui.widgets.help_screen import HelpScreen
from tl_tui.widgets.palette import (
    CommandPalette,
    PaletteChoice,
    PaletteRow,
    build_rows,
    fuzzy_score,
    row_line,
)
from tl_tui.widgets.record_view import RecordView

COMMANDS = (
    AppCommand("new-record", "New record", "n", "new_record"),
    AppCommand("link", "Link the open record", "l", "link"),
    AppCommand("help", "Show the key map", "F1", "help"),
    AppCommand("trace", "Trace the open record", "", "trace"),
)


def target(key: str, title: str = "A title", status: str | None = "Open") -> LinkTarget:
    return LinkTarget(
        id=f"id-{key}",
        key=key,
        type="core.Record",
        title=title,
        status=status,
        scope=SCOPE,
        link_total=0,
    )


# --- fuzzy_score ------------------------------------------------------------------------------


def test_an_empty_query_matches_everything_with_score_zero() -> None:
    assert fuzzy_score("", "anything") == 0
    assert fuzzy_score("   ", "anything") == 0


def test_a_prefix_match_scores_its_characters_bonuses_and_the_prefix_bonus() -> None:
    # n(0): 1 + word start 6; e: 1 + consecutive 4; w: 1 + 4; whole query is a prefix: +20
    assert fuzzy_score("new", "New record") == 37
    assert fuzzy_score("NEW", "new record") == 37


def test_word_starts_score_higher_than_scattered_characters() -> None:
    # n at 0: 1 + 6; r after a space: 1 + 6; not a prefix
    assert fuzzy_score("nr", "New record") == 14
    # n at 2 (no bonus), r at 4 (no bonus): 1 + 1
    assert fuzzy_score("nr", "Winery") == 2


def test_a_query_that_is_not_a_subsequence_gives_none() -> None:
    assert fuzzy_score("xyz", "New record") is None
    assert fuzzy_score("wen", "New record") is None  # letters in the wrong order
    assert fuzzy_score("newww", "New record") is None  # a character cannot be used twice


def test_prefix_beats_word_start_beats_scattered() -> None:
    prefix = fuzzy_score("rec", "Record view") or 0
    word_start = fuzzy_score("rec", "New record") or 0
    scattered = fuzzy_score("rec", "Careful decision") or 0
    assert prefix > word_start > scattered > 0


def test_spaces_in_the_query_are_ignored() -> None:
    assert fuzzy_score("n r", "New record") == fuzzy_score("nr", "New record")


# --- build_rows ---------------------------------------------------------------------------------


def test_with_no_records_and_no_query_all_commands_are_listed_in_order() -> None:
    rows = build_rows("", COMMANDS, [])
    assert [r.kind for r in rows] == ["header", "command", "command", "command", "command"]
    assert rows[0].label == "Commands"
    assert [r.label for r in rows[1:]] == [c.label for c in COMMANDS]
    assert [r.hint for r in rows[1:]] == ["n", "l", "F1", ""]
    assert rows[1].choice == PaletteChoice("command", command_id="new-record")


def test_records_come_first_with_key_title_and_status() -> None:
    rows = build_rows("", COMMANDS, [target("FV-1001", "Control valve", "Design"), target("FV-2")])
    assert [r.kind for r in rows[:4]] == ["header", "record", "record", "header"]
    assert rows[0].label == "Records"
    first = rows[1]
    assert (first.label, first.detail, first.hint) == ("FV-1001", "Control valve · Design", "Enter")
    assert first.choice == PaletteChoice("record", key="FV-1001")
    assert rows[3].label == "Commands"


def test_a_record_without_a_status_shows_a_dash() -> None:
    rows = build_rows("", [], [target("FV-1", "T", None)])
    assert rows[1].detail == "T · —"


def test_commands_are_filtered_and_ranked_by_the_query() -> None:
    rows = build_rows("link", COMMANDS, [])
    assert [r.label for r in rows if r.kind == "command"] == ["Link the open record"]
    rows = build_rows("op", COMMANDS, [])
    labels = [r.label for r in rows if r.kind == "command"]
    # Link and Trace score the same (order kept); "Show the key map" has no word-start bonus.
    assert labels == ["Link the open record", "Trace the open record", "Show the key map"]
    rows = build_rows("show", COMMANDS, [])
    assert [r.label for r in rows if r.kind == "command"] == ["Show the key map"]


def test_ties_keep_the_original_order_and_better_matches_come_first() -> None:
    commands = (
        AppCommand("a", "Open the record list", "", "x"),
        AppCommand("b", "Record", "", "y"),
    )
    rows = build_rows("rec", commands, [])
    assert [r.label for r in rows if r.kind == "command"] == ["Record", "Open the record list"]


def test_nothing_matching_gives_no_rows() -> None:
    assert build_rows("zzzz", COMMANDS, []) == []


def test_mode_narrows_the_sections() -> None:
    records = [target("FV-1")]
    only_records = build_rows("fv", COMMANDS, records, "records")
    assert [r.kind for r in only_records] == ["header", "record"]
    only_commands = build_rows("", COMMANDS, records, "commands")
    assert {r.kind for r in only_commands} == {"header", "command"}
    assert build_rows("", COMMANDS, records, "all")[0].label == "Records"


# --- row_line -----------------------------------------------------------------------------------


def test_header_lines_are_filled_with_rules() -> None:
    line = row_line(PaletteRow("header", "Records"), False, 20)
    assert line == "─ Records ──────────"
    assert len(line) == 20


def test_a_command_line_has_the_hint_on_the_right() -> None:
    row = PaletteRow("command", "New record", "", "n")
    assert row_line(row, True, 20) == "▶ New record       n"
    assert row_line(row, False, 20) == "  New record       n"


def test_a_record_line_shows_key_and_detail() -> None:
    row = PaletteRow("record", "FV-1001", "Control valve · Design", "Enter")
    line = row_line(row, True, 50)
    assert line.startswith("▶ FV-1001  Control valve · Design  ")
    assert line.endswith("  Enter")
    assert len(line) == 50


def test_a_long_line_is_cut_with_an_ellipsis_and_keeps_the_hint() -> None:
    row = PaletteRow("record", "FV-1001", "A very long title that does not fit", "Enter")
    line = row_line(row, False, 30)
    assert len(line) == 30
    assert line.endswith("… Enter")
    assert line.startswith("  FV-1001  A very")


@pytest.mark.parametrize("width", [8, 12, 40])
def test_lines_are_exactly_the_width(width: int) -> None:
    for row in (
        PaletteRow("header", "Commands"),
        PaletteRow("command", "Show the key map", "", "F1"),
        PaletteRow("record", "FV-1", "T · Open", "Enter"),
    ):
        assert len(row_line(row, False, width)) == width


# --- the modal ----------------------------------------------------------------------------------


class Host(App[None]):
    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client
        self.results: list[PaletteChoice | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        self.push_screen(CommandPalette(self.client, SCOPE), self.results.append)


def _type(app: Host, text: str) -> None:
    app.screen.query_one("#palette-input", Input).value = text


def test_it_opens_with_the_commands_listed() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Commands" in text
        assert "New record" in text and "Show the key map" in text
        assert "Records" not in text.replace("Link the selection", "")  # no record section yet

    run_pilot(app, scenario, size=(110, 36))


def test_typing_a_key_searches_records_and_enter_chooses_the_first() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _type(app, "fv-100")
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1001" in text and "FV-1002" in text and "FV-1003" in text
        assert "Control valve FCV" in text
        assert "search_linkable" in client.calls
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [PaletteChoice("record", key="FV-1002")]

    run_pilot(app, scenario, size=(110, 36))


def test_typing_a_command_name_filters_commands_and_enter_chooses_it() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _type(app, "key map")
        await pilot.pause()
        assert "Show the key map" in screen_text(app)
        assert "New record" not in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [PaletteChoice("command", command_id="help")]

    run_pilot(app, scenario, size=(110, 36))


def test_tab_cycles_the_filter() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "Showing: all" in screen_text(app)
        await pilot.press("tab")
        await pilot.pause()
        assert "Showing: records" in screen_text(app)
        assert "New record" not in screen_text(app)
        await pilot.press("tab")
        await pilot.pause()
        assert "Showing: commands" in screen_text(app)
        assert "New record" in screen_text(app)
        await pilot.press("tab")
        await pilot.pause()
        assert "Showing: all" in screen_text(app)

    run_pilot(app, scenario, size=(110, 36))


def test_escape_closes_with_none() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None]

    run_pilot(app, scenario, size=(110, 36))


def test_enter_with_nothing_matching_stays_open() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _type(app, "zzzzzz")
        await pilot.pause()
        assert app.screen.query_one("#palette-list", OptionList).option_count == 0
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []

    run_pilot(app, scenario, size=(110, 36))


def test_the_default_commands_are_the_app_commands() -> None:
    palette = CommandPalette(FakeClient(), SCOPE)
    assert palette.commands == APP_COMMANDS


# --- the keys of the app ------------------------------------------------------------------------


def test_ctrl_p_and_colon_open_the_palette_once() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        for key in ("ctrl+p", "colon"):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("ctrl+p")  # no second palette on top
            await pilot.pause()
            assert len(app.screen_stack) == 2
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, CommandPalette)

    run_pilot(app, scenario, size=(120, 40))


def test_choosing_a_record_opens_it_and_starts_a_trail() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()
        app.screen.query_one("#palette-input", Input).value = "fv-1003"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        view = app.query_one(RecordView)
        assert view.key == "FV-1003"
        assert app.history.current == (SCOPE, "FV-1003")

    run_pilot(app, scenario, size=(120, 40))


def test_choosing_a_command_runs_the_app_action() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("colon")
        await pilot.pause()
        app.screen.query_one("#palette-input", Input).value = "key map"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

    run_pilot(app, scenario, size=(120, 40))


def test_the_l_w_t_keys_are_typed_into_the_palette_not_run() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()
        await pilot.press("l", "w", "t")
        await pilot.pause()
        assert app.screen.query_one("#palette-input", Input).value == "lwt"
        assert isinstance(app.screen, CommandPalette)

    run_pilot(app, scenario, size=(120, 40))
