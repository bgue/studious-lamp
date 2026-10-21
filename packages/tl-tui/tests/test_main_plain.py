"""Main screen in plain mode: feed pane, header and reference tray show no ids (P1-UX-T13).

Plain is the default (``DisplayMode.technical`` is False); each test that needs technical text sets
the app's ``display_mode`` and redraws. The pure functions default to technical (raw) output.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from rich.cells import cell_len
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_core.services.feed_queries import FeedSuggestion
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.tray import ReferenceTray, TrayItem
from tl_tui.widgets.feed_pane import FeedPane, author_text
from tl_tui.widgets.header import TlHeader, header_line
from tl_tui.widgets.ref_tray import ReferenceTrayScreen, tray_line


class Host(App[None]):
    def __init__(self, client: FakeClient, **kw: Any) -> None:
        super().__init__()
        self.client = client
        self.kw = kw
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield FeedPane(self.client, SCOPE, actor="user:me", id="feed", **self.kw)

    def on_mount(self) -> None:
        self.query_one(FeedPane).focus()

    def pane(self) -> FeedPane:
        return self.query_one(FeedPane)


def seeded() -> FakeClient:
    client = FakeClient.with_valve_example()
    client.seed_card("jsmith created 14 records", record_ids=())
    client.seed_post("Spool arrived #FV-1001 #hold @party:fab-a", actor="user:mlee")
    client.seed_post("Classified 3 letters #fyi", actor="agent:triage")
    client.seed_post("Imported 4 rows", actor="svc:importer")
    return client


# --- pure text --------------------------------------------------------------------------------


def test_author_text_plain_and_technical() -> None:
    labels = Labels(services={"svc:importer": "Importer"})
    assert author_text("user:mlee", technical=False) == "mlee"
    assert author_text("agent:triage", technical=False) == "triage ⚙"
    assert author_text("agent:triage") == "agent:triage ⚙"
    assert author_text("svc:importer", labels, technical=False) == "Importer"
    assert author_text("svc:importer", technical=False) == "a service"
    assert author_text("svc:importer") == "svc:importer"
    assert author_text("other:x", technical=False) == "other:x"
    assert author_text("other:x") == "other:x"


# --- the feed pane ----------------------------------------------------------------------------


def test_feed_pane_plain_shows_names_and_no_ids() -> None:
    client = seeded()
    valve = client.get_record(SCOPE, "FV-1001")
    assert valve is not None
    record_app = Host(client, record_id=valve["id"])

    async def record_scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(record_app)
        assert "Feed · P123 · record this record" in text
        assert valve["id"] not in text
        assert find_technical(text) == []

    run_pilot(record_app, record_scenario)

    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        pane = app.pane()
        mlee = next(i for i in pane.items if i.actor == "user:mlee")
        # A proposal on a record that has no key: plain names it as a record, not by its id.
        pane.suggestions = {
            mlee.id: [FeedSuggestion("P1", "constraint", "r-hidden-1", None, "Create one?")]
        }
        pane.refresh_for_display_mode()
        await pilot.pause()
        text = screen_text(app)
        assert "triage ⚙" in text and "agent:triage" not in text
        assert "Imported 4 rows" in text and "a service" in text
        assert "proposal: constraint on a record [a]" in text
        assert "r-hidden-1" not in text
        assert find_technical(text) == []

    run_pilot(app, scenario)


def test_feed_pane_technical_toggle_restores_the_actor_ids_and_back() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "agent:triage ⚙" not in screen_text(app)
        app.display_mode.technical = True
        app.pane().refresh_for_display_mode()
        await pilot.pause()
        assert "agent:triage ⚙" in screen_text(app)
        app.display_mode.technical = False
        app.pane().refresh_for_display_mode()
        await pilot.pause()
        assert "agent:triage ⚙" not in screen_text(app)
        assert "triage ⚙" in screen_text(app)

    run_pilot(app, scenario)


# --- the header -------------------------------------------------------------------------------


def test_header_line_plain_and_technical_for_a_service() -> None:
    plain = header_line(
        "ACME", "project:P123", "Records", "embedded", "svc:sync", 60, technical=False
    )
    assert cell_len(plain) == 60
    assert plain.endswith("● embedded · a service ")
    technical = header_line("ACME", "project:P123", "Records", "embedded", "svc:sync", 60)
    assert technical.endswith("● embedded · svc:sync ")
    narrow = header_line(
        "ACME", "project:P123", "Records", "embedded", "svc:sync", 20, technical=False
    )
    assert cell_len(narrow) == 20 and narrow == " ACME ▸ P123 ▸ Reco…"


class HeaderHost(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield TlHeader(company="ACME", scope="project:P123", actor="svc:sync", id="header")


def test_header_widget_follows_the_display_mode() -> None:
    app = HeaderHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "a service" in screen_text(app).splitlines()[0]
        assert "svc:sync" not in screen_text(app).splitlines()[0]
        app.display_mode.technical = True
        app.query_one(TlHeader).refresh_for_display_mode()
        await pilot.pause()
        assert "svc:sync" in screen_text(app).splitlines()[0]

    run_pilot(app, scenario, size=(80, 10))


# --- the reference tray -----------------------------------------------------------------------


def test_tray_line_plain_uses_the_type_label_and_technical_the_raw_type() -> None:
    labels = Labels(type_titles={"engineering.Tag": "Control valve"})
    tag = TrayItem(record_id="id1", key="FV-1001", type="engineering.Tag", title="Valve")
    plain = tray_line(
        tag, checked=False, highlighted=False, width=50, labels=labels, technical=False
    )
    assert plain.endswith("Control valve") and "engineering.Tag" not in plain
    technical = tray_line(tag, checked=False, highlighted=False, width=50, labels=labels)
    assert technical.endswith("engineering.Tag")
    assert len(plain) == 50 and len(technical) == 50


class TrayHost(App[None]):
    def __init__(self, client: FakeClient, tray: ReferenceTray) -> None:
        super().__init__()
        self.client = client
        self.tray = tray
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        screen = ReferenceTrayScreen(self.client, SCOPE, self.tray, None, actor="user:t")
        self.push_screen(screen)


def test_ref_tray_screen_plain_hides_the_raw_type_and_refresh_keeps_the_row() -> None:
    client = FakeClient.with_valve_example()
    tray = ReferenceTray()
    tray.add(TrayItem.from_record(client.get_record(SCOPE, "FV-1002") or {}))
    raw_type = tray.items[0].type
    assert raw_type
    app = TrayHost(client, tray)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1002" in text and find_technical(text) == []
        assert raw_type not in text
        app.display_mode.technical = True
        screen = app.screen
        assert isinstance(screen, ReferenceTrayScreen)
        screen.refresh_for_display_mode()
        await pilot.pause()
        assert raw_type in screen_text(app)

    run_pilot(app, scenario, size=(110, 40))
