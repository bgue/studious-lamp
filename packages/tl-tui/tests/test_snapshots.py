"""Snapshot tests for the shell, grid, record view, psets tab, forms and narrow mode (P0-I2-T17).

Every scenario pins the terminal size (120x40 or 80x24) and runs against `FakeClient`, whose ids,
times and hashes are deterministic. Provided by the supervisor; do not edit. Create the stored
snapshots once with `--snapshot-update`, then run again without it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import FakeClient
from helpers import screen_text
from textual.pilot import Pilot
from textual.widgets import TabbedContent
from tl_tui.app import TlApp

WIDE = (120, 40)
NARROW = (80, 24)

Check = Callable[[Pilot[Any]], Awaitable[None]]


def _app() -> TlApp:
    return TlApp(FakeClient.with_valve_example())


def _expect(app: TlApp, *needles: str, keys: tuple[str, ...] = ()) -> Check:
    """A `run_before` step: press ``keys``, settle, and fail unless every needle is on screen."""

    async def step(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        if keys:
            await pilot.press(*keys)
        await pilot.pause()
        await pilot.pause()
        text = screen_text(app)
        for needle in needles:
            assert needle in text, f"{needle!r} not on screen:\n{text}"

    return step


def _open_tab(app: TlApp, tab: str, *needles: str) -> Check:
    async def step(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        app.query_one("#rv-tabs", TabbedContent).active = tab
        await pilot.pause()
        await pilot.pause()
        text = screen_text(app)
        for needle in needles:
            assert needle in text, f"{needle!r} not on screen:\n{text}"

    return step


def test_shell_wide(snap_compare: Any) -> None:
    app = _app()
    assert snap_compare(app, terminal_size=WIDE, run_before=_expect(app, "FV-1001", "Records"))


def test_shell_wide_panels_collapsed(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "FV-1001", keys=("f2", "f3"))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_shell_narrow(snap_compare: Any) -> None:
    app = _app()
    assert snap_compare(app, terminal_size=NARROW, run_before=_expect(app, "FV-1001"))


def test_shell_narrow_nav_overlay(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "P123", "Saved views (none yet)", keys=("f2",))
    assert snap_compare(app, terminal_size=NARROW, run_before=step)


def test_grid_selection_and_sort(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "Status ▲", "[x]", keys=("space", "down", "space", "right", "right", "s"))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_column_chooser(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "Choose columns", "valve_data.size_in", keys=("c",))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_record_view_details(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "FV-1001 · Control valve", "Conformance  ✓ ok", keys=("enter",))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_record_view_history(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "Pset.ValuesSet", "Record.Created", keys=("enter", "h"))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_record_view_narrow(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "FV-1001 · Control valve", keys=("enter",))
    assert snap_compare(app, terminal_size=NARROW, run_before=step)


def test_psets_tab_conformant(snap_compare: Any) -> None:
    app = _app()
    step = _open_tab(app, "tab-psets", "Property", "size_in", "Layer")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_psets_tab_nonconformant(snap_compare: Any) -> None:
    app = _app()

    async def step(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "down", "enter")  # FV-1003, installed without a size
        await pilot.pause()
        app.query_one("#rv-tabs", TabbedContent).active = "tab-psets"
        await pilot.pause()
        await pilot.pause()
        text = screen_text(app)
        assert "Conformance: ✗ nonconformant" in text and "✗" in text

    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_edit_form(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "Edit FV-1001", "Details", keys=("enter", "e"))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_new_record_form(snap_compare: Any) -> None:
    app = _app()
    step = _expect(app, "New record", "Key", "Title ●", keys=("n",))
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


@pytest.mark.parametrize("size", [WIDE, NARROW])
def test_status_message_in_the_footer(snap_compare: Any, size: tuple[int, int]) -> None:
    app = _app()
    step = _expect(app, "Created FV-9999", keys=())

    async def with_status(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        from tl_tui.widgets.footer import TlFooter

        app.query_one(TlFooter).show_status("Created FV-9999", "info")
        await step(pilot)

    assert snap_compare(app, terminal_size=size, run_before=with_status)
