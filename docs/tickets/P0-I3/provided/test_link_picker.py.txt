"""Link picker: rows, commands, the modal, and the `l` key of the app (P0-I3-T12; sketch 4)."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Select
from tl_core.services.link_queries import LinkTarget
from tl_core.services.links import AddLink
from tl_tui.app import TlApp
from tl_tui.widgets.footer import TlFooter
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.link_picker import (
    LinkPicker,
    LinkPickerResult,
    PickerSource,
    build_commands,
    preview_text,
    result_line,
    title_text,
)
from tl_tui.widgets.new_record_form import NewRecordForm


def target(
    key: str | None = "FV-1001", title: str = "Control valve", status: str | None = "Design"
) -> LinkTarget:
    return LinkTarget(
        id=f"id-{key}",
        key=key,
        type="core.Record",
        title=title,
        status=status,
        scope=SCOPE,
        link_total=3,
    )


def source(key: str = "FV-9") -> PickerSource:
    return PickerSource(id=f"src-{key}", key=key, type="core.Record", title=f"title {key}")


# --- pure functions -----------------------------------------------------------------------------


def test_picker_source_from_a_record_envelope() -> None:
    found = PickerSource.from_record(
        {"id": "i1", "key": "FV-1", "type": "core.Record", "title": "T", "status": "Design"}
    )
    assert found == PickerSource("i1", "FV-1", "core.Record", "T")
    keyless = PickerSource.from_record({"id": "i2", "key": None, "type": None, "title": None})
    assert (keyless.key, keyless.type, keyless.title) == ("i2", "", "")


def test_the_title_names_one_source_or_counts_several() -> None:
    assert title_text([source("FV-9")]) == "Link FV-9 →"
    assert title_text([source("A"), source("B"), source("C")]) == "Link 3 selected records →"


def test_a_result_line_has_cursor_tick_key_title_and_status_on_the_right() -> None:
    line = result_line(target(), selected=False, highlighted=True, width=40)
    assert line == f"{'▶ [ ] FV-1001  Control valve':<34}Design"
    assert len(line) == 40


def test_a_ticked_row_shows_x_and_an_unhighlighted_row_has_no_cursor() -> None:
    line = result_line(target(), selected=True, highlighted=False, width=40)
    assert line.startswith("  [x] FV-1001  Control valve")
    assert line.endswith("Design")


def test_a_long_title_is_cut_with_an_ellipsis_and_keeps_the_status() -> None:
    line = result_line(target(title="A very long title that cannot fit"), False, False, width=30)
    assert len(line) == 30
    assert line.endswith("… Design")
    assert line.startswith("  [ ] FV-1001  A very")


def test_a_missing_key_or_status_shows_a_dash() -> None:
    line = result_line(target(key=None, status=None), False, False, width=30)
    assert "—  Control valve" in line
    assert line.endswith("—")


def test_the_preview_line_and_its_empty_hint() -> None:
    assert preview_text(target()) == "FV-1001 · Control valve · Design · 3 linked"
    assert preview_text(target(status=None)) == "FV-1001 · Control valve · — · 3 linked"
    assert preview_text(None) == "No record highlighted"


def test_build_commands_pairs_every_source_with_every_target() -> None:
    commands = build_commands(
        [source("A"), source("B")],
        [target("T1"), target("T2")],
        relation="requires",
        pin="C",
        note="why",
        scope=SCOPE,
        actor="user:t",
    )
    assert [(c.from_id, c.to_id) for c in commands] == [
        ("src-A", "id-T1"),
        ("src-A", "id-T2"),
        ("src-B", "id-T1"),
        ("src-B", "id-T2"),
    ]
    first = commands[0]
    assert isinstance(first, AddLink)
    assert (first.relation, first.pin, first.note) == ("requires", "C", "why")
    assert (first.actor, first.source, first.scope, first.link_source) == (
        "user:t",
        "tui",
        SCOPE,
        "manual",
    )


def test_build_commands_never_pairs_a_record_with_itself() -> None:
    same = LinkTarget(
        id="src-A", key="A", type="core.Record", title="t", status=None, scope=SCOPE, link_total=0
    )
    commands = build_commands(
        [source("A")],
        [same, target("T1")],
        relation="references",
        pin=None,
        note=None,
        scope=SCOPE,
        actor="u",
    )
    assert [c.to_id for c in commands] == ["id-T1"]


# --- the modal ----------------------------------------------------------------------------------


class Host(App[None]):
    def __init__(self, client: FakeClient, sources: list[PickerSource]) -> None:
        super().__init__()
        self.client = client
        self.sources = sources
        self.results: list[LinkPickerResult | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        picker = LinkPicker(self.client, SCOPE, self.sources, actor="user:t")
        self.push_screen(picker, self.results.append)


def _src(client: FakeClient, key: str = "FV-1001") -> PickerSource:
    return PickerSource.from_record(client._records_by_key(key))  # pyright: ignore[reportPrivateUsage]


def _search(app: Host, text: str) -> None:
    app.screen.query_one("#picker-search", Input).value = text


def test_it_lists_the_other_records_and_previews_the_highlighted_one() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, [_src(client)])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Link FV-1001 →" in text
        assert "FV-1002" in text and "FV-1003" in text
        assert "[ ] FV-1001" not in text  # the source is not offered
        assert "FV-1002 · Manual valve MV on 4in vent · Design · 0 linked" in text
        select = app.screen.query_one("#picker-relation", Select)
        assert select.value == "references"

    run_pilot(app, scenario, size=(110, 40))


def test_searching_narrows_the_list() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, [_src(client)])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _search(app, "check")
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1003" in text and "FV-1002" not in text

    run_pilot(app, scenario, size=(110, 40))


def test_enter_links_the_highlighted_record_and_dismisses_with_the_count() -> None:
    client = FakeClient.with_valve_example()
    source_record = _src(client)
    app = Host(client, [source_record])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [LinkPickerResult(created=1, messages=[])]
        (view,) = client.links_of(source_record.id)
        assert (view.direction, view.relation, view.other_key, view.status) == (
            "out",
            "references",
            "FV-1002",
            "active",
        )
        (cmd,) = [c for c in client.link_commands if isinstance(c, AddLink)]
        assert (cmd.actor, cmd.source, cmd.link_source) == ("user:t", "tui", "manual")
        assert cmd.pin is None and cmd.note is None

    run_pilot(app, scenario, size=(110, 40))


def test_ctrl_t_ticks_records_and_enter_links_all_ticked() -> None:
    client = FakeClient.with_valve_example()
    source_record = _src(client)
    app = Host(client, [source_record])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+t", "down", "ctrl+t")
        await pilot.pause()
        text = screen_text(app)
        assert "[x] FV-1002" in text and "[x] FV-1003" in text
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [LinkPickerResult(created=2, messages=[])]
        assert sorted(v.other_key or "" for v in client.links_of(source_record.id)) == [
            "FV-1002",
            "FV-1003",
        ]

    run_pilot(app, scenario, size=(110, 40))


def test_ctrl_t_again_unticks() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, [_src(client)])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert "[x] FV-1002" in screen_text(app)
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert "[x]" not in screen_text(app)

    run_pilot(app, scenario, size=(110, 40))


def test_relation_pin_and_note_are_sent() -> None:
    client = FakeClient.with_valve_example()
    source_record = _src(client)
    app = Host(client, [source_record])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.screen.query_one("#picker-relation", Select).value = "requires"
        app.screen.query_one("#picker-pin", Input).value = "C"
        app.screen.query_one("#picker-note", Input).value = "see photos"
        await pilot.pause()
        await pilot.press("down")  # moving the highlight must not undo a chosen relation
        await pilot.pause()
        assert app.screen.query_one("#picker-relation", Select).value == "requires"
        await pilot.press("up")
        _search(app, "")
        await pilot.press("enter")
        await pilot.pause()
        (view,) = client.links_of(source_record.id)
        assert (view.relation, view.pin, view.note) == ("requires", "C", "see photos")

    run_pilot(app, scenario, size=(110, 40))


def test_several_sources_are_each_linked_to_the_target() -> None:
    client = FakeClient.with_valve_example()
    a, b = _src(client, "FV-1001"), _src(client, "FV-1002")
    app = Host(client, [a, b])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "Link 2 selected records →" in screen_text(app)
        _search(app, "check")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [LinkPickerResult(created=2, messages=[])]
        assert [v.other_key for v in client.links_of(a.id)] == ["FV-1003"]
        assert [v.other_key for v in client.links_of(b.id)] == ["FV-1003"]

    run_pilot(app, scenario, size=(110, 40))


def test_a_refused_link_keeps_the_picker_open_and_says_why() -> None:
    client = FakeClient.with_valve_example()
    source_record = _src(client)
    client.seed_link("FV-1001", "FV-1002")  # the highlighted record is already linked
    app = Host(client, [source_record])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []
        assert "FV-1001 → FV-1002" in screen_text(app)
        assert "already exists" in screen_text(app)
        await pilot.press("down", "enter")  # a different record works
        await pilot.pause()
        assert app.results == [LinkPickerResult(created=1, messages=[])]

    run_pilot(app, scenario, size=(110, 40))


def test_partial_success_dismisses_with_the_messages() -> None:
    client = FakeClient.with_valve_example()
    source_record = _src(client)
    client.seed_link("FV-1001", "FV-1002")
    app = Host(client, [source_record])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+t", "down", "ctrl+t", "enter")
        await pilot.pause()
        (result,) = app.results
        assert result is not None and result.created == 1
        assert len(result.messages) == 1 and result.messages[0].startswith("FV-1001 → FV-1002: ")

    run_pilot(app, scenario, size=(110, 40))


def test_enter_with_no_results_asks_for_a_record() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, [_src(client)])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _search(app, "zzzzzz")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []
        assert "Choose a record to link" in screen_text(app)

    run_pilot(app, scenario, size=(110, 40))


def test_escape_cancels() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, [_src(client)])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None]
        assert client.link_commands == []

    run_pilot(app, scenario, size=(110, 40))


def test_ctrl_n_creates_a_record_and_links_it() -> None:
    client = FakeClient.with_valve_example()
    source_record = _src(client)
    app = Host(client, [source_record])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+n")
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        form.query_one("#new_key Input", Input).value = "FV-7777"
        form.query_one("#new_title Input", Input).value = "Brand new"
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert app.results == [LinkPickerResult(created=1, messages=[])]
        (view,) = client.links_of(source_record.id)
        assert (view.other_key, view.other_title) == ("FV-7777", "Brand new")

    run_pilot(app, scenario, size=(110, 40))


def test_typing_l_in_the_search_box_types_a_letter() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, [_src(client)])

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("l", "w", "t")
        await pilot.pause()
        assert app.screen.query_one("#picker-search", Input).value == "lwt"

    run_pilot(app, scenario, size=(110, 40))


# --- the `l` key of the app -----------------------------------------------------------------------


def test_l_on_the_grid_links_the_cursor_row_and_reports_it() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, LinkPicker)
        await pilot.press("l")  # a second `l` is typed into the search box, not a second picker
        await pilot.pause()
        assert isinstance(app.screen, LinkPicker) and len(app.screen_stack) == 2
        app.screen.query_one("#picker-search", Input).value = "check"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, LinkPicker)
        assert "Linked 1" in app.query_one(TlFooter).status
        first = client._records_by_key("FV-1001")  # pyright: ignore[reportPrivateUsage]
        assert [v.other_key for v in client.links_of(first["id"])] == ["FV-1003"]

    run_pilot(app, scenario, size=(120, 40))


def test_l_links_every_selected_row() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one(RecordGrid)
        grid.focus()
        await pilot.press("space", "down", "space")
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, LinkPicker)
        assert [s.key for s in picker.sources] == ["FV-1001", "FV-1002"]

    run_pilot(app, scenario, size=(120, 40))


def test_l_in_the_record_view_links_the_open_record() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, LinkPicker)
        assert [s.key for s in picker.sources] == ["FV-1001"]

    run_pilot(app, scenario, size=(120, 40))


class TypedClient(FakeClient):
    """A fake whose default relation depends on the target type, as the real vocabulary can."""

    def default_relation(self, from_type: str, to_type: str) -> str:
        return "requires" if to_type == "other.Type" else "references"


def test_the_relation_follows_the_highlighted_record_until_the_user_changes_it() -> None:
    client = TypedClient.with_valve_example()
    client._records_by_key("FV-1003")["type"] = "other.Type"  # pyright: ignore[reportPrivateUsage]
    app = Host(client, [_src(client)])

    def relation() -> str:
        return str(app.screen.query_one("#picker-relation", Select).value)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert relation() == "references"  # FV-1002 is highlighted
        await pilot.press("down")  # FV-1003, of the other type
        await pilot.pause()
        await pilot.pause()
        assert relation() == "requires"
        await pilot.press("up")
        await pilot.pause()
        await pilot.pause()
        assert (
            relation() == "references"
        )  # still following: the picker's own changes are not the user's
        app.screen.query_one("#picker-relation", Select).value = "blocks"
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.pause()
        assert relation() == "blocks"  # the user chose: it stays fixed
        await pilot.press("up")
        await pilot.pause()
        await pilot.pause()
        assert relation() == "blocks"

    run_pilot(app, scenario, size=(110, 40))
