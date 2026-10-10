"""Filter bar widget (P0-I4-T60). Provided; do not edit."""

from __future__ import annotations

from typing import Any

import pytest
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from textual.widgets import Input
from tl_tui.messages import FilterClosed, FilterSubmitted
from tl_tui.widgets.filter_bar import INPUT_OFFSET, FilterBar, caret_line, result_line
from tl_tui.widgets.grid import FilterResult


class Host(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield FilterBar(id="bar")

    def on_filter_submitted(self, message: FilterSubmitted) -> None:
        self.seen.append(message)

    def on_filter_closed(self, message: FilterClosed) -> None:
        self.seen.append(message)


def bar_of(app: Host) -> FilterBar:
    return app.query_one("#bar", FilterBar)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (FilterResult(True, None), ""),
        (FilterResult(True, 0), "0 matches"),
        (FilterResult(True, 1), "1 match"),
        (FilterResult(True, 12), "12 matches"),
        (FilterResult(False, None, "unexpected ')'", 14), "✗ unexpected ')' (position 14)"),
        (FilterResult(False, None, "server unreachable"), "✗ server unreachable"),
    ],
)
def test_result_line(result: FilterResult, expected: str) -> None:
    assert result_line(result) == expected


def test_caret_line_points_at_the_cell_of_the_character() -> None:
    assert caret_line("status:open )", None) == ""
    assert caret_line("status:open )", 0) == " " * INPUT_OFFSET + "^"
    assert caret_line("status:open )", 12) == " " * (INPUT_OFFSET + 12) + "^"
    assert caret_line("ab", 99) == " " * (INPUT_OFFSET + 2) + "^"  # past the end: after the text
    assert caret_line("日本 x", 3) == " " * (INPUT_OFFSET + 5) + "^"  # wide characters take 2 cells


def test_the_bar_is_hidden_until_it_is_opened_and_then_holds_the_focus() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        bar = bar_of(app)
        assert not bar.display
        bar.show_bar()
        await pilot.pause()
        assert bar.display
        assert isinstance(app.focused, Input) and app.focused.id == "filter-input"
        bar.hide_bar()
        await pilot.pause()
        assert not bar.display

    run_pilot(app, scenario)


def test_enter_posts_the_text_and_a_blank_line_posts_an_empty_text() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        bar = bar_of(app)
        bar.show_bar()
        await pilot.pause()
        await pilot.press(*"status:open", "enter")
        await pilot.pause()
        assert [m.text for m in app.seen if isinstance(m, FilterSubmitted)] == ["status:open"]
        assert bar.value == "status:open"
        bar.set_text("")
        await pilot.press("enter")
        await pilot.pause()
        texts = [m.text for m in app.seen if isinstance(m, FilterSubmitted)]
        assert texts == ["status:open", ""]

    run_pilot(app, scenario)


def test_escape_posts_filter_closed() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        bar_of(app).show_bar()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert [type(m) for m in app.seen] == [FilterClosed]

    run_pilot(app, scenario)


def test_a_count_is_shown_and_an_error_puts_a_caret_under_the_bad_character() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        bar = bar_of(app)
        bar.show_bar()
        bar.set_text("status:open )")
        await pilot.pause()
        bar.show_result(FilterResult(False, None, "unexpected ')'", 12))
        await pilot.pause()
        lines = screen_text(app).splitlines()
        assert any("✗ unexpected ')' (position 12)" in line for line in lines)
        caret_rows = [i for i, line in enumerate(lines) if line.strip() == "^"]
        assert len(caret_rows) == 1
        assert lines[caret_rows[0]].index("^") == INPUT_OFFSET + 12
        assert lines[caret_rows[0] - 2].lstrip().startswith("status:open )")
        bar.show_result(FilterResult(True, 3))
        await pilot.pause()
        text = screen_text(app)
        assert "3 matches" in text and "✗" not in text and "^" not in text

    run_pilot(app, scenario)


def test_user_text_and_messages_are_not_read_as_markup() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        bar = bar_of(app)
        bar.show_bar()
        bar.set_text("title:[bold]x")
        await pilot.pause()
        bar.show_result(FilterResult(False, None, "unknown field [red]foo[/]", 0))
        await pilot.pause()
        text = screen_text(app)
        assert "title:[bold]x" in text and "unknown field [red]foo[/]" in text

    run_pilot(app, scenario)
