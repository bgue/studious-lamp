"""Acceptance for P2-I1-T05d: the CWP register screen (``tl_tui.widgets.cwp_register``) on the
``FakeClient`` with ``seed_awp``, through the Textual pilot as ``tests/helpers.py`` does. No
database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05d.py``. Prints ``PASS <check>`` per check, then
``T05d ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_awp import PROJECT, seed_awp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable, Static  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.widgets import cwp_register  # noqa: E402
from tl_tui.widgets.cwp_register import CwpRegisterScreen  # noqa: E402

MOUNT_WIDTHS = (80, 170)
HEIGHT = 44
Step = Callable[[Pilot[None], TlApp, CwpRegisterScreen], Awaitable[None]]


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def seeded() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    return client


def with_extra_cwa_less() -> FakeClient:
    """The seed plus a CWP with no CWA, numbered first: ``c`` must move it last."""
    client = FakeClient()
    seed_awp(client)
    details = [client.get_cwp(PROJECT, f"P123-CWP-{n:04d}") for n in (1, 2, 3)]
    extra = details[0].model_copy(update={"number": "P123-CWP-0000", "id": "CWP-0", "cwa": None})
    client.load_awp(PROJECT, cwps=[extra, *details])
    return client


def run(
    client: FakeClient, width: int, steps: Step | None = None
) -> tuple[TlApp, CwpRegisterScreen]:
    """Mount the register on ``client`` at ``width`` columns; ``steps`` runs in the pilot."""
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    found: list[CwpRegisterScreen] = []

    async def go(pilot: Pilot[None]) -> None:
        screen = CwpRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        found.append(screen)
        if steps is not None:
            await steps(pilot, app, screen)

    run_pilot(app, go, size=(width, HEIGHT))
    return app, found[0]


def numbers(screen: CwpRegisterScreen) -> list[str]:
    return [row.number for row in screen.shown]


def row_count(screen: CwpRegisterScreen) -> int:
    return screen.query_one("#log-table", DataTable).row_count


def status(screen: CwpRegisterScreen) -> str:
    return str(screen.query_one("#log-status", Static).render())


def check_mount(width: int) -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: CwpRegisterScreen) -> None:
        seen["text"] = screen_text(app)
        seen["rows"] = row_count(screen)
        seen["panel"] = panel_of(screen)

    run(seeded(), width, steps)
    lines = str(seen["text"]).splitlines()
    widest = max((len(line) for line in lines), default=0)
    print(f"-- width {width}")
    print("\n".join(lines[:8]))
    need(widest <= width, f"a line is {widest} columns wide at {width}")
    need(seen["rows"] == 3, "the seed has 3 CWP rows")
    header = next((line for line in lines if "Number" in line and "State" in line), "")
    need(header != "", "no header row with Number and State")
    need(header.index("Subject") < header.index("State"), "Subject is right of the third column")
    if width >= 160:
        panel = str(seen["panel"])
        print(panel)
        need("P123-CWP-0001 · Piping spool set" in panel, "panel has no heading")
        need("Released for IWP development" in panel, "panel has no state")
        panel_lines = [line.strip() for line in panel.splitlines()]
        summary = panel_lines[2] if len(panel_lines) > 2 else ""
        need(" · " in summary and summary != "", f"panel has no summary line: {summary!r}")
    passed(f"mount {width}")


def check_keys() -> None:
    def steps(pilot: Pilot[None], app: TlApp, screen: CwpRegisterScreen) -> Awaitable[None]:
        async def run_keys() -> None:
            need(row_count(screen) == 4, f"start: {row_count(screen)} rows")
            await pilot.press("d")
            await settle(pilot)
            need(row_count(screen) == 1, f"d (ELE): {row_count(screen)} rows")
            await pilot.press("d")
            await settle(pilot)
            need(row_count(screen) == 3, f"d (PIP): {row_count(screen)} rows")
            await pilot.press("d")
            await settle(pilot)
            need(row_count(screen) == 4, f"d (all again): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 1, f"s (first state): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 1, f"s (second state): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 2, f"s (third state): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 4, "s (all again) must show 4 rows")
            need(numbers(screen) == [f"P123-CWP-{n:04d}" for n in range(4)], "number order")
            await pilot.press("c")
            await settle(pilot)
            need(
                numbers(screen)
                == ["P123-CWP-0001", "P123-CWP-0002", "P123-CWP-0003", "P123-CWP-0000"],
                f"c orders by CWA: {numbers(screen)}",
            )
            need("by CWA" in screen_text(app), "the summary does not name the grouping")
            await pilot.press("c")
            await settle(pilot)
            need(numbers(screen)[0] == "P123-CWP-0000", "c again must restore number order")

        return run_keys()

    run(with_extra_cwa_less(), 170, steps)
    passed("keys")


def check_enter() -> None:
    calls: list[tuple[Any, ...]] = []

    def fake_open(*args: Any) -> None:
        calls.append(args)

    def steps(pilot: Pilot[None], app: TlApp, screen: CwpRegisterScreen) -> Awaitable[None]:
        async def press() -> None:
            await pilot.press("enter")
            await settle(pilot)

        return press()

    with mock.patch.object(cwp_register, "open_record", fake_open):
        run(seeded(), 170, steps)
    need(len(calls) == 1, f"open_record called {len(calls)} times")
    passed("enter")


def check_missing() -> None:
    client = seeded()

    def gone(project: str, number: str) -> None:
        raise RecordNotFoundError(f"no CWP {number!r}")

    client.get_cwp = gone  # type: ignore[method-assign]
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: CwpRegisterScreen) -> None:
        seen["status"] = status(screen)

    run(client, 170, steps)
    text = seen["status"]
    print(f"status: {text}")
    need("no CWP" in text, f"the status does not name the error: {text!r}")
    passed("missing")


def main() -> None:
    check_mount(MOUNT_WIDTHS[0])
    check_mount(MOUNT_WIDTHS[1])
    check_keys()
    check_enter()
    check_missing()
    print("T05d ok")


if __name__ == "__main__":
    try:
        main()
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
