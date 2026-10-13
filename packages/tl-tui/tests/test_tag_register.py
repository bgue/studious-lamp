"""The tag register screen on the fake client, driven with a pilot (P1-I1-T09d)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from tl_schema.forms import ConformanceIssue
from tl_tui.app import TlApp
from tl_tui.widgets.tag_register import TagRegisterScreen

LACKS = ConformanceIssue(
    path="psets.valve_data", level="nonconformant", rule="class_required", message="required"
)


def world() -> FakeClient:
    client = FakeClient()
    client.add_tag("P123", "47-FV-1001", class_code="ControlValve", conformance="nonconformant",
                   issues=[LACKS], title="Feed gas control")  # fmt: skip
    client.add_tag("P123", "47-FV-1002", class_code="ControlValve", conformance="ok")
    client.add_tag("P123", "47-HV-1003", class_code="ManualValve", conformance="ok")
    client.add_tag("P123", "LEGACY-1", class_code=None, number_status="violation", violations=[
        {"segment": None, "level": "error", "message": "does not fit the pattern"}
    ])  # fmt: skip
    client.add_tag("P123", "47-FV-0999", class_code="ControlValve", status="Superseded")
    return client


def scenario(
    client: FakeClient, steps: Callable[[Pilot[None], TlApp, TagRegisterScreen], Awaitable[None]]
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f8")
        await pilot.pause()
        assert isinstance(app.screen, TagRegisterScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def numbers(screen: TagRegisterScreen) -> list[str]:
    return [v.number for v in screen.shown]


def status(screen: TagRegisterScreen) -> str:
    return str(screen.query_one("#tags-status", Static).render())


def test_f8_lists_the_tags_in_service_by_number_and_describes_the_first() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        text = screen_text(app)
        assert "Tags of P123" in text
        assert numbers(screen) == ["47-FV-1001", "47-FV-1002", "47-HV-1003", "LEGACY-1"]
        assert screen.query_one("#tags-table", DataTable).row_count == 4
        assert "BAD" in text and "nonconformant" in text
        assert "lacks:" in text and "psets.valve_data" in text  # the detail of the first tag
        assert "4 of 4 tags" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, TagRegisterScreen)

    scenario(world(), steps)


def test_moving_the_cursor_describes_the_tag_it_lands_on() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("down", "down", "down")
        await pilot.pause()
        assert screen.detail is not None and screen.detail.number == "LEGACY-1"
        text = screen_text(app)
        assert "number violation: -" in text and "! number: does not fit the pattern" in text

    scenario(world(), steps)


def test_c_walks_the_classes_v_shows_the_violations_and_a_shows_the_ended() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("c")
        await pilot.pause()
        assert screen.class_code == "ControlValve"
        assert numbers(screen) == ["47-FV-1001", "47-FV-1002"]
        assert "class ControlValve" in status(screen)
        await pilot.press("c", "c")
        await pilot.pause()
        assert screen.class_code is None and len(numbers(screen)) == 4
        await pilot.press("v")
        await pilot.pause()
        assert numbers(screen) == ["LEGACY-1"] and "violations only" in status(screen)
        await pilot.press("v", "a")
        await pilot.pause()
        assert "47-FV-0999" in numbers(screen) and "incl. ended" in status(screen)

    scenario(world(), steps)


def test_the_filter_matches_the_number_or_the_title_and_escape_clears_it() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("slash")
        screen.query_one("#tags-filter", Input).value = "feed"
        await pilot.pause()
        assert numbers(screen) == ["47-FV-1001"]
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, TagRegisterScreen) and len(numbers(screen)) == 4
        assert screen.query_one("#tags-filter", Input).value == ""

    scenario(world(), steps)


def test_typing_c_in_the_filter_is_text_not_a_command() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("slash", "c")
        await pilot.pause()
        assert screen.class_code is None

    scenario(world(), steps)


def test_f5_reads_again_and_keeps_the_highlighted_tag() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        await pilot.press("down")
        client.add_tag("P123", "10-PT-0001", class_code=None)
        await pilot.press("f5")
        await pilot.pause()
        assert numbers(screen)[0] == "10-PT-0001"
        current = screen.current()
        assert current is not None and current.number == "47-FV-1002"

    scenario(client, steps)


def test_a_company_scope_has_no_tag_register() -> None:
    app = TlApp(world(), scope="company", actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f8")
        await pilot.pause()
        assert not isinstance(app.screen, TagRegisterScreen)

    run_pilot(app, go)


def test_when_the_filter_matches_nothing_the_panel_says_so_and_no_tag_is_described() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: TagRegisterScreen) -> None:
        assert screen.detail is not None  # the first tag is described
        await pilot.press("slash")
        screen.query_one("#tags-filter", Input).value = "no such tag"
        await pilot.pause()
        assert numbers(screen) == [] and screen.detail is None
        assert "No tag matches." in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert screen.detail is not None and screen.detail.number == "47-FV-1001"

    scenario(world(), steps)
