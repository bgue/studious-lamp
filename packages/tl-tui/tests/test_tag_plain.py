"""The tag register in plain words: Enter opens the record, labels, technical mode (P1-UX-T02)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from textual.widgets import Input
from tl_mod_engineering.views import TagView
from tl_schema.forms import ConformanceIssue
from tl_tui.app import TlApp
from tl_tui.details import NOTE_LABEL, NOTE_TEXT, details_for
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.widgets.record_screen import RecordScreen
from tl_tui.widgets.tag_register import TagRegisterScreen

PROJECT = "P123"
LACKS = ConformanceIssue(
    path="psets.valve_data.body_material",
    level="nonconformant",
    rule="class_required",
    message="required by the class",
)


def world() -> FakeClient:
    """Two tags; each has a stored record under its view id, so Enter finds it."""
    client = FakeClient()
    feed = client.add_tag(
        PROJECT,
        "47-FV-1001",
        class_code="ControlValve",
        conformance="nonconformant",
        issues=[LACKS],
        title="Feed gas control",
    )
    client.add_stored_record(feed.id, feed.number, "engineering.Tag", feed.title)
    manual = client.add_tag(PROJECT, "47-HV-1003", class_code="ManualValve", conformance="ok")
    client.add_stored_record(manual.id, manual.number, "engineering.Tag", manual.title)
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, TagRegisterScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f8")
        await settle(pilot)
        assert isinstance(app.screen, TagRegisterScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go, size=(140, 40))


def numbers(screen: TagRegisterScreen) -> list[str]:
    return [v.number for v in screen.shown]


def test_enter_opens_the_record_screen_with_the_tag_details_and_escape_returns_to_the_same_row() -> (  # noqa: E501
    None
):  # noqa: E501
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert "Control valve" in text and "Valve data / Body material" in text
        assert "ControlValve" not in text and "psets." not in text
        await pilot.press("escape")
        await settle(pilot)
        assert isinstance(app.screen, TagRegisterScreen)
        current = screen.current()
        assert current is not None and current.number == "47-FV-1001"
        await pilot.press("down")
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, RecordScreen)
        assert "Manual valve" in screen_text(app)
        await pilot.press("escape")
        await settle(pilot)
        assert isinstance(app.screen, TagRegisterScreen)
        current = screen.current()
        assert current is not None and current.number == "47-HV-1003"

    scenario(world(), steps)


def test_enter_in_the_filter_box_does_not_open_a_record() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("slash")
        screen.query_one("#log-filter", Input).value = "47"
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, TagRegisterScreen)
        assert not any(isinstance(s, RecordScreen) for s in app.screen_stack)
        assert numbers(screen) == ["47-FV-1001", "47-HV-1003"]

    scenario(world(), steps)


def test_a_tag_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = world()
    hidden = client.add_tag(PROJECT, "47-PT-2001", class_code="Transmitter")
    # no stored record for the tag: the read of its record finds nothing, as for a hidden one

    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("down", "down")
        await settle(pilot)
        current = screen.current()
        assert current is not None and current.number == "47-PT-2001"
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert "No record" in text
        assert hidden.id not in text

    scenario(client, steps)


def test_plain_text_names_the_class_and_the_properties_in_words() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        text = screen_text(app)
        assert "Control valve" in text
        assert "Valve data / Body material" in text
        for raw in ("ControlValve", "psets.", "area="):
            assert raw not in text, raw
        assert find_technical(text) == []
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(app.screen, RecordScreen)
        record_text = screen_text(app)
        assert "Control valve" in record_text and "Valve data / Body material" in record_text
        assert find_technical(record_text) == []

    scenario(world(), steps)


def test_technical_mode_shows_the_raw_path_and_segments_and_back() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        assert "area=" not in screen_text(app)
        app.display_mode.technical = True
        screen.refresh_for_display_mode()
        await settle(pilot)
        text = screen_text(app)
        assert "psets.valve_data.body_material" in text
        assert "area=47 mnemonic=FV seq=1001" in text
        assert "ControlValve" in text
        app.display_mode.technical = False
        screen.refresh_for_display_mode()
        await settle(pilot)
        text = screen_text(app)
        assert "area=" not in text and "psets." not in text
        assert "Valve data / Body material" in text

    scenario(world(), steps)


class BrokenTagReads(FakeClient):
    """A client whose tag read fails: the Details tab must still open."""

    def get_tag(self, project: str, number: str) -> TagView:
        raise RuntimeError("the tag read failed")


def test_the_tag_renderer_rows_with_a_failing_read_fall_back_to_generic_rows_and_a_note() -> None:
    client = BrokenTagReads()
    feed = client.add_tag(
        PROJECT, "47-FV-1001", class_code="ControlValve", title="Feed gas control"
    )
    client.add_stored_record(feed.id, feed.number, "engineering.Tag", feed.title)
    record = client.get_record_by_id(feed.id)
    assert record is not None

    rows = details_for(client, PROJECT, record, Labels(), DisplayMode())

    assert [row.label for row in rows] == [
        "Type",
        "Title",
        "Status",
        "Created",
        "Updated",
        "Conformance",
        NOTE_LABEL,
    ]
    assert rows[1].value == "Feed gas control"
    assert rows[-1].value == NOTE_TEXT
