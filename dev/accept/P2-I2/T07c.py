"""Acceptance for P2-I2-T07c: the IWP screen keys reach readiness and the constraint log, and the
palette lists the IWP log, the constraint log and the backlog (P2-I2 T07c).

The fake is ``FakeClient`` with ``seed_iwp``; the IWP screen is opened for PIP-0001 (the IWP with
the readiness and the three constraints), mounted in a Textual pilot. No network, no pytest.

Prints ``PASS keys``, ``PASS readiness``, ``PASS back``, ``PASS constraints``, ``PASS palette``,
then ``T07c ok``. Exits 1 on the first failure.

Run: ``uv run python dev/accept/P2-I2/T07c.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-tui/tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_iwp import PROJECT, seed_iwp  # noqa: E402
from helpers import run_pilot, screen_text, settle  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.widgets.constraint_screen import ConstraintScreen  # noqa: E402
from tl_tui.widgets.iwp_register import IwpScreen  # noqa: E402
from tl_tui.widgets.readiness_screen import ReadinessScreen  # noqa: E402

HEIGHT = 44
WIDTH = 170
PIP1 = f"{PROJECT}-IWP-PIP-0001"  # scope by type, 3 constraints, readiness of 9 checks
SIGNED_IN = "user:sue"
CHECK_NAMES = ("constraints_cleared", "documents_current", "crew_assigned")
PALETTE_IDS = ("iwps", "constraints", "backlog")


def need(cond: bool, name: str) -> None:
    if not cond:
        print(f"FAIL {name}", flush=True)
        sys.exit(1)


def words(text: str) -> str:
    """The text with lower case words joined by ``_``, so ``Constraints cleared`` matches the id."""
    return re.sub(r"\s+", "_", text.lower())


def rows_of(screen: Any) -> list[list[str]]:
    table = screen.query_one("#log-table", DataTable)
    return [[str(cell) for cell in table.get_row_at(i)] for i in range(table.row_count)]


def run(steps: Any, *, open_iwp: bool = True) -> None:
    """Mount the app on the seeded fake; with ``open_iwp`` the IWP screen of PIP-0001 is on top."""
    client = FakeClient()
    seed_iwp(client)
    app = TlApp(client, scope=SCOPE, actor=SIGNED_IN)

    async def go(pilot: Pilot[None]) -> None:
        if open_iwp:
            app.push_screen(IwpScreen(client, PROJECT, PIP1))
            await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=(WIDTH, HEIGHT))


def check_keys() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        seen["iwp"] = app.screen
        await pilot.press("r")
        await settle(pilot)
        seen["readiness"] = app.screen
        seen["ready_text"] = screen_text(app)
        await pilot.press("escape")
        await settle(pilot)
        seen["back"] = app.screen
        await pilot.press("c")
        await settle(pilot)
        seen["constraints"] = app.screen
        seen["con_rows"] = rows_of(app.screen)
        seen["con_text"] = screen_text(app)
        await pilot.press("escape")
        await settle(pilot)

    run(steps)
    need(isinstance(seen["iwp"], IwpScreen), "keys IwpScreen opened")
    print("PASS keys", flush=True)

    need(isinstance(seen["readiness"], ReadinessScreen), "readiness r pushes ReadinessScreen")
    need(seen["readiness"].number == PIP1, "readiness names the IWP")
    ready = words(str(seen["ready_text"]))
    for name in CHECK_NAMES:
        need(name in ready, f"readiness shows check {name}")
    print("PASS readiness", flush=True)

    need(isinstance(seen["back"], IwpScreen), "escape returns to IwpScreen")
    print("PASS back", flush=True)

    need(isinstance(seen["constraints"], ConstraintScreen), "c pushes ConstraintScreen")
    need(seen["constraints"].subject_key == PIP1, "constraint log filtered to the IWP")
    rows = seen["con_rows"]
    need(len(rows) == 3, f"constraint log has the IWP's 3 constraints, got {len(rows)}")
    need(f"Constraints on {PIP1}" in str(seen["con_text"]), "constraint log names the IWP")
    print("PASS constraints", flush=True)


def check_palette() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        app.action_palette()
        await settle(pilot)
        palette: Any = app.screen
        seen["ids"] = [
            row.choice.command_id
            for row in palette.rows
            if row.choice is not None and row.choice.command_id is not None
        ]
        await pilot.press("escape")
        await settle(pilot)

    run(steps, open_iwp=False)  # the palette opens from the app, not over a modal
    ids = seen["ids"]
    for cid in PALETTE_IDS:
        need(cid in ids, f"palette lists {cid}")
    print("PASS palette", flush=True)


def main() -> None:
    check_keys()
    check_palette()
    print("T07c ok", flush=True)


if __name__ == "__main__":
    main()
