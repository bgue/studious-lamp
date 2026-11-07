"""The five awp palette entries and their app actions (P2-I1-T12; pytest form of
``dev/accept/P2-I1/T05h.py``). The ``FakeClient`` with ``seed_awp``, through the Textual pilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_awp import seed_awp
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.widgets import Input, OptionList
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.widgets.cwa_register import CwaRegisterScreen
from tl_tui.widgets.cwp_register import CwpRegisterScreen
from tl_tui.widgets.package_log import PackageLogScreen
from tl_tui.widgets.path_screen import PathScreen
from tl_tui.widgets.wbs_screen import WbsScreen

SIZE = (170, 44)
EXPECTED: dict[str, type] = {
    "cwps": CwpRegisterScreen,
    "wbs": WbsScreen,
    "cwas": CwaRegisterScreen,
    "path": PathScreen,
    "packages": PackageLogScreen,
}
IDS = list(EXPECTED)
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app(scope: str = SCOPE) -> TlApp:
    client = FakeClient()
    seed_awp(client)
    return TlApp(client, scope=scope, actor="user:kim")


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=SIZE)


def label_of(cid: str) -> str:
    return next(c.label for c in APP_COMMANDS if c.id == cid)


def top_row(app: TlApp) -> Any:
    """The palette's highlighted row (what Enter would choose), read without choosing it."""
    palette: Any = app.screen
    index = palette.query_one("#palette-list", OptionList).highlighted
    rows = palette.rows
    return rows[index].choice if index is not None and 0 <= index < len(rows) else None


# --- the palette ids ----------------------------------------------------------------------------


def test_the_five_ids_are_in_app_commands_unique_keyless_and_bound_to_actions() -> None:
    ids = [c.id for c in APP_COMMANDS]
    assert len(ids) == len(set(ids))
    rows = {c.id: c for c in APP_COMMANDS}
    for cid in IDS:
        assert cid in rows, f"{cid} is not in APP_COMMANDS"
        row = rows[cid]
        assert row.keys == "", f"{cid} has a key {row.keys!r}"
        assert row.action == cid, f"{cid} names action {row.action!r}"
        assert callable(getattr(TlApp, f"action_{row.action}", None))


# --- each entry opens its screen ----------------------------------------------------------------


@pytest.mark.parametrize("cid", IDS)
def test_action_opens_the_screen(cid: str) -> None:
    cls = EXPECTED[cid]
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        getattr(app, f"action_{cid}")()
        await settle(pilot)
        seen["screen"] = app.screen
        await pilot.press("escape")
        await settle(pilot)
        seen["depth_back"] = len(app.screen_stack) == base

    run(make_app(), steps)
    assert isinstance(seen["screen"], cls), f"action_{cid} opened {type(seen['screen']).__name__}"
    assert seen["depth_back"], f"Esc did not return from action_{cid}"


@pytest.mark.parametrize("cid", IDS)
def test_palette_opens_the_screen(cid: str) -> None:
    cls = EXPECTED[cid]
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = label_of(cid)
        await settle(pilot)
        seen["choice"] = top_row(app)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen
        await pilot.press("escape")
        await settle(pilot)
        seen["depth_back"] = len(app.screen_stack) == base

    run(make_app(), steps)
    choice = seen["choice"]
    assert choice is not None and choice.command_id == cid, (
        f"typing the label of {cid} ranks {getattr(choice, 'command_id', None)!r} first"
    )
    assert isinstance(seen["screen"], cls), f"palette {cid} opened {type(seen['screen']).__name__}"
    assert seen["depth_back"], f"Esc did not return from palette {cid}"


# --- no project in scope ------------------------------------------------------------------------


def test_no_project_scope_warns() -> None:
    seen: dict[str, Any] = {"per_action": {}}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        notices: list[tuple[str, str]] = []
        real_notify = app.notify

        def record(message: str, *args: Any, severity: Any = "information", **kw: Any) -> Any:
            notices.append((str(message), str(severity)))
            return real_notify(message, *args, severity=severity, **kw)

        app.notify = record  # type: ignore[method-assign]
        for cid in IDS:
            before = len(notices)
            getattr(app, f"action_{cid}")()
            await settle(pilot)
            seen["per_action"][cid] = {
                "no_screen": len(app.screen_stack) == base,
                "new_notices": notices[before:],
            }

    run(make_app("company"), steps)
    for cid in IDS:
        result = seen["per_action"][cid]
        assert result["no_screen"], f"a no-project action {cid} pushed a screen"
        new = result["new_notices"]
        assert len(new) == 1, f"action {cid} raised {len(new)} notices: {new}"
        assert new[0][1] == "warning", f"action {cid} notice is not a warning: {new}"
