"""Navigation tree and context panel (P0-I2-T12b). Provided by the supervisor; do not edit."""

from __future__ import annotations

from typing import Any

from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from tl_tui.messages import NavSelected
from tl_tui.widgets.context_panel import ContextPanel, context_text, flatten_psets
from tl_tui.widgets.nav_tree import NavTree

RECORD: dict[str, Any] = {
    "id": "R1",
    "key": "FV-1001",
    "type": "core.Record",
    "title": "T",
    "status": "Design",
    "version": 3,
    "conformance": "warning",
    "effective_schema_hash": "a91f" + "0" * 56 + "3c",
    "psets": {
        "valve_data": {"size_in": 6.0, "x": {"fat_witness_by": "@p"}},
        "prj": {"shutdown_tie_in": {"window": "SD-1"}},
    },
}


def test_flatten_psets_walks_nested_dicts_in_sorted_dotted_order() -> None:
    assert flatten_psets(RECORD["psets"]) == [
        ("prj.shutdown_tie_in.window", "SD-1"),
        ("valve_data.size_in", 6.0),
        ("valve_data.x.fat_witness_by", "@p"),
    ]
    assert flatten_psets({}) == []
    assert flatten_psets({"a": {}, "b": [1, 2]}) == [("b", [1, 2])]


def test_context_text_for_a_record() -> None:
    assert context_text(RECORD) == "\n".join(
        [
            "FV-1001  v3",
            "T",
            "Design · core.Record",
            "! warning",
            "── Psets ──",
            "prj.shutdown_tie_in.window  SD-1",
            "valve_data.size_in  6",
            "valve_data.x.fat_witness_by  @p",
            "── Schema ──",
            "#a91f…3c",
        ]
    )


def test_context_text_for_sparse_and_missing_records() -> None:
    sparse = {**RECORD, "status": None, "psets": {}, "effective_schema_hash": None}
    lines = context_text(sparse).splitlines()
    assert lines[2] == "— · core.Record"
    assert lines[4:] == ["── Psets ──", "(none)", "── Schema ──", "—"]
    assert context_text(None) == "No record under the cursor"


class Host(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield NavTree(company="ACME", scope="project:P123", id="nav")
        yield ContextPanel(id="context")

    def on_nav_selected(self, message: NavSelected) -> None:
        self.seen.append(message)


def test_nav_tree_shows_company_project_and_views() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "ACME" in text and "P123" in text and "project:P123" not in text
        assert "Records" in text and "★ Saved views (none yet)" in text

    run_pilot(app, scenario, size=(60, 14))


def test_choosing_records_posts_nav_selected_and_other_entries_do_not() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tree = app.query_one(NavTree)
        tree.focus()
        await pilot.press("down", "down", "enter")  # company, project, Records
        await pilot.pause()
        assert [m.view_id for m in app.seen if isinstance(m, NavSelected)] == ["records"]
        await pilot.press("down", "enter")  # Saved views
        await pilot.pause()
        assert len(app.seen) == 1

    run_pilot(app, scenario, size=(60, 14))


def test_context_panel_renders_and_updates_the_record_literally() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        panel = app.query_one(ContextPanel)
        assert "No record under the cursor" in screen_text(app)
        panel.show_record({**RECORD, "title": "[bold]Valve[/bold]"})
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1001  v3" in text and "[bold]Valve[/bold]" in text
        assert "valve_data.size_in  6" in text
        assert panel.record is not None and panel.record["key"] == "FV-1001"
        assert panel.text == context_text(panel.record)
        panel.show_record(None)
        await pilot.pause()
        assert panel.record is None and "No record under the cursor" in screen_text(app)

    run_pilot(app, scenario, size=(60, 24))
