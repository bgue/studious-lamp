"""Header and footer widgets (P0-I2-T12). Provided by the supervisor; do not edit."""

from __future__ import annotations

from typing import Any

from helpers import run_pilot, screen_text
from rich.cells import cell_len
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_tui.widgets.footer import TlFooter, footer_lines
from tl_tui.widgets.header import TlHeader, header_line


def test_header_line_fills_the_width_with_breadcrumb_left_and_connection_right() -> None:
    line = header_line("ACME", "project:P123", "Records", "embedded", "user:dev", 60)
    assert cell_len(line) == 60
    assert line.startswith(" ACME ▸ P123 ▸ Records")
    assert line.endswith("● embedded · dev ")


def test_header_line_keeps_other_scopes_and_actors_verbatim() -> None:
    line = header_line("ACME", "company", "Records", "remote", "svc:sync", 60)
    assert line.startswith(" ACME ▸ company ▸ Records")
    assert line.endswith("● remote · svc:sync ")


def test_header_line_drops_the_right_part_then_truncates_the_left() -> None:
    no_right = header_line("ACME", "project:P123", "Records", "embedded", "user:dev", 30)
    assert no_right == " ACME ▸ P123 ▸ Records" + " " * 8
    cut = header_line("ACME", "project:P123", "Records", "embedded", "user:dev", 20)
    assert cut == " ACME ▸ P123 ▸ Reco…"
    assert cell_len(cut) == 20


def test_footer_lines_hints_and_empty_second_line() -> None:
    first, second = footer_lines("Enter open  Space select", "", "info", 0, 40)
    assert first == " Enter open  Space select"
    assert second == ""


def test_footer_lines_truncate_hints_with_an_ellipsis() -> None:
    first, _ = footer_lines("Enter open  Space select", "", "info", 0, 12)
    assert first == " Enter open…"
    assert cell_len(first) == 12


def test_footer_lines_status_prefixes_pair_severity_with_a_symbol() -> None:
    assert footer_lines("h", "Saved", "info", 0, 40)[1] == " Saved"
    assert footer_lines("h", "careful", "warning", 0, 40)[1] == " ! careful"
    assert footer_lines("h", "boom", "error", 0, 40)[1] == " ✗ boom"


def test_footer_lines_selection_count_is_right_aligned() -> None:
    _, second = footer_lines("h", "", "info", 2, 30)
    assert cell_len(second) == 30
    assert second.endswith("2 selected ")
    assert second.startswith("  ")
    _, both = footer_lines("h", "boom", "error", 12, 30)
    assert cell_len(both) == 30
    assert both.startswith(" ✗ boom ") and both.endswith("12 selected ")


def test_footer_lines_truncate_the_status_but_keep_the_count() -> None:
    _, second = footer_lines("h", "a very long status message indeed", "info", 2, 30)
    assert cell_len(second) == 30
    assert "…" in second
    assert second.endswith("2 selected ")


class Host(App[None]):
    def compose(self) -> ComposeResult:
        yield TlHeader(company="ACME", scope="project:P123", id="header")
        yield TlFooter(id="footer")


def test_header_widget_renders_and_follows_set_view() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        first = screen_text(app).splitlines()[0]
        assert first.startswith(" ACME ▸ P123 ▸ Records")
        assert first.endswith("● embedded · dev")
        app.query_one(TlHeader).set_view("FV-1001")
        await pilot.pause()
        assert screen_text(app).splitlines()[0].startswith(" ACME ▸ P123 ▸ FV-1001")

    run_pilot(app, scenario, size=(80, 10))


def test_header_widget_reflows_when_the_terminal_is_resized() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.resize_terminal(40, 10)
        await pilot.pause()
        first = screen_text(app).splitlines()[0]
        assert cell_len(first) <= 40
        assert first.endswith("● embedded · dev")
        await pilot.resize_terminal(24, 10)
        await pilot.pause()
        assert "embedded" not in screen_text(app).splitlines()[0]

    run_pilot(app, scenario, size=(80, 10))


def test_footer_widget_shows_hints_status_and_selection_count() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        footer = app.query_one(TlFooter)
        footer.set_hints("Enter open  [ ] step")
        footer.show_status("Saved FV-1001", "info")
        footer.set_selection_count(3)
        await pilot.pause()
        lines = [line for line in screen_text(app).splitlines() if line.strip()]
        assert lines[-2] == " Enter open  [ ] step"
        assert lines[-1].startswith(" Saved FV-1001")
        assert lines[-1].endswith("3 selected")
        footer.show_status("not found", "error")
        footer.set_selection_count(0)
        await pilot.pause()
        lines = [line for line in screen_text(app).splitlines() if line.strip()]
        assert lines[-1] == " ✗ not found"

    run_pilot(app, scenario, size=(80, 10))
