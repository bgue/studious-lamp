"""Acceptance for P2-I2-T07a: the readiness screen (``tl_tui.widgets.readiness_screen``) on the
``FakeClient`` with ``seed_iwp``, through the Textual pilot as ``tests/helpers.py`` does. No
database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I2/T07a.py``. Prints ``PASS <check>`` per check, then
``T07a ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_iwp import PROJECT, seed_iwp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable, Static  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.readiness_text import not_evaluated_text  # noqa: E402
from tl_tui.widgets.readiness_screen import ReadinessScreen  # noqa: E402

NUMBER = f"{PROJECT}-IWP-PIP-0001"
REF_ID = "DOC-2"
HEIGHT = 44
ACTOR = "user:kim"
Step = Callable[[Pilot[None], TlApp, ReadinessScreen], Awaitable[None]]


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def seeded() -> FakeClient:
    client = FakeClient()
    seed_iwp(client)
    return client


def run(client: FakeClient, width: int, steps: Step | None = None) -> tuple[TlApp, ReadinessScreen]:
    """Mount the screen on ``client`` at ``width`` columns; ``steps`` runs in the pilot."""
    app = TlApp(client, scope=SCOPE, actor=ACTOR)
    found: list[ReadinessScreen] = []

    async def go(pilot: Pilot[None]) -> None:
        screen = ReadinessScreen(client, PROJECT, NUMBER)
        app.push_screen(screen)
        await settle(pilot)
        found.append(screen)
        if steps is not None:
            await steps(pilot, app, screen)

    run_pilot(app, go, size=(width, HEIGHT))
    return app, found[0]


def table_of(screen: ReadinessScreen) -> DataTable[Any]:
    return screen.query_one("#log-table", DataTable)


def cells_of(screen: ReadinessScreen) -> list[list[str]]:
    table = table_of(screen)
    return [[str(cell) for cell in table.get_row_at(i)] for i in range(table.row_count)]


def status(screen: ReadinessScreen) -> str:
    return str(screen.query_one("#log-status", Static).render())


def check_mount(width: int) -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ReadinessScreen) -> None:
        seen["text"] = screen_text(app)
        seen["panel"] = panel_of(screen)

    run(seeded(), width, steps)
    lines = str(seen["text"]).splitlines()
    widest = max((len(line) for line in lines), default=0)
    print(f"-- width {width}")
    print("\n".join(lines[:8]))
    need(widest <= width, f"a line is {widest} columns wide at {width}")
    header = next((line for line in lines if "Check" in line and "State" in line), "")
    need(header != "", "no header row with Check and State")
    need(header.index("Check") < header.index("State"), "Check is not left of State")
    if width >= 160:
        panel = str(seen["panel"])
        print(panel)
        need(f"{NUMBER} · readiness" in panel, "panel has no heading")
        need("Not ready" in panel, "panel has no state")
        need("7/9 passing" in panel, "panel has no summary")
    passed(f"mount {width}")


def check_counts() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ReadinessScreen) -> None:
        seen["status"] = status(screen)
        seen["cells"] = cells_of(screen)

    run(seeded(), 170, steps)
    need(
        "7/9 passing (2 ok, 5 n/a, 2 blocked)" in str(seen["status"]),
        f"summary is {seen['status']!r}",
    )
    states = [row[1] for row in seen["cells"]]
    need(states.count("n/a") == 5, f"n/a rows: {states}")
    need("n_a" not in states, "a state reads n_a, not n/a")
    passed("counts")


def check_refs() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ReadinessScreen) -> None:
        index = next(i for i, row in enumerate(screen.shown) if row.record_id == REF_ID)
        seen["row"] = cells_of(screen)[index]
        table_of(screen).move_cursor(row=index)
        await settle(pilot)
        with mock.patch("tl_tui.widgets.readiness_screen.open_record") as opened:
            await pilot.press("enter")
            await settle(pilot)
            seen["calls"] = list(opened.call_args_list)

    run(seeded(), 170, steps)
    need("P123-DWG-0002" in str(seen["row"][3]), f"the ref row is {seen['row']!r}")
    calls = seen["calls"]
    need(len(calls) == 1, f"open_record called {len(calls)} times")
    args = calls[0].args
    need(args[-1] == REF_ID, f"open_record got {args[-1]!r}, not {REF_ID!r}")
    passed("refs")


def check_none() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ReadinessScreen) -> None:
        seen["status"] = status(screen)
        seen["panel"] = panel_of(screen)
        seen["rows"] = table_of(screen).row_count

    run(FakeClient(), 170, steps)
    text = not_evaluated_text(NUMBER)
    need(text == f"{NUMBER} has not been evaluated", "the one text changed")
    need(text in str(seen["status"]), f"status is {seen['status']!r}")
    need(text in str(seen["panel"]), "the panel does not show the text")
    need(seen["rows"] == 0, "a missing readiness has rows")
    passed("none")


def check_words() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ReadinessScreen) -> None:
        seen["text"] = screen_text(app)

    run(seeded(), 170, steps)
    for line in str(seen["text"]).splitlines():
        need(re.search(r"[0-9a-f]{32}", line) is None, f"a 32-hex id: {line!r}")
        need("facts_hash" not in line, f"facts_hash: {line!r}")
    passed("words")


def main() -> None:
    check_mount(80)
    check_mount(170)
    check_counts()
    check_refs()
    check_none()
    check_words()
    print("T07a ok")


if __name__ == "__main__":
    try:
        main()
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
