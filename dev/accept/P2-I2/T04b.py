"""Acceptance for P2-I2-T04b: the constraint review screen (``tl_tui.widgets.constraint_screen``)
on the ``FakeClient`` with ``seed_iwp``, through the Textual pilot as ``tests/helpers.py`` does. No
database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I2/T04b.py``. Prints ``PASS <check>`` per check, then
``T04b ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import replace
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
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.constraint_text import order_by_group  # noqa: E402
from tl_tui.widgets.constraint_screen import ConstraintScreen  # noqa: E402

MOUNT_WIDTHS = (80, 170)
HEIGHT = 44
HEX32 = re.compile(r"[0-9a-f]{32}")
Step = Callable[[Pilot[None], TlApp, ConstraintScreen], Awaitable[None]]


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


def run(
    client: FakeClient,
    width: int,
    subject: str | None = None,
    steps: Step | None = None,
) -> tuple[TlApp, ConstraintScreen]:
    """Mount the review on ``client`` at ``width`` columns; ``steps`` runs in the pilot."""
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    found: list[ConstraintScreen] = []

    async def go(pilot: Pilot[None]) -> None:
        screen = ConstraintScreen(client, PROJECT, subject_key=subject)
        app.push_screen(screen)
        await settle(pilot)
        found.append(screen)
        if steps is not None:
            await steps(pilot, app, screen)

    run_pilot(app, go, size=(width, HEIGHT))
    return app, found[0]


def keys_of(screen: ConstraintScreen) -> list[str]:
    return [row.key for row in screen.shown]


def row_count(screen: ConstraintScreen) -> int:
    return screen.query_one("#log-table", DataTable).row_count


def status(screen: ConstraintScreen) -> str:
    return str(screen.query_one("#log-status", Static).render())


def check_mount(width: int) -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ConstraintScreen) -> None:
        seen["text"] = screen_text(app)
        seen["rows"] = row_count(screen)
        seen["panel"] = panel_of(screen)

    run(seeded(), width, steps=steps)
    lines = str(seen["text"]).splitlines()
    widest = max((len(line) for line in lines), default=0)
    print(f"-- width {width}")
    print("\n".join(lines[:8]))
    need(widest <= width, f"a line is {widest} columns wide at {width}")
    need(seen["rows"] == 5, f"the seed has 5 constraints, the list has {seen['rows']}")
    header = next((line for line in lines if "Constraint" in line and "State" in line), "")
    need(header != "", "no header row with Constraint and State")
    need(header.index("Subject") < header.index("Type"), "Subject is right of the third column")
    if width >= 160:
        panel = str(seen["panel"])
        print(panel)
        panel_lines = [line.strip() for line in panel.splitlines() if line.strip()]
        need(
            panel_lines[0] == f"{PROJECT}-CON-0001 · {PROJECT}-IWP-PIP-0001",
            f"panel has no heading: {panel_lines[:1]}",
        )
        need(panel_lines[1] == "Open", f"panel has no state: {panel_lines[1:2]}")
        need(" · " in panel_lines[2], f"panel has no summary line: {panel_lines[2:3]}")
    passed(f"mount {width}")


def check_keys() -> None:
    def steps(pilot: Pilot[None], app: TlApp, screen: ConstraintScreen) -> Awaitable[None]:
        async def run_keys() -> None:
            need(len(keys_of(screen)) == 5, "start: 5 rows")
            await pilot.press("o")
            await settle(pilot)
            want = [row.key for row in order_by_group(screen.views, "owner")]
            need(keys_of(screen) == want, f"o: order {keys_of(screen)} != {want}")
            await pilot.press("o")
            await settle(pilot)
            need(keys_of(screen) == [row.key for row in screen.views], "o again: key order")
            await pilot.press("t")
            await settle(pilot)
            want = [row.key for row in order_by_group(screen.views, "category")]
            need(keys_of(screen) == want, f"t: order {keys_of(screen)} != {want}")
            await pilot.press("a")
            await settle(pilot)
            want = [row.key for row in order_by_group(screen.views, "age")]
            need(keys_of(screen) == want, f"a: order {keys_of(screen)} != {want}")
            await pilot.press("a")
            await settle(pilot)
            await pilot.press("b")
            await settle(pilot)
            need(keys_of(screen) == [f"{PROJECT}-CON-0001"], f"b: {keys_of(screen)}")
            await pilot.press("b")
            await settle(pilot)
            need(len(keys_of(screen)) == 5, "b again: all rows")
            await pilot.press("s")
            await settle(pilot)
            need(len(keys_of(screen)) == 1, f"s (first state): {len(keys_of(screen))} rows")
            await pilot.press("s")
            await settle(pilot)
            need(len(keys_of(screen)) == 4, f"s (second state): {len(keys_of(screen))} rows")
            await pilot.press("s")
            await settle(pilot)
            need(len(keys_of(screen)) == 5, "s (all again) must show 5 rows")

        return run_keys()

    run(seeded(), 170, steps=steps)
    passed("keys")


def check_subject() -> None:
    client = seeded()
    subject = f"{PROJECT}-IWP-PIP-0001"  # the first IWP carries the seed constraints
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ConstraintScreen) -> None:
        seen["shown"] = list(screen.shown)
        seen["status"] = status(screen)

    run(client, 170, subject=subject, steps=steps)
    shown = seen["shown"]
    need(len(shown) == 3, f"subject rows: {len(shown)} != 3")
    need(all(row.subject_key == subject for row in shown), "a row of another subject")
    need(f"Constraints on {subject}" in seen["status"], f"heading: {seen['status']!r}")
    passed("subject")


def check_truncated() -> None:
    client = seeded()
    base = client.list_constraints(PROJECT).rows[0]
    many = [replace(base, key=f"{PROJECT}-CON-{n:04d}", id=f"CON-{n}") for n in range(1, 511)]
    client.load_constraints(PROJECT, many)

    def steps(pilot: Pilot[None], app: TlApp, screen: ConstraintScreen) -> Awaitable[None]:
        async def run_keys() -> None:
            need("(first 500 only)" not in status(screen), "note shown without grouping")
            await pilot.press("o")
            await settle(pilot)
            need("(first 500 only)" in status(screen), f"no note: {status(screen)!r}")

        return run_keys()

    run(client, 170, steps=steps)
    passed("truncated")


def check_missing() -> None:
    client = seeded()

    def steps(pilot: Pilot[None], app: TlApp, screen: ConstraintScreen) -> Awaitable[None]:
        async def run_keys() -> None:
            failing = mock.patch.object(
                client, "get_constraint", side_effect=RecordNotFoundError("no constraint")
            )
            with failing:
                await pilot.press("enter")
                await settle(pilot)
            need(status(screen).startswith("! "), f"no error status: {status(screen)!r}")

        return run_keys()

    run(client, 170, steps=steps)
    passed("missing")


def check_words() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: ConstraintScreen) -> None:
        seen["text"] = screen_text(app)

    run(seeded(), 170, steps=steps)
    need(HEX32.search(seen["text"]) is None, "a cell carries a 32-hex id")
    passed("words")


def main() -> int:
    checks: list[Callable[[], None]] = [
        *(lambda w=w: check_mount(w) for w in MOUNT_WIDTHS),
        check_keys,
        check_subject,
        check_truncated,
        check_missing,
        check_words,
    ]
    try:
        for check in checks:
            check()
    except Failed as exc:
        print(f"FAIL {exc}")
        return 1
    print("T04b ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
