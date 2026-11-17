"""P2-I4B-T06 acceptance: the toolcrib line and its screen, keyboard only.

Run from the repo root after ``dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db``:
``uv run python dev/accept/P2-I4B/T06.py``. Exit 0 with one ``PASS <check>`` line per check.
Each screen check works on its own copy of the seed ledger. The screenshots go to
``.accept/shots/T06-toolcrib-80.svg`` and ``.accept/shots/T06-toolcrib-170.svg`` (untracked).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("TL_ENV", "test")  # the dev ledger rule, as the other P2-W0 scripts set it

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
ACTOR = "user:crib"
CRIB = "TC1"
ITEM_CODE = "ELB-LR-90-6-SCH40"  # the seed's elbow, in the project's library
SIZES = ((80, 30), (170, 40))
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the Textual test helpers

from helpers import settle, static_of  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import Input  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials.handlers.receipts import AcceptReceipt, InspectReceipt  # noqa: E402
from tl_mod_materials.views import StockRowView  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.receipt_entry_text import build_command as receipt_command  # noqa: E402
from tl_tui.toolcrib_text import (  # noqa: E402
    NEED_PERSON,
    done_text,
    no_such_tool,
)
from tl_tui.widgets.toolcrib_screen import ToolcribScreen  # noqa: E402


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def passed(check: str) -> None:
    print(f"PASS {check}")


def copy_ledger(tmp: Path) -> Path:
    """A copy of the seed ledger (and its WAL sidecars) in ``tmp``; the path of the copy."""
    for src in LEDGER.parent.glob(LEDGER.name + "*"):
        shutil.copy(src, tmp / ("tl.db" + src.name[len(LEDGER.name) :]))
    return tmp / "tl.db"


async def type_into(pilot: Pilot[None], text: str) -> None:
    await pilot.press(*text)
    await settle(pilot)


async def clear_line(pilot: Pilot[None], typed: str) -> None:
    """Backspace the typed text out of the line, as a person would."""
    await pilot.press(*["backspace"] * len(typed))
    await settle(pilot)


def crib_stock(client: EmbeddedClient) -> list[StockRowView]:
    return client.list_materials_stock(PROJECT, location=CRIB)


def on_hand_at_crib(client: EmbeddedClient, lot: str) -> Decimal:
    return sum((r.on_hand for r in crib_stock(client) if r.lot == lot), Decimal(0))


def status_of(screen: ToolcribScreen) -> str:
    return static_of(screen, "#tc-status")


def line_of(screen: ToolcribScreen) -> Input:
    return screen.query_one("#tc-line", Input)


Body = Callable[[Pilot[None], TlApp, ToolcribScreen, EmbeddedClient], Awaitable[None]]


def with_screen(size: tuple[int, int], body: Body) -> None:
    """Run ``body`` on the toolcrib screen for ``TC1`` in a fresh copy of the seed ledger."""
    with tempfile.TemporaryDirectory() as tmp:
        db = copy_ledger(Path(tmp))
        client = EmbeddedClient(SqliteUowFactory(db), actor=ACTOR)
        if not crib_stock(client):
            receive_at_crib(client)
        app = TlApp(client, scope=f"project:{PROJECT}", actor=ACTOR)

        async def scenario() -> None:
            async with app.run_test(size=size) as pilot:
                await settle(pilot)
                app.push_screen(ToolcribScreen(client, PROJECT, ACTOR, CRIB))
                await settle(pilot)
                screen = app.screen
                expect(isinstance(screen, ToolcribScreen), type(screen).__name__)
                assert isinstance(screen, ToolcribScreen)
                expect(screen.ready, f"{CRIB} is not a toolcrib of {PROJECT}")
                await body(pilot, app, screen, client)

        asyncio.run(scenario())


def receive_at_crib(client: EmbeddedClient) -> None:
    """The seed holds no stock at TC1 (its receipts land at L2), so the script books one receipt
    there: 5 EA of the seed's elbow, as the receipt form would send it (no PO line, a supplier
    and a delivery reference typed, received today), inspected and accepted so the lot is stock.
    Only the copy of the ledger is changed."""
    header = {
        "po_line": "",
        "supplier": "Northline Pipe Supply",
        "delivery_ref": "DN-TC1",
        "received_on": date.today().isoformat(),
        "location": CRIB,
    }
    lines = [{"item": ITEM_CODE, "qty": "5", "heat": "", "condition": "good"}]
    cmd = receipt_command(header, lines, actor=ACTOR, project=PROJECT)
    made = client.materials_command("CreateReceipt", cmd)
    scope = f"project:{PROJECT}"
    seen = client.materials_command(
        "InspectReceipt",
        InspectReceipt(actor=ACTOR, source="tui", scope=scope, stream_id=made.stream_id),
    )
    client.materials_command(
        "AcceptReceipt",
        AcceptReceipt(
            actor=ACTOR,
            source="tui",
            scope=scope,
            stream_id=made.stream_id,
            expected_version=seen.version,
        ),
    )
    expect(bool(crib_stock(client)), f"the receipt at {CRIB} left no stock there")


def pick_lot(client: EmbeddedClient) -> StockRowView:
    """A lot with stock at the crib, the one the checks issue and return."""
    rows = [r for r in crib_stock(client) if r.on_hand >= 1]
    expect(bool(rows), f"no lot with stock at {CRIB} after the setup receipt")
    return rows[0]


def check_issue_and_return(size: tuple[int, int]) -> None:
    """(1) an issue posts, (2) a return puts the stock back and a too-big return is refused."""

    async def body(
        pilot: Pilot[None], app: TlApp, screen: ToolcribScreen, client: EmbeddedClient
    ) -> None:
        row = pick_lot(client)
        before = on_hand_at_crib(client, row.lot)
        await type_into(pilot, f"{row.lot} Ana Ruiz x1")
        await pilot.press("enter")
        await settle(pilot)
        want = done_text("issue", "1", row.uom, row.lot, "Ana Ruiz")
        expect(status_of(screen) == want, f"status is {status_of(screen)!r}, want {want!r}")
        issues = [
            m
            for m in client.list_materials_movements(PROJECT, lot=row.lot)
            if m.person == "Ana Ruiz" and m.kind == "issue"
        ]
        expect(bool(issues), f"no issue of {row.lot} to Ana Ruiz is listed")
        expect(
            on_hand_at_crib(client, row.lot) == before - 1, "stock at the crib did not fall by 1"
        )
        expect(line_of(screen).value == "" and app.focused is line_of(screen), "line not cleared")
        passed(f"issue at {size[0]}x{size[1]}: one line posts an issue to Ana Ruiz, stock -1")
        await pilot.press("ctrl+r")
        await settle(pilot)
        await type_into(pilot, f"{row.lot} Ana Ruiz")
        await pilot.press("enter")
        await settle(pilot)
        want = done_text("return", "1", row.uom, row.lot, "Ana Ruiz")
        expect(status_of(screen) == want, f"return status is {status_of(screen)!r}")
        expect(on_hand_at_crib(client, row.lot) == before, "stock at the crib is not back")
        await type_into(pilot, f"{row.lot} Ana Ruiz x99999")
        await pilot.press("enter")
        await settle(pilot)
        refused = status_of(screen)
        expect(refused.startswith("! "), f"no refusal on the status line: {refused!r}")
        expect(refused != want, "the refusal repeated the done text")
        expect(
            line_of(screen).value == f"{row.lot} Ana Ruiz x99999",
            "the line lost what was typed after a refusal",
        )
        expect(on_hand_at_crib(client, row.lot) == before, "a refused return changed stock")
        passed(f"return at {size[0]}x{size[1]}: stock back; over-return refused, line kept")
        screen_svg = app.export_screenshot(title="Toolcrib")
        SHOTS.mkdir(parents=True, exist_ok=True)
        (SHOTS / f"T06-toolcrib-{size[0]}.svg").write_text(screen_svg, encoding="utf-8")
        print(f"  refusal text: {refused}")

    with_screen(size, body)


def check_bad_lines(size: tuple[int, int]) -> None:
    """(3) an unknown tool and an issue without a person are refused, nothing is posted."""

    async def body(
        pilot: Pilot[None], app: TlApp, screen: ToolcribScreen, client: EmbeddedClient
    ) -> None:
        row = pick_lot(client)
        posted = len(client.list_materials_movements(PROJECT))
        await type_into(pilot, "NOPE-TOOL Ana Ruiz")
        await pilot.press("enter")
        await settle(pilot)
        expect(status_of(screen) == "! " + no_such_tool("NOPE-TOOL"), status_of(screen))
        await clear_line(pilot, "NOPE-TOOL Ana Ruiz")  # a refusal keeps the line's text
        await type_into(pilot, row.lot)
        await pilot.press("enter")
        await settle(pilot)
        expect(status_of(screen) == "! " + NEED_PERSON, f"status is {status_of(screen)!r}")
        expect(line_of(screen).value == row.lot, "the line lost what was typed")
        expect(len(client.list_materials_movements(PROJECT)) == posted, "a bad line posted")
        passed(f"bad lines at {size[0]}x{size[1]}: unknown tool and missing person, nothing posted")

    with_screen(size, body)


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    try:
        for size in SIZES:
            check_issue_and_return(size)
            check_bad_lines(size)
            print(f"PASS shots: .accept/shots/T06-toolcrib-{size[0]}.svg written")
    except Failure as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
