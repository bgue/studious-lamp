"""Workflow action menu: text, the modal, and the `w` key of the app (P0-I3-T15; brief 8)."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_core.services.workflow import TransitionOption, WorkflowStatus
from tl_core.workflow.engine import GuardResult
from tl_tui.app import TlApp
from tl_tui.widgets.footer import TlFooter
from tl_tui.widgets.record_view import RecordView
from tl_tui.widgets.workflow_menu import WorkflowMenu, guard_lines, header_text, option_line


def option(allowed: bool, guards: list[GuardResult]) -> TransitionOption:
    return TransitionOption(
        transition="approve",
        label="Approve",
        from_state="Review",
        to_state="Approved",
        allowed=allowed,
        guards=guards,
    )


def status() -> WorkflowStatus:
    return WorkflowStatus(
        record_id="r1",
        key="P123-REC-0001",
        workflow="core.review",
        workflow_version=1,
        state="Review",
        state_label="Review",
        entered_at="2026-10-09T09:05:00+00:00",
        version=2,
        options=[],
    )


# --- pure functions -----------------------------------------------------------------------------


def test_header_text() -> None:
    assert header_text(status()) == (
        "P123-REC-0001  core.review v1\nState: Review  (since 2026-10-09 09:05)"
    )


def test_option_line_shows_the_verdict_with_a_symbol() -> None:
    assert option_line(option(True, [])) == "Approve → Approved  ✓ allowed"
    assert option_line(option(False, [])) == "Approve → Approved  ✗ blocked"


def test_guard_lines_mark_each_guard() -> None:
    guards = [
        GuardResult(kind="expected_links", passed=False, message="missing links: data sheet"),
        GuardResult(kind="conformance", passed=True, message="conformance is ok in Approved"),
    ]
    assert guard_lines(option(False, guards)) == [
        "  ✗ expected_links: missing links: data sheet",
        "  ✓ conformance: conformance is ok in Approved",
    ]
    assert guard_lines(option(True, [])) == ["  (no guards)"]


# --- the modal ----------------------------------------------------------------------------------


class Host(App[None]):
    def __init__(
        self, client: FakeClient, key: str = "FV-1001", roles: tuple[str, ...] = ()
    ) -> None:
        super().__init__()
        self.client = client
        self.key = key
        self.roles = roles
        self.results: list[bool | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        record = self.client.get_record(SCOPE, self.key)
        assert record is not None
        menu = WorkflowMenu(self.client, SCOPE, record, roles=self.roles, actor="user:t")
        self.push_screen(menu, self.results.append)


def test_it_shows_the_state_the_transitions_and_why_one_is_blocked() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1001  fake.valves v1" in text
        assert "State: Design  (since 2026-10-09" in text
        assert "Roles: none" in text
        assert "Install → Installed  ✗ blocked" in text
        assert "✗ expected_links: missing links: data sheet (0 of 1)" in text
        assert "✗ roles: needs one of the roles: engineer" in text

    run_pilot(app, scenario, size=(110, 40))


def test_enter_on_a_blocked_transition_explains_and_stays_open() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []
        assert "Blocked: missing links: data sheet (0 of 1); needs one of the roles: engineer" in (
            screen_text(app)
        )
        assert client.get_record(SCOPE, "FV-1001")["status"] == "Design"  # type: ignore[index]

    run_pilot(app, scenario, size=(130, 40))


def test_an_allowed_transition_runs_and_dismisses_with_true() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    app = Host(client, roles=("engineer",))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Roles: engineer" in text and "Install → Installed  ✓ allowed" in text
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [True]
        record = client.get_record(SCOPE, "FV-1001")
        assert record is not None and record["status"] == "Installed"
        (cmd,) = [c for c in client.link_commands if hasattr(c, "transition")]
        assert (cmd.actor, cmd.source, cmd.transition, cmd.actor_roles) == (
            "user:t",
            "tui",
            "install",
            ["engineer"],
        )
        assert cmd.expected_version == 3

    run_pilot(app, scenario, size=(110, 40))


def test_up_and_down_change_the_guards_shown() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1003", "FV-1001")
    app = Host(client, key="FV-1003")  # Installed: commission and revert, no guards

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Commission → Commissioned  ✓ allowed" in text
        assert "Back to design → Design  ✓ allowed" in text
        assert "(no guards)" in text
        await pilot.press("down", "up")
        await pilot.pause()

    run_pilot(app, scenario, size=(110, 40))


def test_escape_closes_with_false() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [False]

    run_pilot(app, scenario, size=(110, 40))


def test_a_record_with_no_options_says_so() -> None:
    client = FakeClient.with_valve_example()
    record = client._records_by_key("FV-1003")  # pyright: ignore[reportPrivateUsage]
    record["status"] = "Commissioned"
    app = Host(client, key="FV-1003")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "No transitions from this state" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []

    run_pilot(app, scenario, size=(110, 40))


# --- the `w` key of the app ------------------------------------------------------------


def test_w_on_the_grid_opens_the_menu_for_the_cursor_row() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client, roles=("engineer",))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        menu = app.screen
        assert isinstance(menu, WorkflowMenu)
        assert menu.record["key"] == "FV-1001"
        assert menu.roles == ("engineer",)
        await pilot.press("w")  # typed nowhere, and no second menu
        await pilot.pause()
        assert len(app.screen_stack) == 2
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, WorkflowMenu)

    run_pilot(app, scenario, size=(120, 40))


def test_a_transition_from_the_record_view_refreshes_the_view() -> None:
    client = FakeClient.with_valve_example()
    client.seed_link("FV-1001", "FV-1002")
    app = TlApp(client, roles=("engineer",))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, WorkflowMenu)
        view = app.query_one(RecordView)
        assert view.record is not None and view.record["status"] == "Installed"
        assert "Installed" in screen_text(app)

    run_pilot(app, scenario, size=(130, 40))


def test_w_without_a_record_says_so() -> None:
    client = FakeClient()  # no records
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert not isinstance(app.screen, WorkflowMenu)
        assert "Open a record" in app.query_one(TlFooter).status

    run_pilot(app, scenario, size=(120, 40))
