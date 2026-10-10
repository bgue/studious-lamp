"""Snapshot tests for the P0-I3 screens: links tab, picker, palette, tray, trace, workflow menu.

Every scenario pins the terminal size (120x40 or 80x24) and runs against `FakeClient`, whose ids,
times and hashes are deterministic. Create the stored snapshots once with `--snapshot-update`,
then run again without it. A snapshot changes only when a screen legitimately changes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import FakeClient
from helpers import screen_text
from textual.pilot import Pilot
from tl_tui.app import TlApp

WIDE = (120, 40)
NARROW = (80, 24)

Check = Callable[[Pilot[Any]], Awaitable[None]]


def _client() -> FakeClient:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002", "raised_against", pin="B")
    client.seed_link("FV-1003", "FV-1001", "requires", status="stale", pin="A")
    client.seed_link("FV-1001", "FV-1003", "references", status="suggested")
    return client


def _expect(app: TlApp, keys: tuple[str, ...], *needles: str) -> Check:
    """A `run_before` step: press ``keys`` one by one, then fail unless every needle is shown."""

    async def step(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        await pilot.pause()
        text = screen_text(app)
        for needle in needles:
            assert needle in text, f"{needle!r} not on screen:\n{text}"

    return step


def test_record_view_header_badges(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("enter",), "FV-1001", "since", "1 link ·")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_links_tab(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("enter", "3"), "FV-1002", "FV-1003")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_links_tab_narrow(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("enter", "3"), "FV-1002")
    assert snap_compare(app, terminal_size=NARROW, run_before=step)


def test_link_picker(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("enter", "l"), "FV-1002")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_command_palette(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("ctrl+p",), "Commands")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_reference_tray(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("R", "down", "R", "down", "enter", "f4"), "Reference tray (2)")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_trace_tab(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("enter", "t"), "FV-1002")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)


def test_workflow_menu(snap_compare: Any) -> None:
    app = TlApp(_client())
    step = _expect(app, ("enter", "w"), "FV-1001")
    assert snap_compare(app, terminal_size=WIDE, run_before=step)
