"""Reaching the toolcrib line: the palette entry, the keys F2, F3 and Ctrl+R, and one issue line
(P2-I4B-T07a). The ``FakeClient`` with a toolcrib location and one lot in stock, through the
Textual pilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.widgets import Input, Static
from tl_mod_materials import views
from tl_mod_materials.handlers.movements import IssueStock
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.toolcrib_text import KEYS
from tl_tui.widgets.toolcrib_screen import ToolcribScreen

SIZE = (170, 44)
ACTOR = "user:uma"
PROJECT = "P123"  # the project of SCOPE
LOT = "BL/26-07"
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def seed_toolcrib(client: FakeClient) -> None:
    """Two toolcribs (TC2 listed first in the rows, TC1 sorts first) and one lot in TC1."""
    locations = [
        views.LocationView(
            id="loc-tc2",
            code="TC2",
            title="Crib 2",
            kind="toolcrib",
            parent_code=None,
            depth=0,
            retired=False,
            lots=0,
            lines=0,
        ),
        views.LocationView(
            id="loc-tc1",
            code="TC1",
            title="Crib 1",
            kind="toolcrib",
            parent_code=None,
            depth=0,
            retired=False,
            lots=1,
            lines=1,
        ),
    ]
    stock = [
        views.StockRowView(
            lot=LOT,
            heat_no=None,
            item_code="BOLT-M16",
            item_title="Bolt M16",
            location="TC1",
            location_title="Crib 1",
            on_hand=Decimal("10"),
            reserved=Decimal("0"),
            available=Decimal("10"),
            uom="ea",
        )
    ]
    client.put_materials(PROJECT, locations=locations, stock=stock)


def no_crib(client: FakeClient) -> None:
    """A project with a store location and no toolcrib."""
    store = views.LocationView(
        id="loc-st1",
        code="ST1",
        title="Store 1",
        kind="store",
        parent_code=None,
        depth=0,
        retired=False,
        lots=0,
        lines=0,
    )
    client.put_materials(PROJECT, locations=[store])


def make_app(seed: Callable[[FakeClient], None] = seed_toolcrib) -> TlApp:
    client = FakeClient()
    seed(client)
    return TlApp(client, scope=SCOPE, actor=ACTOR)


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=SIZE)


def label_of(cid: str) -> str:
    return next(c.label for c in APP_COMMANDS if c.id == cid)


async def choose_toolcrib(pilot: Pilot[Any], app: TlApp) -> None:
    """Open the palette, type the entry's label and press Enter."""
    app.action_palette()
    await settle(pilot)
    app.screen.query_one("#palette-input", Input).value = label_of("toolcrib")
    await settle(pilot)
    await pilot.press("enter")
    await settle(pilot)


def notices(app: TlApp) -> list[str]:
    return [str(n.message) for n in app._notifications]


# --- the palette and the key text -----------------------------------------------------------------


def test_the_palette_lists_toolcrib_with_no_key() -> None:
    rows = {c.id: c for c in APP_COMMANDS}
    assert "toolcrib" in rows
    assert rows["toolcrib"].keys == ""
    assert callable(getattr(TlApp, f"action_{rows['toolcrib'].action}", None))
    assert len({c.id for c in APP_COMMANDS}) == len(APP_COMMANDS)


def test_the_key_line_names_f2_f3_and_ctrl_r_and_not_ctrl_i() -> None:
    assert "F2" in KEYS and "F3" in KEYS and "Ctrl+R" in KEYS
    assert "Ctrl+I" not in KEYS


def test_the_screen_binds_f2_f3_and_ctrl_r_and_not_ctrl_i() -> None:
    keys = {str(b.key) for b in ToolcribScreen.BINDINGS}  # type: ignore[attr-defined]
    assert {"f2", "f3", "ctrl+r"} <= keys
    assert "ctrl+i" not in keys


# --- the palette entry ----------------------------------------------------------------------------


def test_choosing_toolcrib_shows_the_screen_for_the_first_crib_code() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        await choose_toolcrib(pilot, app)
        seen["screen"] = app.screen
        seen["grew"] = len(app.screen_stack) == base + 1

    run(make_app(), steps)
    screen = seen["screen"]
    assert isinstance(screen, ToolcribScreen), type(screen).__name__
    assert seen["grew"]
    assert screen.crib == "TC1"
    assert screen.project == PROJECT


def test_with_no_toolcrib_the_entry_shows_the_notice_and_stays_put() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        await choose_toolcrib(pilot, app)
        seen["same"] = len(app.screen_stack) == base
        seen["screen"] = app.screen

    app = make_app(no_crib)
    run(app, steps)
    assert seen["same"]
    assert not isinstance(seen["screen"], ToolcribScreen)
    assert "No toolcrib in this project. Add a location of kind toolcrib." in notices(app)


def test_with_a_modal_open_the_entry_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(ToolcribScreen(app.client, PROJECT, ACTOR, "TC1"))
        await settle(pilot)
        base = len(app.screen_stack)
        app.action_toolcrib()
        await settle(pilot)
        seen["same"] = len(app.screen_stack) == base

    run(make_app(), steps)
    assert seen["same"]


# --- the keys on the screen -----------------------------------------------------------------------


def test_f3_f2_and_ctrl_r_set_the_mode_and_keep_the_line_and_focus() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        await choose_toolcrib(pilot, app)
        screen: Any = app.screen
        line = screen.query_one("#tc-line", Input)
        line.value = "BL/26-07 Ana Ruiz"
        title = screen.query_one("#tc-title", Static)
        await pilot.press("f3")
        await settle(pilot)
        seen["f3"] = str(title.render())
        seen["f3_line"] = line.value
        seen["f3_focus"] = screen.focused is line
        await pilot.press("f2")
        await settle(pilot)
        seen["f2"] = str(title.render())
        await pilot.press("ctrl+r")
        await settle(pilot)
        seen["ctrl_r"] = str(title.render())
        seen["end_line"] = line.value
        seen["end_focus"] = screen.focused is line

    run(make_app(), steps)
    assert "Return a tool" in seen["f3"]
    assert "Issue a tool" in seen["f2"]
    assert "Return a tool" in seen["ctrl_r"]
    assert seen["f3_line"] == "BL/26-07 Ana Ruiz"
    assert seen["end_line"] == "BL/26-07 Ana Ruiz"
    assert seen["f3_focus"] and seen["end_focus"]


# --- one issue line ------------------------------------------------------------------------------


def test_one_issue_line_posts_one_issue_and_clears_the_line() -> None:
    client = FakeClient()
    seed_toolcrib(client)
    app = TlApp(client, scope=SCOPE, actor=ACTOR)
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        await choose_toolcrib(pilot, app)
        screen: Any = app.screen
        line = screen.query_one("#tc-line", Input)
        line.value = f"{LOT} Ana Ruiz"
        await pilot.press("enter")
        await settle(pilot)
        seen["value"] = line.value

    run(app, steps)
    assert len(client.materials_commands) == 1
    cmd = client.materials_commands[0]
    assert isinstance(cmd, IssueStock)
    assert seen["value"] == ""
