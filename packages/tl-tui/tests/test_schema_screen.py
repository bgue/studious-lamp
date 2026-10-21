"""The schema workbench screen on the fake client, driven with a pilot (P1-I8-T04a).
Provided; do not edit.

The screen lists the package versions as a tree, shows the highlighted one with three tabs
(what it defines, lint, diff), opens the review screen of T04b with `v` and reads the list again
when that closes, and says so when there is nothing to show or the client refuses.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_schemareg import make_package
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.screen import ModalScreen
from textual.widgets import DataTable
from tl_core.services.errors import ServiceError
from tl_mod_schemareg.testing import fixture_text
from tl_mod_schemareg.views import LintIssueView
from tl_tui.app import TlApp
from tl_tui.client import ClientInterface
from tl_tui.display import DisplayMode
from tl_tui.widgets import schema_review_screen
from tl_tui.widgets.schema_screen import SchemaWorkbenchScreen


def full_client() -> FakeClient:
    client = FakeClient()
    client.seed_schema_package(
        make_package(
            "co.acme.engineering",
            "3.2.0",
            "Published",
            content=fixture_text("co.acme.engineering"),
            worst_class="additive",
            analysed=True,
        )
    )
    client.seed_schema_package(
        make_package(
            "co.acme.engineering",
            "3.3.0",
            content=fixture_text("co.acme.engineering"),
            lint=[LintIssueView(severity="error", rule="L1", path="psets.a", message="No text.")],
            diff="--- co.acme.engineering@3.2.0\n+++ co.acme.engineering@3.3.0\n+  seat_leak\n",
            classification=None,
        )
    )
    client.seed_schema_package(
        make_package(
            "x.P123",
            "1.4.0",
            kind="extension",
            scope="project:P123",
            project="P123",
            content=fixture_text("x.P123"),
        )
    )
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[Any], TlApp, SchemaWorkbenchScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=False)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def table(screen: SchemaWorkbenchScreen) -> DataTable[str]:
    return screen.query_one("#schema-table", DataTable)


def show_technical(app: TlApp, screen: SchemaWorkbenchScreen, on: bool) -> None:
    """Switch the app's display mode and draw the workbench again, as the toggle will."""
    mode = DisplayMode()
    mode.technical = on
    app.display_mode = mode  # pyright: ignore[reportAttributeAccessIssue]  # App does not declare it
    screen.refresh_for_display_mode()


def test_ctrl_o_lists_the_versions_as_a_tree_and_escape_closes() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        text = screen_text(app)
        assert "Schema packages (3)" in text and f"scope {SCOPE}" in text
        assert "P123" in text and "Engineering" in text
        names = [str(table(screen).get_row_at(i)[0]) for i in range(3)]
        assert names == ["P123", "Engineering", ""]  # the second 3.x row has no name
        show_technical(app, screen, True)
        names = [str(table(screen).get_row_at(i)[0]) for i in range(3)]
        assert names == ["x.P123", "co.acme.engineering", ""]
        assert table(screen).cursor_row == 0
        show_technical(app, screen, False)
        assert "x.P123" not in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SchemaWorkbenchScreen)

    scenario(full_client(), steps)


def test_the_highlighted_version_shows_its_header_and_what_it_defines() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        text = screen_text(app)
        assert "P123, version 1.4.0  Draft" in text and "Project P123" in text
        assert "[1 Properties]  2 Lint  3 Diff" in text
        assert "extends Engineering, version 3.2.0, Valve data" in text
        assert "add MaterialCode  SS316L-NACE  -> SS316L" in text
        await pilot.press("down")
        await pilot.pause()
        text = screen_text(app)
        assert "Engineering, version 3.3.0  Draft" in text
        assert "pset valve_data  required  mandatory  applies to Record" in text
        show_technical(app, screen, True)
        assert "co.acme.engineering@3.3.0  Draft" in screen_text(app)
        assert "pset valve_data  required  mandatory  applies to core.Record" in screen_text(app)
        show_technical(app, screen, False)
        assert "co.acme.engineering@3.3.0  Draft" not in screen_text(app)

    scenario(full_client(), steps)


def test_the_tabs_show_lint_and_the_diff_and_the_brackets_wrap_round() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        await pilot.press("down")  # 3.3.0, the one with a finding and a diff
        await pilot.press("2")
        await pilot.pause()
        text = screen_text(app)
        assert "1 Properties  [2 Lint]  3 Diff" in text
        assert "Lint: 1 errors, 0 warnings" in text and "error  L1  psets.a  No text." in text
        await pilot.press("3")
        await pilot.pause()
        text = screen_text(app)
        assert "+  seat_leak" in text and "--- co.acme.engineering@3.2.0" in text
        await pilot.press("right_square_bracket")  # wraps to the first tab
        await pilot.pause()
        assert "[1 Properties]" in screen_text(app)
        await pilot.press("left_square_bracket")  # and back to the last
        await pilot.pause()
        assert "[3 Diff]" in screen_text(app)

    scenario(full_client(), steps)


def test_the_version_below_has_no_diff_and_says_why() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        await pilot.press("down", "down", "3")  # 3.2.0: analysed, no base
        await pilot.pause()
        assert "Not analysed yet" in screen_text(app) or "No base to compare" in screen_text(app)

    scenario(full_client(), steps)


def test_an_empty_registry_says_so() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        text = screen_text(app)
        assert "Schema packages (0)" in text and "No package versions." in text
        await pilot.press("v", "2", "3")  # nothing highlighted: nothing happens, nothing breaks
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)

    scenario(FakeClient(), steps)


def test_a_refusal_of_the_list_is_shown_in_the_status_line() -> None:
    client = full_client()

    def refuse(**_: Any) -> Any:
        raise ServiceError("the registry is closed")

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        client.list_schema_packages = refuse  # type: ignore[method-assign]
        await pilot.press("f5")
        await pilot.pause()
        text = screen_text(app)
        assert "! the registry is closed" in text and "Schema packages (0)" in text

    scenario(client, steps)


def test_v_opens_the_review_of_the_highlighted_version_and_the_list_is_read_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = full_client()
    opened: list[tuple[str, str, str]] = []

    class Review(ModalScreen[None]):
        def __init__(self, client: ClientInterface, scope: str, actor: str, ref: str) -> None:
            super().__init__()
            opened.append((scope, actor, ref))

    monkeypatch.setattr(schema_review_screen, "SchemaReviewScreen", Review)

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaWorkbenchScreen) -> None:
        await pilot.press("down", "v")  # 3.3.0
        await pilot.pause()
        assert isinstance(app.screen, Review)
        assert opened == [(SCOPE, "user:boss", "PKG-co.acme.engineering-3.3.0")]
        client.seed_schema_package(make_package("co.acme.standards", "1.0.0"))
        app.screen.dismiss(None)
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)
        assert "Schema packages (4)" in screen_text(app)
        assert table(app.screen).cursor_row >= 0

    scenario(client, steps)


def test_the_key_hints_fit_an_80_column_terminal() -> None:
    assert all(len(line) <= 80 for line in SchemaWorkbenchScreen.KEY_HINTS.splitlines())
