"""Acceptance for P2-I2-T08: the backlog weeks per foreman and the sizing list (pure functions and
the Textual screen on ``FakeClient`` + ``seed_iwp``). No pytest, no network.

Prints ``PASS <check>`` per check, then ``T08 ok``. Exits 1 on the first failure.
Run: ``uv run python dev/accept/P2-I2/T08.py``.
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-tui/tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_iwp import PROJECT, seed_iwp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable  # noqa: E402
from tl_mod_awp.iwp_views import IwpRow  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.backlog_text import (  # noqa: E402
    BACKLOG_COLUMNS,
    SIZING_COLUMNS,
    backlog_cells,
    backlog_rows,
    backlog_summary,
    iwp_weeks,
    size_flag,
    sizing_cells,
    sizing_rows,
)
from tl_tui.widgets.backlog_screen import BacklogScreen  # noqa: E402

HEX32 = re.compile(r"[0-9a-f]{32}")
LOW, HIGH = Decimal("60"), Decimal("850")
TARGET = 4


def iwp_row(
    number: str,
    state: str,
    foreman: str | None,
    start: str | None,
    finish: str | None,
    *,
    hours: str | None = None,
) -> IwpRow:
    """A hand-made ``IwpRow`` for the pure checks."""
    return IwpRow(
        id=f"IWP-{number}",
        number=f"P123-IWP-{number}",
        title=f"Package {number}",
        state=state,
        discipline="PIP",
        planned_start=start,
        planned_finish=finish,
        foreman=foreman,
        estimated_hours=None if hours is None else Decimal(hours),
    )


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"FAIL {name} {detail}".rstrip())
        sys.exit(1)
    print(f"PASS {name}")


def check_weeks() -> None:
    got = [
        iwp_weeks("2026-12-01", "2026-12-01"),
        iwp_weeks("2026-12-01", "2026-12-14"),
        iwp_weeks("2026-12-01", "2026-12-15"),
        iwp_weeks(None, "2026-12-15"),
    ]
    check("weeks", got == [1, 2, 3, 0], f"got {got}")


def check_backlog() -> None:
    rows = [
        iwp_row("A", "Ready", "user:uma", "2026-12-01", "2026-12-15"),  # 3 weeks
        iwp_row("B", "Issued", "user:uma", "2026-12-01", "2026-12-07"),  # 1 week
        iwp_row("C", "Ready", "user:sue", None, None),  # undated, 0 weeks
        iwp_row("D", "Ready", None, "2026-12-01", "2026-12-08"),  # 2 weeks, no foreman
        iwp_row("E", "Draft", "user:sue", "2026-12-01", "2026-12-31"),  # ignored
    ]
    found = backlog_rows(rows, TARGET)
    cells = [backlog_cells(r) for r in found]
    want = [
        ("sue", "1", "0", "4", "below target", "1"),
        ("uma", "2", "4", "4", "at or above target", "0"),
        ("-", "1", "2", "4", "below target", "0"),
    ]
    check("backlog", cells == want, f"got {cells}")
    check(
        "backlog summary",
        backlog_summary(rows, TARGET) == "3 foremen, 2 below the 4-week target",
        backlog_summary(rows, TARGET),
    )


def check_sizing() -> None:
    hours: list[Decimal | None] = [
        None,
        Decimal("59"),
        Decimal("60"),
        Decimal("850"),
        Decimal("851"),
    ]
    flags = [size_flag(h, LOW, HIGH) for h in hours]
    want = ["", "undersize", "", "", "oversize"]
    check("sizing", flags == want, f"got {flags}")
    rows = [
        iwp_row(f"{n}", "Ready", None, None, None, hours=str(h)) for n, h in enumerate(hours[1:])
    ]
    flagged = sizing_rows(rows, LOW, HIGH)
    check("sizing rows", [r.flag for r in flagged] == ["undersize", "oversize"])
    check(
        "sizing cells",
        sizing_cells(flagged[1])[-1] == "over size"
        and sizing_cells(flagged[0])[-1] == "under size",
    )


def run_screen(width: int, height: int, steps: Any = None) -> tuple[TlApp, BacklogScreen, Any]:
    client = FakeClient()
    seed_iwp(client)
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    found: list[BacklogScreen] = []

    async def go(pilot: Pilot[None]) -> None:
        screen = BacklogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        found.append(screen)
        if steps is not None:
            await steps(pilot, app, screen)

    run_pilot(app, go, size=(width, height))
    return app, found[0], client


def capture(width: int, height: int) -> tuple[str, str]:
    """The screen text and the panel text, read while the pilot runs."""
    got: dict[str, str] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: BacklogScreen) -> None:
        got["text"] = screen_text(app)
        got["panel"] = panel_of(screen)

    run_screen(width, height, steps)
    return got["text"], got["panel"]


def check_mount(width: int, height: int) -> None:
    text, panel = capture(width, height)
    lines = text.splitlines()
    overflow = [line for line in lines if len(line) > width]
    check(f"mount {width}", not overflow and len(lines) > 0, f"overflow {overflow[:1]}")
    if width >= 170:
        check(
            "panel 170",
            "Backlog weeks per foreman" in panel and "below the 4-week target" in panel,
            panel,
        )


def check_keys() -> None:
    columns: list[list[str]] = []

    async def steps(pilot: Pilot[None], app: TlApp, screen: BacklogScreen) -> None:
        table = screen.query_one("#log-table", DataTable)
        columns.append([str(c.label) for c in table.columns.values()])
        await pilot.press("z")
        await settle(pilot)
        columns.append([str(c.label) for c in table.columns.values()])
        await pilot.press("b")
        await settle(pilot)
        columns.append([str(c.label) for c in table.columns.values()])

    run_screen(120, 40, steps)
    check(
        "keys",
        columns[0] == list(BACKLOG_COLUMNS)
        and columns[1] == list(SIZING_COLUMNS)
        and columns[2] == list(BACKLOG_COLUMNS),
        f"got {columns}",
    )


def check_words() -> None:
    text, _ = capture(170, 40)
    bad = [line for line in text.splitlines() if HEX32.search(line)]
    check("words", not bad, f"found {bad[:1]}")


def main() -> None:
    check_weeks()
    check_backlog()
    check_sizing()
    check_mount(80, 30)
    check_mount(170, 40)
    check_keys()
    check_words()
    print("T08 ok")


if __name__ == "__main__":
    main()
