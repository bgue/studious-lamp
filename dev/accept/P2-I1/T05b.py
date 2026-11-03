"""Acceptance for P2-I1-T05b: the WBS text (``tl_tui.wbs_text``) and the WBS tree screen
(``tl_tui.widgets.wbs_screen``), on the ``seed_awp`` fake through the Textual pilot. No database,
no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05b.py``. Prints ``PASS <check>`` per check, then
``T05b ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_awp import PROJECT, seed_awp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle, static_of  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_awp.views import WbsCwp, WbsRow  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.layout import plain_lines  # noqa: E402
from tl_tui.wbs_text import (  # noqa: E402
    depth_limited,
    is_leaf,
    unallocated_leaves,
    wbs_cells,
    wbs_page,
)
from tl_tui.widgets.wbs_screen import WbsScreen  # noqa: E402

WIDTHS = (80, 170)


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def by_code(rows: list[WbsRow], code: str) -> WbsRow:
    return next(row for row in rows if row.code == code)


def check_no_textual() -> None:
    code = "import sys; sys.modules['textual'] = None\nimport tl_tui.wbs_text\nprint('imported')"
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    need(done.returncode == 0 and "imported" in done.stdout, f"textual imported: {done.stderr}")
    passed("no textual")


def check_cells(rows: list[WbsRow]) -> None:
    root, piping, electrical = by_code(rows, "1"), by_code(rows, "1.1"), by_code(rows, "1.2")
    need(wbs_cells(root, rows) == ("1", "Plant", "120", "—"), f"root cells {wbs_cells(root, rows)}")
    need(
        wbs_cells(piping, rows) == ("1.1", "  Piping", "80", "1 · 100%"),
        f"leaf with cost codes {wbs_cells(piping, rows)}",
    )
    need(
        wbs_cells(electrical, rows) == ("1.2", "  Electrical", "—", "—"),
        f"empty leaf {wbs_cells(electrical, rows)}",
    )
    deep = piping.model_copy(update={"depth": 2, "code": "1.1.1", "parent_code": "1.1"})
    need(wbs_cells(deep, [*rows, deep])[1] == "    Piping", "two spaces per depth")
    need(is_leaf(piping, rows) and not is_leaf(root, rows), "leaf test on the whole tree")
    passed("cells")


def check_page(rows: list[WbsRow]) -> None:
    electrical = by_code(rows, "1.2")
    lines = plain_lines(wbs_page(electrical, rows), width=80)
    need(
        lines == ["1.2 · Electrical", "Leaf · active", "", "Cost codes", "—", "", "CWPs",
                  "No CWPs allocated"],
        f"leaf page {lines}",
    )  # fmt: skip
    panel = plain_lines(wbs_page(electrical, rows, panel=True), width=80)
    need(panel[2] == "Leaf · 0 CWPs", f"panel summary {panel}")
    root = by_code(rows, "1")
    parent = plain_lines(wbs_page(root, rows, panel=True), width=80)
    need(parent[:3] == ["1 · Plant", "Parent of 2 · active", "Parent 1 · 0 CWPs · 120 h"],
         f"parent page {parent[:3]}")  # fmt: skip
    need(any("4210" in line and "100%" in line for line in parent), f"cost code table {parent}")
    piping = by_code(rows, "1.1").model_copy(
        update={
            "cwps": [
                WbsCwp(
                    number="P123-CWP-0001",
                    title="Piping spool set",
                    percent=Decimal("100"),
                    hours=Decimal("40"),
                )
            ],
            "cwp_count": 1,
        }
    )
    lines = plain_lines(wbs_page(piping, [*rows, piping]), width=80)
    need("No CWPs allocated" not in lines, "CWP table was not shown")
    need(any("P123-CWP-0001" in line and "40" in line for line in lines), f"CWP table {lines}")
    passed("page")


def check_helpers(rows: list[WbsRow]) -> None:
    need(len(depth_limited(rows, 1)) == 1, "depth 1 keeps the top node only")
    need(len(depth_limited(rows, 2)) == 3, "depth 2 keeps every node of the seed")
    need([row.code for row in unallocated_leaves(rows)] == ["1.2"], "only 1.2 is unallocated")


def open_screen(
    client: FakeClient,
    size: tuple[int, int],
    steps: Callable[[Any, WbsScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = WbsScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, WbsScreen), "the WBS screen did not open")
        await steps(pilot, screen)

    run_pilot(app, go, size=size)


def check_depth_and_unallocated(client: FakeClient) -> None:
    reads: list[str] = []
    read_tree = client.wbs_tree

    def counted(project: str, *, depth: int | None = None) -> list[WbsRow]:
        reads.append(project)
        return read_tree(project, depth=depth)

    client.wbs_tree = counted  # type: ignore[method-assign]

    async def steps(pilot: Any, screen: WbsScreen) -> None:
        need(len(screen.shown) == 3, f"all three nodes at first: {len(screen.shown)}")
        await pilot.press("1")
        await settle(pilot)
        need(len(screen.shown) == 1, f"depth 1 shows {len(screen.shown)} rows")
        await pilot.press("0")
        await settle(pilot)
        need(len(screen.shown) == 3, "0 shows every depth again")
        await pilot.press("u")
        await settle(pilot)
        need([row.code for row in screen.shown] == ["1.2"], "u keeps the unallocated leaf")
        await pilot.press("u")
        await settle(pilot)
        need(len(screen.shown) == 3, "u again shows every node")
        need(len(reads) == 1, f"the tree is read once, read {len(reads)} times")

    open_screen(client, (120, 40), steps)
    passed("depth")
    passed("unallocated")


def check_mount(client: FakeClient, width: int) -> None:
    async def steps(pilot: Any, screen: WbsScreen) -> None:
        lines = screen_text(pilot.app).splitlines()
        too_wide = [line for line in lines if len(line) > width]
        need(not too_wide, f"lines wider than {width}: {too_wide[:1]}")
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row with Number and Subject")
        need(header.index("Subject") < header.index("Budget h"), "Subject starts after column 3")
        need("Piping" in "\n".join(lines), "no subject shown")
        if width >= 170:
            panel = panel_of(screen)
            need("1 · Plant" in panel and "Parent of 2 · active" in panel, f"panel {panel!r}")
            need("Parent 1 · 0 CWPs · 120 h" in panel, "panel summary is missing")
            await pilot.press("down")
            await pilot.press("down")
            await settle(pilot)
            panel = panel_of(screen)
            need("1.2 · Electrical" in panel and "Leaf · active" in panel, f"leaf panel {panel!r}")
            need("Leaf · 0 CWPs" in panel, "leaf summary is missing")

    open_screen(client, (width, 40), steps)
    passed(f"mount {width}")


def check_missing() -> None:
    client = FakeClient()
    seed_awp(client)

    def gone(project: str, code: str) -> None:
        raise RecordNotFoundError(f"no WBS node {code!r}")

    client.get_wbs_node = gone  # type: ignore[method-assign]

    async def steps(pilot: Any, screen: WbsScreen) -> None:
        await pilot.press("down")  # highlight 1.1: the panel asks for it and is refused
        await settle(pilot)
        status = static_of(screen, "#log-status")
        need("no WBS node" in status, f"no status line: {status!r}")
        need("1.1 · Piping" in panel_of(screen), "the panel should keep the listing's copy")

    open_screen(client, (120, 40), steps)
    passed("missing")


def main() -> int:
    client = FakeClient()
    seed_awp(client)
    rows = client.wbs_tree(PROJECT)
    try:
        check_no_textual()
        check_cells(rows)
        check_page(rows)
        check_helpers(rows)
        check_depth_and_unallocated(seeded_client())
        for width in WIDTHS:
            check_mount(seeded_client(), width)
        check_missing()
    except Failed as exc:
        print(f"FAIL {exc}")
        return 1
    print("T05b ok")
    return 0


def seeded_client() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    return client


if __name__ == "__main__":
    sys.exit(main())
