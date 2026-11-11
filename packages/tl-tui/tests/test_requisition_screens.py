"""The requisition log and the requisition screen at 80 and 170 columns (P2-I4A T07a)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_requisitions import PROJECT, seed_requisitions
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_tui.app import TlApp
from tl_tui.widgets.requisition_register import RequisitionLogScreen, RequisitionScreen

MOUNT_WIDTHS = (80, 170)
HEIGHT = 44
ACTOR = "user:uma"  # raised REQ-1, REQ-3 and REQ-5 in the seed
Step = Callable[[Pilot[None], TlApp, RequisitionLogScreen], Awaitable[None]]


def need(ok: bool, what: str) -> None:
    assert ok, what


def seeded() -> FakeClient:
    client = FakeClient()
    seed_requisitions(client)
    return client


def run(
    client: FakeClient, width: int, steps: Step | None = None
) -> tuple[TlApp, RequisitionLogScreen]:
    """Mount the log on ``client`` at ``width`` columns; ``steps`` runs in the pilot."""
    app = TlApp(client, scope=SCOPE, actor=ACTOR)
    found: list[RequisitionLogScreen] = []

    async def go(pilot: Pilot[None]) -> None:
        screen = RequisitionLogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        found.append(screen)
        if steps is not None:
            await steps(pilot, app, screen)

    run_pilot(app, go, size=(width, HEIGHT))
    return app, found[0]


def row_count(screen: RequisitionLogScreen) -> int:
    return screen.query_one("#log-table", DataTable).row_count


def check_mount(width: int) -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: RequisitionLogScreen) -> None:
        seen["text"] = screen_text(app)
        seen["rows"] = row_count(screen)

    run(seeded(), width, steps)
    lines = str(seen["text"]).splitlines()
    widest = max((len(line) for line in lines), default=0)
    need(widest <= width, f"a line is {widest} columns wide at {width}")
    need(seen["rows"] == 5, "the seed has 5 requisition rows")
    header = next((line for line in lines if "Number" in line and "State" in line), "")
    need(header != "", "no header row with Number and State")
    need(header.index("Subject") < header.index("State"), "Subject is right of the third column")
    before_subject = header[: header.index("Subject")].split()
    need(len(before_subject) <= 1, f"Subject is right of the third column: {header!r}")


def test_mounts_at_80_and_170_without_overflow() -> None:
    for width in MOUNT_WIDTHS:
        check_mount(width)


def test_keys_change_the_row_count() -> None:
    def steps(pilot: Pilot[None], app: TlApp, screen: RequisitionLogScreen) -> Awaitable[None]:
        async def run_keys() -> None:
            need(row_count(screen) == 5, f"start: {row_count(screen)} rows")
            await pilot.press("k")
            await settle(pilot)
            need(row_count(screen) == 1, f"k (general): {row_count(screen)} rows")
            await pilot.press("k")
            await settle(pilot)
            need(row_count(screen) == 2, f"k (labour): {row_count(screen)} rows")
            await pilot.press("k")
            await pilot.press("k")
            await pilot.press("k")
            await settle(pilot)
            need(row_count(screen) == 5, f"k (all again): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 1, f"s (Approved): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 1, f"s (Rejected): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 3, f"s (Requested): {row_count(screen)} rows")
            await pilot.press("s")
            await settle(pilot)
            need(row_count(screen) == 5, f"s (all again): {row_count(screen)} rows")
            await pilot.press("m")
            await settle(pilot)
            need(row_count(screen) == 3, f"m (raised by uma): {row_count(screen)} rows")
            need("requester uma" in screen_text(app), "the summary does not name the requester")
            await pilot.press("m")
            await settle(pilot)
            need(row_count(screen) == 5, f"m (all again): {row_count(screen)} rows")

        return run_keys()

    run(seeded(), 170, steps)


def test_enter_opens_the_work_order_section() -> None:
    def steps(pilot: Pilot[None], app: TlApp, screen: RequisitionLogScreen) -> Awaitable[None]:
        async def run_enter() -> None:
            await pilot.press("enter")
            await settle(pilot)
            need(isinstance(app.screen, RequisitionScreen), "Enter did not open the requisition")
            text = screen_text(app)
            need("Work order" in text, "no Work order section")
            need(f"{PROJECT}-WO-0001 · Scheduled" in text, "the work order is not named")

        return run_enter()

    run(seeded(), 170, steps)


def test_a_missing_requisition_shows_an_error_not_a_traceback() -> None:
    client = seeded()
    app = TlApp(client, scope=SCOPE, actor=ACTOR)
    seen: dict[str, str] = {}

    async def go(pilot: Pilot[None]) -> None:
        screen = RequisitionScreen(client, PROJECT, f"{PROJECT}-REQ-9999")
        app.push_screen(screen)
        await settle(pilot)
        seen["status"] = str(screen.query_one("#req-status", Static).render())
        seen["text"] = screen_text(app)

    run_pilot(app, go, size=(170, HEIGHT))
    need(seen["status"].startswith("! "), f"no error status: {seen['status']!r}")
    need("could not be read" in seen["text"], "no read-failure text on the screen")
    need("Traceback" not in seen["text"], "a traceback is shown")
