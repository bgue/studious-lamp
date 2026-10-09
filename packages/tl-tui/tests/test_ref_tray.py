"""Reference tray screen: rows, commands, the modal, and the R and F4 keys (P0-I3-T13b)."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Select
from tl_core.services.links import AddLink
from tl_tui.app import TlApp
from tl_tui.tray import ReferenceTray, TrayItem
from tl_tui.widgets.footer import TlFooter
from tl_tui.widgets.record_view import RecordView
from tl_tui.widgets.ref_tray import (
    ReferenceTrayScreen,
    build_commands,
    target_text,
    title_text,
    tray_line,
)


def item(n: int, type_: str = "core.Record") -> TrayItem:
    return TrayItem(record_id=f"id{n}", key=f"K-{n}", type=type_, title=f"title {n}")


# --- pure functions -----------------------------------------------------------------------------


def test_a_tray_line_has_cursor_tick_key_title_and_type_on_the_right() -> None:
    line = tray_line(item(1), checked=True, highlighted=True, width=40)
    assert line == f"{'▶ [x] K-1  title 1':<29}core.Record"
    assert len(line) == 40
    plain = tray_line(item(1), checked=False, highlighted=False, width=40)
    assert plain.startswith("  [ ] K-1  title 1")


def test_a_long_title_is_cut_and_a_missing_type_shows_a_dash() -> None:
    long = TrayItem("i", "K-1", "core.Record", "A very long title that cannot fit here")
    line = tray_line(long, False, False, width=30)
    assert len(line) == 30 and line.endswith("… core.Record")
    assert tray_line(TrayItem("i", "K-1", "", "t"), False, False, 30).endswith("—")


def test_title_and_target_text() -> None:
    tray = ReferenceTray()
    tray.add(item(1))
    tray.add(item(2))
    assert title_text(tray) == "Reference tray (2)"
    assert target_text({"id": "x", "key": "FV-1001"}, 2) == "Link 2 ticked to FV-1001 as:"
    assert target_text({"id": "x", "key": None}, 0) == "Link 0 ticked to x as:"
    assert target_text(None, 2) == "Open a record to link the ticked ones to it"


def test_build_commands_go_from_the_target_to_each_item_and_skip_the_target() -> None:
    commands = build_commands(
        [item(1), item(2), item(3)],
        "id2",
        relation="requires",
        pin="C",
        scope=SCOPE,
        actor="user:t",
    )
    assert [(c.from_id, c.to_id) for c in commands] == [("id2", "id1"), ("id2", "id3")]
    first = commands[0]
    assert isinstance(first, AddLink)
    assert (first.relation, first.pin, first.note) == ("requires", "C", None)
    assert (first.actor, first.source, first.scope, first.link_source) == (
        "user:t",
        "tui",
        SCOPE,
        "tray",
    )


# --- the modal ----------------------------------------------------------------------------------


class Host(App[None]):
    def __init__(self, client: FakeClient, tray: ReferenceTray, target_key: str | None) -> None:
        super().__init__()
        self.client = client
        self.tray = tray
        self.target_key = target_key
        self.results: list[int | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        target = self.client.get_record(SCOPE, self.target_key) if self.target_key else None
        screen = ReferenceTrayScreen(self.client, SCOPE, self.tray, target, actor="user:t")
        self.push_screen(screen, self.results.append)


def _tray(client: FakeClient, *keys: str) -> ReferenceTray:
    tray = ReferenceTray()
    for key in keys:
        tray.add(TrayItem.from_record(client.get_record(SCOPE, key) or {}))
    return tray


def test_it_lists_the_tray_with_ticks_and_the_target() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, _tray(client, "FV-1002", "FV-1003"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Reference tray (2)" in text
        assert "[x] FV-1002" in text and "[x] FV-1003" in text
        assert "Link 2 ticked to FV-1001 as:" in text

    run_pilot(app, scenario, size=(110, 40))


def test_space_ticks_and_unticks_the_highlighted_record() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, _tray(client, "FV-1002", "FV-1003"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert "[ ] FV-1002" in screen_text(app) and "Link 1 ticked" in screen_text(app)
        assert [i.key for i in app.tray.checked_items()] == ["FV-1003"]
        await pilot.press("space")
        await pilot.pause()
        assert "[x] FV-1002" in screen_text(app)

    run_pilot(app, scenario, size=(110, 40))


def test_delete_removes_and_c_clears() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, _tray(client, "FV-1002", "FV-1003"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("delete")
        await pilot.pause()
        assert [i.key for i in app.tray.items] == ["FV-1003"]
        assert "Reference tray (1)" in screen_text(app)
        await pilot.press("c")
        await pilot.pause()
        assert len(app.tray) == 0
        assert "The tray is empty" in screen_text(app)

    run_pilot(app, scenario, size=(110, 40))


def test_enter_links_the_ticked_records_to_the_target_and_empties_them_from_the_tray() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, _tray(client, "FV-1002", "FV-1003"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.screen.query_one("#tray-relation", Select).value = "requires"
        app.screen.query_one("#tray-pin", Input).value = "B"
        await pilot.pause()
        await pilot.press("space")  # untick FV-1002
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [1]
        first = client._records_by_key("FV-1001")  # pyright: ignore[reportPrivateUsage]
        (view,) = client.links_of(first["id"])
        assert (view.other_key, view.relation, view.pin, view.source) == (
            "FV-1003",
            "requires",
            "B",
            "tray",
        )
        assert [i.key for i in app.tray.items] == ["FV-1002"]  # the unticked one stays

    run_pilot(app, scenario, size=(110, 40))


def test_without_a_target_it_asks_for_one_and_without_ticks_it_asks_for_a_tick() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, _tray(client, "FV-1002"), None)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "Open a record to link the ticked ones to it" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert "Open a record first" in screen_text(app) and app.results == []

    run_pilot(app, scenario, size=(110, 40))

    client2 = FakeClient.with_valve_example()
    app2 = Host(client2, _tray(client2, "FV-1002"), "FV-1001")

    async def scenario2(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("space", "enter")
        await pilot.pause()
        assert "Tick at least one record" in screen_text(app2) and app2.results == []

    run_pilot(app2, scenario2, size=(110, 40))


def test_a_refused_link_stays_open_and_says_why() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    app = Host(client, _tray(client, "FV-1002"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []
        assert "FV-1002: " in screen_text(app) and "already exists" in screen_text(app)
        assert len(app.tray) == 1

    run_pilot(app, scenario, size=(110, 40))


def test_a_partly_refused_batch_stays_open_with_the_refused_records_ticked() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1003")
    app = Host(client, _tray(client, "FV-1002", "FV-1003"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        text = screen_text(app)
        assert app.results == []  # still open
        assert "FV-1003: " in text and "already exists" in text
        assert "Reference tray (1)" in text and "[x] FV-1003" in text
        assert [i.key for i in app.tray.checked_items()] == ["FV-1003"]
        source = client.get_record(SCOPE, "FV-1001")
        assert source is not None and len(client.links_of(source["id"])) == 2
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [1]  # closing reports the link that was made

    run_pilot(app, scenario, size=(110, 40))


def test_escape_closes_with_none() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, _tray(client, "FV-1002"), "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None]

    run_pilot(app, scenario, size=(110, 40))


# --- the R and F4 keys of the app -----------------------------------------------------------------


def test_capital_r_adds_the_cursor_row_selection_or_open_record_to_the_tray() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        assert [i.key for i in app.tray.items] == ["FV-1001"]
        assert "Added FV-1001 to the tray (1)" in app.query_one(TlFooter).status
        await pilot.press("R")
        await pilot.pause()
        assert "Already in the tray (1)" in app.query_one(TlFooter).status
        await pilot.press("space", "down", "space", "R")  # a selection of two
        await pilot.pause()
        assert [i.key for i in app.tray.items] == ["FV-1001", "FV-1002"]

    run_pilot(app, scenario, size=(120, 40))


def test_f4_opens_the_tray_and_linking_refreshes_the_open_record() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "R")  # FV-1002 into the tray
        await pilot.pause()
        await pilot.press("up", "enter")  # open FV-1001
        await pilot.pause()
        await pilot.press("f4")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ReferenceTrayScreen)
        assert screen.target is not None and screen.target["key"] == "FV-1001"
        await pilot.press("f4")  # no second tray on top
        await pilot.pause()
        assert len(app.screen_stack) == 2
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, ReferenceTrayScreen)
        assert "Linked 1 from the tray" in app.query_one(TlFooter).status
        view = app.query_one(RecordView)
        assert view.record is not None
        assert [v.other_key for v in client.links_of(view.record["id"])] == ["FV-1002"]
        assert "1 links" in screen_text(app)

    run_pilot(app, scenario, size=(140, 40))
