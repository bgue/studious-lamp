"""The shared LogScreen on a small test host: three rows and fake actions (P1-UX2-S2).

A log is tested the same way: subclass ``LogScreen`` with a few rows, push it on a bare ``App`` and
drive it with a pilot. ``settle`` waits for the workers that read the rows and the actions.
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from textual.worker import WorkerFailed
from tl_core.services.errors import ServiceError
from tl_tui.display import DisplayMode, mode_of
from tl_tui.widgets.log_screen import (
    LogAction,
    LogScreen,
    check_action_keys,
    usable_actions,
)


@dataclass(frozen=True)
class Item:
    key: str
    number: str
    title: str
    state: str


ITEMS = [
    Item("r1", "P123-RFI-0001", "Pile cap clash at AZ203", "Open"),
    Item("r2", "P123-RFI-0002", "Cable tray route [rev B, draft]", "Answered"),
    Item("r3", "P123-RFI-0003", "Fire damper access", "Closed"),
]


@dataclass
class Probe:
    """What the host did, and the levers a test pulls."""

    items: list[Item] = field(default_factory=lambda: list(ITEMS))
    loads: int = 0
    asked: list[str] = field(default_factory=list)
    ran: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    refuse: bool = False
    fail_actions_for: str | None = None
    hold: dict[str, threading.Event] = field(default_factory=dict)  # row key -> release
    actions: dict[str, tuple[tuple[str, str], ...]] = field(
        default_factory=lambda: {
            "r1": (("a", "Answer"), ("c", "Close")),
            "r2": (("c", "Close"), ("ctrl+e", "Escalate")),
            "r3": (),
        }
    )


class Host(LogScreen[Item]):
    LOG_NAME = "RFI Log"
    KEY_HINTS = "/ filter  o open only  F5 reload  Esc back"

    def __init__(self, probe: Probe) -> None:
        super().__init__()
        self.probe = probe

    def log_project(self) -> str:
        return "P123"

    def columns(self) -> Sequence[str]:
        return ("Number", "Title", "State")

    def load_rows(self) -> Sequence[Item]:
        self.probe.loads += 1
        return list(self.probe.items)

    def row_key(self, row: Item) -> str:
        return row.key

    def row_cells(self, row: Item) -> Sequence[str]:
        state = row.state.upper() if mode_of(self.app).technical else row.state
        return (row.number, row.title, state)

    def row_record(self, row: Item) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: Item | None) -> str:
        return (
            "Nothing selected." if row is None else f"{row.number}\n{row.title}\nState: {row.state}"
        )

    def actions_for(self, row: Item) -> Sequence[LogAction]:
        self.probe.asked.append(row.key)
        gate = self.probe.hold.get(row.key)
        if gate is not None:
            assert gate.wait(5), "the test never released the slow answer"
        if self.probe.fail_actions_for == row.key:
            raise ServiceError("cannot work out the actions")
        return [
            LogAction(key, label, self.runner(f"{label}:{row.key}"))
            for key, label in self.probe.actions[row.key]
        ]

    def runner(self, name: str) -> Callable[[], None]:
        def run() -> None:
            if self.probe.refuse:
                raise ServiceError("Only the author may close this.")
            self.probe.ran.append(name)

        return run

    def summary_text(self) -> str:
        return f"{len(self.shown)} of {len(self.rows)} RFIs"

    def open_row(self, row: Item) -> None:
        self.probe.opened.append(row.key)


class HostApp(App[None]):
    def __init__(self, screen: Host) -> None:
        super().__init__()
        self.host = screen

    def on_mount(self) -> None:
        self.push_screen(self.host)


async def settle(pilot: Pilot[Any]) -> None:
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def until(pilot: Pilot[Any], done: Callable[[], bool]) -> None:
    """Wait (without joining the workers) until ``done()``; a slow worker may still be running."""
    for _ in range(100):
        await pilot.pause(0.05)
        if done():
            return
    raise AssertionError("gave up waiting")


def drive(
    steps: Callable[[Pilot[Any], Host, Probe], Awaitable[None]],
    probe: Probe | None = None,
    size: tuple[int, int] = (100, 30),
    *,
    join: bool = True,
) -> Probe:
    probe = probe or Probe()
    host = Host(probe)
    app = HostApp(host)

    async def go(pilot: Pilot[Any]) -> None:
        if join:
            await settle(pilot)
        else:
            await until(pilot, lambda: bool(host.shown))
        assert pilot.app.screen is host
        await steps(pilot, host, probe)

    run_pilot(app, go, size=size)
    return probe


def text_of(screen: Host, widget_id: str) -> str:
    return str(screen.query_one(widget_id, Static).render())


def crumb(screen: Host) -> str:
    return text_of(screen, "#log-crumb")


def bar(screen: Host) -> str:
    return text_of(screen, "#log-actions")


def status(screen: Host) -> str:
    return text_of(screen, "#log-status")


# --- the layout --------------------------------------------------------------------------


def test_the_screen_lists_the_rows_with_plain_cells_and_the_hints() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        table = screen.query_one("#log-table", DataTable)
        assert table.row_count == 3
        shown = screen_text(pilot.app)
        assert "P123-RFI-0001" in shown and "[rev B, draft]" in shown  # not read as markup
        assert text_of(screen, "#log-keys") == Host.KEY_HINTS
        assert status(screen) == "3 of 3 RFIs"  # the summary line
        for ident in ("crumb", "filter", "table", "panel", "actions", "keys", "status"):
            screen.query_one(f"#log-{ident}")

    drive(steps)


def test_breadcrumb_follows_the_highlighted_row() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        assert crumb(screen) == "P123 › RFI Log › P123-RFI-0001: Pile cap clash at AZ203"
        await pilot.press("down")
        await settle(pilot)
        assert crumb(screen) == "P123 › RFI Log › P123-RFI-0002: Cable tray route [rev B, draft]"
        assert "P123-RFI-0002" in text_of(screen, "#log-panel-text")

    drive(steps)


def test_breadcrumb_is_the_log_alone_with_no_rows() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        assert crumb(screen) == "P123 › RFI Log"
        assert text_of(screen, "#log-panel-text") == "Nothing selected."
        assert bar(screen) == ""

    drive(steps, Probe(items=[]))


def test_breadcrumb_shortens_the_title_on_a_narrow_terminal() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        line = crumb(screen)
        assert line.startswith("P123 › RFI Log › P123-RFI-0001: Pile") and line.endswith("…")
        assert len(line) <= 40 - 2

    drive(steps, size=(40, 24))


def test_the_record_part_of_the_breadcrumb_is_highlighted() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        rendered = screen.query_one("#log-crumb", Static).render()
        marked = [rendered.plain[span.start : span.end] for span in rendered.spans]  # type: ignore[attr-defined]
        assert marked == ["P123-RFI-0001: Pile cap clash at AZ203"]

    drive(steps)


def test_layout_switches_at_160_columns() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        table = screen.query_one("#log-table", DataTable)
        panel = screen.query_one("#log-panel")
        await pilot.press("down")
        await settle(pilot)
        assert not screen.has_class("-wide") and panel.region.y >= table.region.bottom

        await pilot.resize_terminal(159, 30)
        await settle(pilot)
        assert not screen.has_class("-wide")
        await pilot.resize_terminal(160, 30)
        await settle(pilot)
        assert screen.has_class("-wide")
        assert panel.region.x >= table.region.right and panel.region.y == table.region.y
        assert table.cursor_row == 1 and crumb(screen).endswith(
            "[rev B, draft]"
        )  # the cursor stayed

        await pilot.resize_terminal(159, 30)
        await settle(pilot)
        assert not screen.has_class("-wide") and table.cursor_row == 1

    drive(steps, size=(100, 30))


def test_a_wide_terminal_starts_wide() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        assert screen.has_class("-wide")

    drive(steps, size=(170, 30))


# --- the actions bar ---------------------------------------------------------------------


def test_the_bar_shows_only_the_supplied_actions_and_follows_the_highlight() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        assert bar(screen) == "[a] Answer  [c] Close  [Enter] Open record"
        await pilot.press("down")
        await settle(pilot)
        assert bar(screen) == "[c] Close  [Ctrl+E] Escalate  [Enter] Open record"
        await pilot.press("down")
        await settle(pilot)
        assert bar(screen) == "[Enter] Open record"
        assert probe.asked == ["r1", "r2", "r3"]

    drive(steps)


def test_stale_actions_answer_is_dropped() -> None:
    probe = Probe()
    probe.hold["r1"] = threading.Event()  # row 1's answer is slow
    both = "[c] Close  [Ctrl+E] Escalate  [Enter] Open record"

    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        try:
            await pilot.press("down")  # row 2 is highlighted while row 1 is still being asked
            await until(pilot, lambda: bar(screen) == both)
            probe.hold["r1"].set()  # now the old answer arrives
            await settle(pilot)
            assert probe.asked == ["r1", "r2"]
            assert bar(screen) == both
            assert [a.key for a in screen.offered] == ["c", "ctrl+e"]
            await pilot.press("a")  # row 1's key must not run anything on row 2
            await settle(pilot)
            assert probe.ran == []
        finally:
            probe.hold["r1"].set()

    drive(steps, probe, join=False)


def test_a_failed_actions_read_empties_the_bar_and_says_why() -> None:
    probe = Probe(fail_actions_for="r2")

    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("down")
        await settle(pilot)
        assert bar(screen) == ""
        assert status(screen) == "! cannot work out the actions"
        await pilot.press("c")  # nothing is offered, so nothing runs
        await settle(pilot)
        assert probe.ran == []

    drive(steps, probe)


# --- running an action -------------------------------------------------------------------


def test_a_pressed_action_key_runs_the_action_and_the_rows_reload() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        loads, asked = probe.loads, len(probe.asked)
        await pilot.press("c")
        await settle(pilot)
        assert probe.ran == ["Close:r1"]
        assert probe.loads == loads + 1  # the rows were read again
        assert len(probe.asked) == asked + 1  # and the bar asked again for the same row
        await pilot.press("down", "ctrl+e")
        await settle(pilot)
        assert probe.ran == ["Close:r1", "Escalate:r2"]

    drive(steps)


def test_a_key_that_is_not_offered_does_nothing() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("x", "e")
        await settle(pilot)
        assert probe.ran == [] and probe.loads == 1

    drive(steps)


def test_action_key_ignored_in_an_input() -> None:
    probe = Probe()
    probe.actions["r1"] = (("a", "Answer"), ("f6", "Panels"))  # f6 is not text: Input lets it pass

    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("slash")
        assert isinstance(screen.focused, Input)
        await pilot.press("a", "f6")
        await settle(pilot)
        assert probe.ran == []
        assert screen.query_one("#log-filter", Input).value == "a"
        await pilot.press("enter")  # leave the box for the list
        await settle(pilot)
        assert not isinstance(screen.focused, Input)
        await pilot.press("f6")
        await settle(pilot)
        assert probe.ran == ["Panels:r1"]  # the same key runs once the list has the focus

    drive(steps, probe)


def test_refusal_goes_to_the_status_line() -> None:
    probe = Probe(refuse=True)

    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        loads = probe.loads
        await pilot.press("c")
        await settle(pilot)
        assert status(screen) == "! Only the author may close this."
        assert probe.loads == loads  # nothing changed, so nothing is read again
        assert isinstance(pilot.app.screen, Host)
        probe.refuse = False
        await pilot.press("c")
        await settle(pilot)
        assert status(screen) == "3 of 3 RFIs"  # the summary is back after a good run

    drive(steps, probe)


def test_attempt_serves_a_form_callback_the_same_way() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        def refused() -> None:
            raise ServiceError("Not allowed in this state.")

        assert screen.attempt(refused) is False
        assert status(screen) == "! Not allowed in this state."
        assert screen.attempt(lambda: None) is True
        await settle(pilot)  # the reload it started finishes before the screen closes

    drive(steps)


def test_colliding_keys_are_refused() -> None:
    def noop() -> None:
        return None

    twice = [LogAction("a", "Answer", noop), LogAction("a", "Amend", noop)]
    reserved = frozenset({"escape", "enter", "slash", "f5"})
    with pytest.raises(ValueError, match="offered twice"):
        check_action_keys(twice, reserved)
    for key in reserved:
        with pytest.raises(ValueError, match="reserved"):
            check_action_keys([LogAction(key, "Bad", noop)], reserved)
    check_action_keys([LogAction("a", "Answer", noop), LogAction("ctrl+e", "Esc.", noop)], reserved)
    assert [a.key for a in usable_actions(twice, reserved)] == ["a"]
    assert usable_actions([LogAction("f5", "Bad", noop)], reserved) == []


def test_colliding_keys_from_the_host_stop_a_test_run() -> None:
    probe = Probe()
    probe.actions["r1"] = (("a", "Answer"), ("a", "Amend"))

    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        raise AssertionError("the screen should not survive two actions on one key")

    with pytest.raises(WorkerFailed) as raised:
        drive(steps, probe)
    assert isinstance(raised.value.error, ValueError)
    assert "offered twice" in str(raised.value.error)


def test_a_host_binding_is_a_reserved_key() -> None:
    class Bound(Host):
        BINDINGS = [*Host.BINDINGS, ("r", "reload", "Reload")]

    probe = Probe()
    probe.actions["r1"] = (("r", "Reopen"),)
    app = HostApp(Bound(probe))

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)

    with pytest.raises(WorkerFailed) as raised:
        run_pilot(app, go)
    assert isinstance(raised.value.error, ValueError)
    assert "reserved" in str(raised.value.error)


# --- opening, filtering, closing ---------------------------------------------------------


def test_enter_opens_the_highlighted_row() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("down", "enter")
        await settle(pilot)
        assert probe.opened == ["r2"]

    drive(steps)


def test_the_filter_narrows_the_rows_and_escape_clears_it_before_closing() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("slash")
        await pilot.press(*"fire")
        await settle(pilot)
        assert [r.key for r in screen.shown] == ["r3"]
        assert crumb(screen).endswith("Fire damper access")
        assert bar(screen) == "[Enter] Open record"
        assert status(screen) == "1 of 3 RFIs"
        await pilot.press("escape")
        await settle(pilot)
        assert screen.query_one("#log-filter", Input).value == ""
        assert len(screen.shown) == 3
        assert isinstance(pilot.app.screen, Host)  # the first Esc only cleared the box
        await pilot.press("escape")
        await settle(pilot)
        assert not isinstance(pilot.app.screen, Host)

    drive(steps)


def test_a_filter_that_matches_nothing_clears_the_breadcrumb_record() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("slash")
        await pilot.press(*"zzz")
        await settle(pilot)
        assert crumb(screen) == "P123 › RFI Log" and bar(screen) == ""

    drive(steps)


def test_f5_reads_again_and_keeps_the_cursor_on_its_row() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("down", "down")
        await settle(pilot)
        probe.items = [Item("r0", "P123-RFI-0000", "New first row", "Open"), *ITEMS]
        await pilot.press("f5")
        await settle(pilot)
        assert probe.loads == 2
        assert screen.query_one("#log-table", DataTable).cursor_row == 3
        assert crumb(screen).endswith("Fire damper access")
        assert bar(screen) == "[Enter] Open record"

    drive(steps)


def test_a_failed_read_is_shown_and_the_rows_stay() -> None:
    class Failing(Host):
        def load_rows(self) -> Sequence[Item]:
            if self.probe.loads:
                self.probe.loads += 1
                raise ServiceError("server said no")
            return super().load_rows()

    probe = Probe()
    host = Failing(probe)
    app = HostApp(host)

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await pilot.press("f5")
        await settle(pilot)
        assert status(host) == "! server said no"
        assert len(host.shown) == 3

    run_pilot(app, go)


def test_the_technical_toggle_rebuilds_the_cells_and_keeps_the_row() -> None:
    async def steps(pilot: Pilot[Any], screen: Host, probe: Probe) -> None:
        await pilot.press("down")
        await settle(pilot)
        assert "ANSWERED" not in screen_text(pilot.app)
        mode = DisplayMode()
        mode.technical = True
        pilot.app.display_mode = mode  # type: ignore[attr-defined]
        screen.refresh_for_display_mode()
        await settle(pilot)
        assert "ANSWERED" in screen_text(pilot.app)
        assert screen.query_one("#log-table", DataTable).cursor_row == 1

    drive(steps)


# --- snapshots ---------------------------------------------------------------------------


def test_the_log_screen_snapshot_80x24(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await pilot.press("down")
        await settle(pilot)

    assert snap_compare(HostApp(Host(Probe())), terminal_size=(80, 24), run_before=run_before)


def test_the_log_screen_snapshot_170x30(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await pilot.press("down")
        await settle(pilot)

    assert snap_compare(HostApp(Host(Probe())), terminal_size=(170, 30), run_before=run_before)


def test_list_navigation_keys_are_reserved() -> None:
    from tl_tui.widgets.log_screen import RESERVED_KEYS

    assert {"up", "down", "pageup", "pagedown", "home", "end", "space", "tab"} <= RESERVED_KEYS
