"""The wave 1 tour: the M3 and M4 terminal screens on the full demo project P200.

    uv run python dev/tour/wave1.py [--out docs/reports/tour/wave1]
    just tour wave1 [/tmp/wave1-tour]

Same method as `highlights.py` (see `tourkit.py`): a fresh SQLite ledger in a temporary directory,
the real TUI driven headless, the frozen clock, and the leak check on every plain screenshot. The
project is built once by the demo project generator (`seed_demo_project`); no `tl init --dev`, no
network, no Postgres. It writes seven SVGs:

    01-wbs         the WBS tree (4 to 5 levels)              user:lhartmann
    02-cwp         the CWP register (40+ rows), filter used  user:lhartmann
    03-path        the path of construction, v1 and v2       user:lhartmann
    04-receipts    the receipt log (rows without an MTR)     user:treyes
    05-stock       the stock                                 user:treyes
    06-takeoff     the take-off (MTO) lines, some short      user:treyes
    07-movements   the movement log                          user:treyes
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:  # `dev` is not an installed package
    sys.path.append(str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

import tourkit as tk  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from tl_adapters.db import as_target  # noqa: E402
from tourkit import Workspace  # noqa: E402

from dev.seed.demo_project import overlay  # noqa: E402
from dev.seed.demo_project.__main__ import run  # noqa: E402
from dev.seed.demo_project.world import PROJECT_ID as PROJECT  # noqa: E402

DEFAULT_OUT = REPO / "docs/reports/tour/wave1"
TODAY = datetime(2026, 11, 6, 9, 0, 0, tzinfo=UTC)  # the project calendar's "today"
LEAD = "treyes"  # materials
AWP = "lhartmann"  # awp (work packages, WBS, path)


def seed_demo_project(ws: Workspace) -> None:
    """The one place a tour or demo gets the project: build P200 in the workspace's ledger."""
    run(as_target(str(ws.db)), objects=ws.root / "objects")
    os.environ["TL_SCHEMA_DIR"] = str(overlay.OVERLAY)  # the clients read the project's types


async def _open(pilot: Pilot[Any], app: Any, make: Callable[[Any], Any], what: str) -> None:
    """Wait for the shell, push the screen on the app's client and wait for its rows."""
    await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
    app.push_screen(make(app.client))
    await tk.until(pilot, lambda: len(app.screen.rows) > 0, what)
    await tk.settle(pilot, 3)


def scenario(
    ws: Workspace,
    name: str,
    title: str,
    actor: str,
    make: Callable[[Any], Any],
    what: str,
    *needles: str,
) -> None:
    """One screen of the tour: open it as ``actor`` and save the shot once ``needles`` show."""
    from tl_tui.main import build_app

    app = build_app(ws.db, PROJECT, live=False, actor=actor)

    async def run_it(pilot: Pilot[Any]) -> None:
        await _open(pilot, app, make, what)
        tk.shot_tui(ws, app, name, title, *needles)

    tk.run_tui(ws, app, run_it)


def shots(ws: Workspace) -> None:
    from tl_tui.widgets.cwp_register import CwpRegisterScreen
    from tl_tui.widgets.movement_screen import MovementLogScreen
    from tl_tui.widgets.mto_screen import MtoLinesScreen
    from tl_tui.widgets.path_screen import PathScreen
    from tl_tui.widgets.receipt_log import ReceiptLogScreen
    from tl_tui.widgets.stock_screen import StockScreen
    from tl_tui.widgets.wbs_screen import WbsScreen

    scenario(
        ws,
        "01-wbs",
        "The WBS tree of P200, five levels deep",
        AWP,
        lambda c: WbsScreen(c, PROJECT),
        "the WBS tree",
        "P200.100.CIV.01.01",
    )
    scenario(
        ws,
        "02-cwp",
        "The CWP register of P200: the work packages, 40 and more rows",
        AWP,
        lambda c: CwpRegisterScreen(c, PROJECT),
        "the CWPs",
        "P200-CWP-",
    )
    scenario(
        ws,
        "03-path",
        "The path of construction of P200: its work areas in order",
        AWP,
        lambda c: PathScreen(c, PROJECT),
        "the path",
        "CWA-100-01",
        "CWA-300-02",
    )
    scenario(
        ws,
        "04-receipts",
        "The receipt log: receipts, the rows without an MTR show n/a",
        LEAD,
        lambda c: ReceiptLogScreen(c, PROJECT),
        "the receipts",
        "P200-RCPT-0001",
        "n/a",
    )
    scenario(
        ws,
        "05-stock",
        "The stock of P200 by lot and location",
        LEAD,
        lambda c: StockScreen(c, PROJECT),
        "the stock",
        "HT5744-1",
    )
    scenario(
        ws,
        "06-takeoff",
        "The take-off lines of P200 with their required and short quantities",
        LEAD,
        lambda c: MtoLinesScreen(c, PROJECT),
        "the take-off lines",
        "P200-CWP-",
    )
    scenario(
        ws,
        "07-movements",
        "The movement log of P200, by lot",
        LEAD,
        lambda c: MovementLogScreen(c, PROJECT),
        "the movements",
        "BLT-STUD-1X95",
        "Receipt",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The wave 1 tour: M3 and M4 screens on P200.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    ws = Workspace(out)
    try:
        print("building the project P200 with the generator", flush=True)
        seed_demo_project(ws)
        tk.freeze()
        tk.CLOCK.now = TODAY  # the calendar's today; the frozen clock is otherwise 2026-10-12
        print("the shots", flush=True)
        shots(ws)
    except tk.TourFailed as exc:
        print(f"TourFailed: {exc}", file=sys.stderr)
        return 1
    finally:
        ws.close()
    print(f"wrote {len(ws.written)} screenshots to {out}")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
