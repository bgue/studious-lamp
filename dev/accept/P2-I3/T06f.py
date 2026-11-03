"""Acceptance for P2-I3-T06f: the stock log and the movement log screens on ``TlApp``.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory and
reads it through ``EmbeddedClient``. At 80x30 and 170x40 it pushes ``StockScreen`` and checks the
keys, the lot filter, the lot panel and the screenshot; then ``MovementLogScreen`` (rows, the kind
and period keys, the panel, the screenshot). A ``FakeClient`` with no stock gives an empty stock
log. Prints ``PASS <check>`` for each check and exits 0; on the first failure prints
``FAIL <check>: <detail>`` and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T06f.py
"""

import asyncio
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
SIZES = ((80, 30), (170, 40))
sys.path[:0] = [str(ROOT / "packages/tl-api/tests"), str(ROOT / "packages/tl-tui/tests")]
os.environ.setdefault("TL_ENV", "dev")  # the harness's dev token file is honoured in dev (as T04b)

from fakes import FakeClient  # noqa: E402
from harness import ALICE  # noqa: E402
from helpers import panel_of, screen_text, settle, static_of  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.materials_text import KIND_WORDS  # noqa: E402
from tl_tui.widgets.movement_screen import MovementLogScreen  # noqa: E402
from tl_tui.widgets.stock_screen import StockScreen  # noqa: E402

Scenario = Callable[[Any, TlApp], Coroutine[Any, Any, None]]


def check(ok: bool, name: str, detail: str = "") -> None:
    """Raise on a failed check (the first failure ends the run); print ``PASS`` otherwise."""
    if not ok:
        raise AssertionError(f"{name}: {detail}")
    print(f"PASS {name}")


def run_at(size: tuple[int, int], client: Any, scenario: Scenario) -> None:
    """Run ``scenario(pilot, app)`` on a ``TlApp`` headless at ``size``."""

    async def main() -> None:
        app = TlApp(client, scope=f"project:{PROJECT}", actor=ALICE, is_admin=False)
        async with app.run_test(size=size) as pilot:
            await settle(pilot)
            await scenario(pilot, app)

    asyncio.run(main())


def save_shot(app: TlApp, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    (SHOTS / name).write_text(app.export_screenshot(title=name.split("-")[1].capitalize()))


def stock_at(size: tuple[int, int], client: EmbeddedClient, rows: list[Any]) -> None:
    """The stock log at one size: the keys, the lot filter and its panel, the screenshot."""
    w = size[0]
    first = rows[0]
    first_text = str(first.heat_no or first.lot)

    async def scenario(pilot: Any, app: TlApp) -> None:
        app.push_screen(StockScreen(client, PROJECT))
        await settle(pilot)
        screen = app.screen
        check(isinstance(screen, StockScreen), f"stock {w}: top screen", type(screen).__name__)
        text = screen_text(app)
        check("l lot" in text, f"stock {w}: keys row", "no 'l lot' on the screen")
        check(first_text in text, f"stock {w}: a heat or lot number", first_text)
        total = len(screen.rows)
        await pilot.press("l")
        await settle(pilot)
        status = static_of(screen, "#log-status")
        check(screen.lot == first.lot, f"stock {w}: l sets the lot", str(screen.lot))
        check(f"lot {first.lot}" in status, f"stock {w}: summary names the lot", status)
        await pilot.press("l")
        await settle(pilot)
        status = static_of(screen, "#log-status")
        check(screen.lot is None, f"stock {w}: l again clears the lot", str(screen.lot))
        check(
            "lot " not in status and len(screen.rows) == total,
            f"stock {w}: lot filter gone",
            status,
        )
        await pilot.press("down")
        await settle(pilot)
        panel = panel_of(screen)
        check("Quantities" in panel, f"stock {w}: panel has Quantities", panel[:200])
        check("Traceability" in panel, f"stock {w}: panel has Traceability", panel[:200])
        save_shot(app, f"T06f-stock-{w}.svg")
        print(f"PASS stock {w}: screenshot saved")
        await pilot.press("escape")
        await settle(pilot)
        check(not isinstance(app.screen, StockScreen), f"stock {w}: Esc closes", "")

    run_at(size, client, scenario)


def movements_at(size: tuple[int, int], client: EmbeddedClient) -> None:
    """The movement log at one size: the rows, the kind and period keys, the panel, a screenshot."""
    w = size[0]

    async def scenario(pilot: Any, app: TlApp) -> None:
        app.push_screen(MovementLogScreen(client, PROJECT))
        await settle(pilot)
        screen = app.screen
        check(isinstance(screen, MovementLogScreen), f"movements {w}: top screen", "")
        check(len(screen.shown) > 0, f"movements {w}: rows present", str(len(screen.shown)))
        check("Qty" in panel_of(screen), f"movements {w}: panel has Qty", "")
        save_shot(app, f"T06f-movements-{w}.svg")
        await pilot.press("k")
        await settle(pilot)
        status = static_of(screen, "#log-status")
        check(screen.kind is not None, f"movements {w}: k sets a kind", str(screen.kind))
        word = KIND_WORDS.get(str(screen.kind), str(screen.kind))
        check(word in status, f"movements {w}: summary names the kind", status)
        await pilot.press("p")
        await settle(pilot)
        status = static_of(screen, "#log-status")
        check("last 7 days" in status, f"movements {w}: p sets last 7 days", status)
        await pilot.press("escape")
        await settle(pilot)
        check(not isinstance(app.screen, MovementLogScreen), f"movements {w}: Esc closes", "")

    run_at(size, client, scenario)


def empty_stock_at(size: tuple[int, int]) -> None:
    """A stock log with no rows: the panel says so, no ``None`` and no bare ``-`` on the screen."""
    w = size[0]
    fake = FakeClient()
    fake.put_materials(PROJECT, stock=[])

    async def scenario(pilot: Any, app: TlApp) -> None:
        app.push_screen(StockScreen(fake, PROJECT))
        await settle(pilot)
        screen = app.screen
        check(isinstance(screen, StockScreen), f"empty stock {w}: top screen", "")
        check(len(screen.rows) == 0, f"empty stock {w}: no rows", str(len(screen.rows)))
        check("No stock on hand" in panel_of(screen), f"empty stock {w}: panel says so", "")
        text = screen_text(app)
        check(re.search(r"\bNone\b", text) is None, f"empty stock {w}: no None", "")
        check(re.search(r"(?<!\S)-(?!\S)", text) is None, f"empty stock {w}: no bare dash", "")
        await pilot.press("escape")
        await settle(pilot)
        check(not isinstance(app.screen, StockScreen), f"empty stock {w}: Esc closes", "")

    run_at(size, fake, scenario)


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, Path(tmp) / ("tl.db" + src.name[len(LEDGER.name) :]))
        client = EmbeddedClient(SqliteUowFactory(db), actor=ALICE)
        rows = client.list_materials_stock(PROJECT, limit=1000)
        if not rows:
            print("FAIL seed: the seed ledger has no stock rows for P123")
            return 1
        try:
            for size in SIZES:
                stock_at(size, client, rows)
                movements_at(size, client)
            for size in SIZES:
                empty_stock_at(size)
        except AssertionError as exc:
            print(f"FAIL {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
