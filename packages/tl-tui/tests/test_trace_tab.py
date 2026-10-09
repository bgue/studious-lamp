"""Trace tab: labels, lines, depth and direction, following (P0-I3-T14; brief 7.5)."""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import TabbedContent, Tree
from tl_core.services.link_trace import TraceNode
from tl_tui.app import TlApp
from tl_tui.widgets.footer import TlFooter
from tl_tui.widgets.record_view import RecordView
from tl_tui.widgets.trace_tab import TraceTab, head_text, node_text, tree_lines


def node(**kw: Any) -> TraceNode:
    data: dict[str, Any] = {
        "record_id": "r1",
        "key": "FV-1001",
        "title": "Control valve",
        "type": "core.Record",
        "status": "Design",
        "voided": False,
        "depth": 0,
    }
    data.update(kw)
    return TraceNode(**data)


# --- pure functions -----------------------------------------------------------------------------


def test_the_root_label_is_key_and_title() -> None:
    assert node_text(node()) == "FV-1001  Control valve"
    assert node_text(node(key=None)) == "—  Control valve"


def test_a_child_label_starts_with_how_it_was_reached() -> None:
    child = node(depth=1, label="raised against", link_status="active")
    assert node_text(child) == "raised against: FV-1001  Control valve"


def test_stale_broken_voided_and_more_are_marked_in_text() -> None:
    assert node_text(node(depth=1, label="x", link_status="stale")).endswith("  ! stale")
    assert node_text(node(depth=1, label="x", link_status="broken")).endswith("  ✗ broken")
    assert node_text(node(voided=True)).endswith("  (voided)")
    assert node_text(node(more=3)).endswith("  +3 more")
    both = node(depth=1, label="x", link_status="stale", voided=True, more=2)
    assert node_text(both) == "x: FV-1001  Control valve  ! stale  (voided)  +2 more"


def test_tree_lines_indent_two_spaces_per_level() -> None:
    root = node(
        children=[
            node(record_id="b", key="B", title="Bee", depth=1, label="references"),
            node(
                record_id="c",
                key="C",
                title="Cee",
                depth=1,
                label="blocked by",
                children=[node(record_id="d", key="D", title="Dee", depth=2, label="requires")],
            ),
        ]
    )
    assert tree_lines(root) == [
        "FV-1001  Control valve",
        "  references: B  Bee",
        "  blocked by: C  Cee",
        "    requires: D  Dee",
    ]


def test_head_text() -> None:
    assert head_text(2, "both") == "Depth 2 · both directions"
    assert head_text(3, "out") == "Depth 3 · outbound"
    assert head_text(1, "in") == "Depth 1 · inbound"


# --- the tab inside the record view ------------------------------------------------------------


def _chain() -> FakeClient:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002", "raised_against")
    client.seed_link("FV-1002", "FV-1003", "requires")
    return client


def test_t_opens_the_trace_tab_of_the_open_record() -> None:
    client = _chain()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-trace"
        tab = app.query_one(TraceTab)
        assert tab.lines == [
            "FV-1001  Control valve FCV on 6in discharge",
            "  raised against: FV-1002  Manual valve MV on 4in vent",
            "    requires: FV-1003  Check valve CV on 2in drain",
        ]
        text = screen_text(app)
        assert "Depth 2 · both directions" in text
        assert "raised against: FV-1002" in text

    run_pilot(app, scenario, size=(140, 40))


def test_t_on_the_grid_asks_for_a_record() -> None:
    app = TlApp(_chain())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert "Open a record first" in app.query_one(TlFooter).status

    run_pilot(app, scenario, size=(140, 40))


def test_plus_and_minus_change_the_depth_within_limits() -> None:
    client = _chain()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        tab = app.query_one(TraceTab)
        tab.query_one(Tree).focus()
        await pilot.press("minus")
        await pilot.pause()
        assert tab.depth == 1 and len(tab.lines) == 2
        assert "  +1 more" in tab.lines[1]
        await pilot.press("minus")
        await pilot.pause()
        assert tab.depth == 1  # the lowest depth
        await pilot.press("plus", "plus")
        await pilot.pause()
        assert tab.depth == 3 and len(tab.lines) == 3
        for _ in range(10):
            await pilot.press("plus")
        await pilot.pause()
        assert tab.depth == 6  # the highest depth
        assert "Depth 6" in screen_text(app)

    run_pilot(app, scenario, size=(140, 40))


def test_o_cycles_the_direction() -> None:
    client = _chain()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "enter")  # FV-1002: one link each way
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        tab = app.query_one(TraceTab)
        tab.query_one(Tree).focus()
        assert len(tab.lines) == 3 and tab.direction == "both"
        await pilot.press("o")
        await pilot.pause()
        assert tab.direction == "out" and len(tab.lines) == 2
        assert "requires: FV-1003" in tab.lines[1]
        assert "outbound" in screen_text(app)
        await pilot.press("o")
        await pilot.pause()
        assert tab.direction == "in" and len(tab.lines) == 2
        assert "has raised: FV-1001" in tab.lines[1]
        await pilot.press("o")
        await pilot.pause()
        assert tab.direction == "both" and len(tab.lines) == 3

    run_pilot(app, scenario, size=(140, 40))


def test_enter_on_a_record_follows_it_and_the_root_does_nothing() -> None:
    client = _chain()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        app.query_one(TraceTab).query_one(Tree).focus()
        await pilot.press("enter")  # the root
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1001"
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1002"
        assert app.history.trail() == "FV-1001 › FV-1002"

    run_pilot(app, scenario, size=(140, 40))


def test_a_record_without_links_shows_only_itself() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert app.query_one(TraceTab).lines == ["FV-1001  Control valve FCV on 6in discharge"]

    run_pilot(app, scenario, size=(140, 40))
