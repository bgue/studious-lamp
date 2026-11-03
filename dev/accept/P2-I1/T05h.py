"""Acceptance for P2-I1-T05h: the five awp palette entries and their app actions (``tl_tui.app``
``_push_awp``; ``tl_tui.commands.APP_COMMANDS``). The ``FakeClient`` with ``seed_awp``, through the
Textual pilot as ``tests/helpers.py`` does. No database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05h.py``. Prints ``PASS <check>`` per check, then
``T05h ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_awp import seed_awp  # noqa: E402
from helpers import run_pilot, settle  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import Input, OptionList  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.commands import APP_COMMANDS  # noqa: E402
from tl_tui.widgets.cwa_register import CwaRegisterScreen  # noqa: E402
from tl_tui.widgets.cwp_register import CwpRegisterScreen  # noqa: E402
from tl_tui.widgets.package_log import PackageLogScreen  # noqa: E402
from tl_tui.widgets.path_screen import PathScreen  # noqa: E402
from tl_tui.widgets.wbs_screen import WbsScreen  # noqa: E402

SIZE = (170, 44)
EXPECTED: dict[str, type] = {
    "cwps": CwpRegisterScreen,
    "wbs": WbsScreen,
    "cwas": CwaRegisterScreen,
    "path": PathScreen,
    "packages": PackageLogScreen,
}
Step = Callable[[Pilot[None], TlApp], Awaitable[None]]


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def make_app(scope: str = SCOPE) -> TlApp:
    client = FakeClient()
    seed_awp(client)
    return TlApp(client, scope=scope, actor="user:kim")


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[None]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=SIZE)


def check_commands() -> None:
    ids = [c.id for c in APP_COMMANDS]
    need(len(ids) == len(set(ids)), "APP_COMMANDS ids are not unique")
    rows = {c.id: c for c in APP_COMMANDS}
    for cid, cls in EXPECTED.items():
        need(cid in rows, f"{cid} is not in APP_COMMANDS")
        row = rows[cid]
        need(row.keys == "", f"{cid} has a key {row.keys!r}; the ticket says none")
        need(row.action == cid, f"{cid} names action {row.action!r}")
        need(callable(getattr(TlApp, f"action_{row.action}", None)), f"no action_{cid} on TlApp")
        need(cls is not None, f"no screen for {cid}")
    passed("commands")


def top_row(app: TlApp) -> Any:
    """The palette's highlighted row (what Enter would choose), read without choosing it."""
    palette = app.screen
    index = palette.query_one("#palette-list", OptionList).highlighted
    rows = palette.rows
    return rows[index].choice if index is not None and 0 <= index < len(rows) else None


def check_open(cid: str) -> None:
    cls = EXPECTED[cid]
    label = next(c.label for c in APP_COMMANDS if c.id == cid)
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        base = len(app.screen_stack)
        # By the action itself.
        getattr(app, f"action_{cid}")()
        await settle(pilot)
        seen["action"] = app.screen
        await pilot.press("escape")
        await settle(pilot)
        seen["action_back"] = len(app.screen_stack) == base
        # By the palette, typing the entry's label; Enter runs the command the row names.
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = label
        await settle(pilot)
        seen["label_choice"] = top_row(app)
        await pilot.press("enter")
        await settle(pilot)
        seen["palette"] = app.screen
        await pilot.press("escape")
        await settle(pilot)
        seen["palette_back"] = len(app.screen_stack) == base
        # Observation only: typing the id (the palette matches labels, not ids).
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = cid
        await settle(pilot)
        seen["id_choice"] = top_row(app)
        await pilot.press("escape")
        await settle(pilot)
        seen["id_back"] = len(app.screen_stack) == base

    run(make_app(), steps)
    need(isinstance(seen["action"], cls), f"action_{cid} opened {type(seen['action']).__name__}")
    need(seen["action_back"], f"Esc did not return from action_{cid}")
    choice = seen["label_choice"]
    need(
        choice is not None and choice.command_id == cid,
        f"typing the label of {cid} ranks {getattr(choice, 'command_id', None)!r} first",
    )
    need(isinstance(seen["palette"], cls), f"palette {cid} opened {type(seen['palette']).__name__}")
    need(seen["palette_back"], f"Esc did not return from palette {cid}")
    need(seen["id_back"], f"Esc did not close the palette after typing the id of {cid}")
    passed(f"open {cid}")
    passed(f"palette {cid}")
    id_choice = seen["id_choice"]
    print(f"INFO typing the id {cid!r} ranks {getattr(id_choice, 'command_id', None)!r} first")


def check_no_project() -> None:
    seen: dict[str, Any] = {"notices": [], "stack": []}

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        base = len(app.screen_stack)
        real_notify = app.notify

        def record(message: str, *args: Any, severity: str = "information", **kw: Any) -> Any:
            seen["notices"].append((str(message), severity))
            return real_notify(message, *args, severity=severity, **kw)

        app.notify = record  # type: ignore[method-assign]
        for cid in EXPECTED:
            getattr(app, f"action_{cid}")()
            await settle(pilot)
            seen["stack"].append(len(app.screen_stack) == base)

    run(make_app("company"), steps)
    need(all(seen["stack"]), f"a no-project action pushed a screen: {seen['stack']}")
    need(len(seen["notices"]) == len(EXPECTED), f"notices: {seen['notices']}")
    need(
        all(sev == "warning" for _, sev in seen["notices"]),
        f"a no-project notice is not a warning: {seen['notices']}",
    )
    passed("no project")


def main() -> None:
    check_commands()
    for cid in EXPECTED:
        check_open(cid)
    check_no_project()
    print("T05h ok")


if __name__ == "__main__":
    try:
        main()
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
