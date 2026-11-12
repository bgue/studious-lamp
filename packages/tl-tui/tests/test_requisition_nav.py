"""Reaching the requisition and work order screens: palette entries, the ``w`` key from a
requisition to its work order (P2-I4A T07d). The ``FakeClient`` with ``seed_requisitions``, through
the Textual pilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_requisitions import PROJECT, seed_requisitions
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.widgets import Input, OptionList
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.widgets.requisition_register import RequisitionLogScreen, RequisitionScreen
from tl_tui.widgets.work_order_backlog import WorkOrderBacklogScreen, WorkOrderScreen

SIZE = (170, 44)
ACTOR = "user:uma"
APPROVED_WITH_ORDER = f"{PROJECT}-REQ-0001"  # Approved; its work order is WO-0001
REQUESTED_NO_ORDER = f"{PROJECT}-REQ-0002"  # Requested; no work order yet
EXPECTED: dict[str, type] = {
    "requisitions": RequisitionLogScreen,
    "work-orders": WorkOrderBacklogScreen,
}
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app() -> TlApp:
    client = FakeClient()
    seed_requisitions(client)
    return TlApp(client, scope=SCOPE, actor=ACTOR)


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=SIZE)


def label_of(cid: str) -> str:
    return next(c.label for c in APP_COMMANDS if c.id == cid)


def top_choice(app: TlApp) -> Any:
    """The palette's highlighted row, read without choosing it."""
    palette: Any = app.screen
    index = palette.query_one("#palette-list", OptionList).highlighted
    rows = palette.rows
    return rows[index].choice if index is not None and 0 <= index < len(rows) else None


# --- the palette ----------------------------------------------------------------------------------


def test_the_palette_lists_requisitions_and_work_orders_with_no_key() -> None:
    rows = {c.id: c for c in APP_COMMANDS}
    for cid in EXPECTED:
        assert cid in rows, f"{cid} is not in APP_COMMANDS"
        assert rows[cid].keys == "", f"{cid} has a key {rows[cid].keys!r}"
        assert callable(getattr(TlApp, f"action_{rows[cid].action}", None))
    assert len({c.id for c in APP_COMMANDS}) == len(APP_COMMANDS)


@pytest.mark.parametrize("cid", list(EXPECTED))
def test_typing_the_label_ranks_the_command_first(cid: str) -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = label_of(cid)
        await settle(pilot)
        seen["choice"] = top_choice(app)

    run(make_app(), steps)
    choice = seen["choice"]
    assert choice is not None and choice.command_id == cid, (
        f"typing the label of {cid} ranks {getattr(choice, 'command_id', None)!r} first"
    )


@pytest.mark.parametrize("cid", list(EXPECTED))
def test_choosing_the_palette_entry_opens_its_screen_and_esc_returns(cid: str) -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = label_of(cid)
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen
        await pilot.press("escape")
        await settle(pilot)
        seen["back"] = len(app.screen_stack) == base

    run(make_app(), steps)
    assert isinstance(seen["screen"], EXPECTED[cid]), (
        f"palette {cid} opened {type(seen['screen']).__name__}"
    )
    assert seen["back"], f"Esc did not return from palette {cid}"


# --- the w key ------------------------------------------------------------------------------------


def test_w_on_an_approved_requisition_shows_its_work_order_and_esc_returns() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(RequisitionScreen(app.client, PROJECT, APPROVED_WITH_ORDER))
        await settle(pilot)
        seen["req"] = app.screen
        await pilot.press("w")
        await settle(pilot)
        seen["wo"] = app.screen
        seen["wo_key"] = getattr(app.screen, "key", None)
        await pilot.press("escape")
        await settle(pilot)
        seen["back"] = app.screen

    run(make_app(), steps)
    assert isinstance(seen["req"], RequisitionScreen)
    assert isinstance(seen["wo"], WorkOrderScreen), f"w opened {type(seen['wo']).__name__}"
    assert seen["wo_key"] == f"{PROJECT}-WO-0001"
    assert isinstance(seen["back"], RequisitionScreen), "Esc did not return to the requisition"


def test_w_on_a_requisition_with_no_work_order_does_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(RequisitionScreen(app.client, PROJECT, REQUESTED_NO_ORDER))
        await settle(pilot)
        seen["before"] = len(app.screen_stack)
        await pilot.press("w")
        await settle(pilot)
        seen["after"] = len(app.screen_stack)
        seen["top"] = app.screen

    run(make_app(), steps)
    assert seen["after"] == seen["before"], "w pushed a screen with no work order"
    assert isinstance(seen["top"], RequisitionScreen)
