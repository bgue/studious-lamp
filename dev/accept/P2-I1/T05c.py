"""Acceptance for P2-I1-T05c: the path of construction text (``tl_tui.path_text``) and its log
screen (``tl_tui.widgets.path_screen``), on the ``seed_awp`` fake through the Textual pilot. No
database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05c.py``. Prints ``PASS <check>`` per check, then
``T05c ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_awp import PROJECT, seed_awp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle, static_of  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_awp.views import PathStep, PathView  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.display import Labels  # noqa: E402
from tl_tui.layout import plain_lines  # noqa: E402
from tl_tui.path_text import (  # noqa: E402
    PATH_COLUMNS,
    compare_cells,
    compare_versions,
    mark,
    path_cells,
    path_lines,
    path_page,
)
from tl_tui.widgets.path_screen import NO_EARLIER, PathScreen  # noqa: E402

WIDTHS = (80, 170)
SECTIONS = ("CWPs", "Steps changed", "Versions")


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


def check_no_textual() -> None:
    code = "import sys; sys.modules['textual'] = None\nimport tl_tui.path_text\nprint('imported')"
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    need(done.returncode == 0 and "imported" in done.stdout, f"textual imported: {done.stderr}")
    passed("no textual")


def check_lines() -> None:
    client = seeded()
    v2 = client.get_path(PROJECT, version=2)
    cwas, cwps = client.list_cwas(PROJECT), client.list_cwps(PROJECT)
    lines = path_lines(v2, cwas, cwps)
    need(len(lines) == 2, f"two steps expected, got {len(lines)}")
    need(
        path_cells(lines[0]) == ("1", "A1 · Area A1", "—", "2", "65.5"),
        f"step 1 cells {path_cells(lines[0])}",
    )
    need(
        path_cells(lines[1]) == ("2", "A2 · Area A2", "Reorder", "1", "—"),
        f"step 2 cells {path_cells(lines[1])}",
    )
    need(len(PATH_COLUMNS) == 5, "five columns")
    unreadable = path_lines(v2, [], cwps)
    need(path_cells(unreadable[0])[1] == "A1", "an unreadable area reads as its code alone")
    no_cwa = v2.model_copy(update={"steps": [v2.steps[0].model_copy(update={"cwa": None})]})
    need(path_cells(path_lines(no_cwa, cwas, cwps)[0])[1] == "—", "a step with no CWA reads —")
    passed("lines")


def check_compare() -> None:
    client = seeded()
    v1, v2 = client.get_path(PROJECT, version=1), client.get_path(PROJECT, version=2)
    seed = compare_versions(v1, v2)
    need([mark(m) for m in seed] == ["", "new"], f"seed marks {[mark(m) for m in seed]}")

    def step(cwa: str, position: int) -> PathStep:
        return PathStep(
            position=position,
            cwa=cwa,
            reason_code=None,
            actor="user:sue",
            recorded_at="2026-10-15T09:00:00+00:00",
        )

    old = v2.model_copy(update={"steps": [step("A1", 1), step("A2", 2), step("A3", 3)]})
    new = v2.model_copy(
        update={"steps": [step("A3", 1), step("A1", 2), step("A4", 3), step(None, 4)]}
    )
    moves = compare_versions(old, new)
    got = [(m.cwa, mark(m)) for m in moves]
    need(
        got == [("A3", "↑2"), ("A1", "↓1"), ("A4", "new"), ("A2", "gone")],
        f"moved marks {got}",
    )
    need(compare_cells(moves[1]) == ("A1", "1", "2", "↓1"), f"A1 cells {compare_cells(moves[1])}")
    need(compare_cells(moves[3]) == ("A2", "2", "—", "gone"), "gone row reads — after")
    passed("compare")


def check_page() -> None:
    client = seeded()
    v1, v2 = client.get_path(PROJECT, version=1), client.get_path(PROJECT, version=2)
    versions = client.list_path_versions(PROJECT)
    lines = path_lines(v2, client.list_cwas(PROJECT), client.list_cwps(PROJECT))
    for width in WIDTHS:
        wide = plain_lines(path_page(v2, versions, lines[0], previous=v1), width=width)
        need(all(len(line) <= width for line in wide), f"page wider than {width}")
    page = plain_lines(path_page(v2, versions, lines[0], previous=v1), width=80)
    need(page[0] == "Path of construction · version 2", f"identity {page[0]!r}")
    need(
        page[1] == "Re-sequenced 2026-10-15 by sue · reason Access",
        f"state line for version 2 {page[1]!r}",
    )
    stripped = [line.strip() for line in page]
    order = [stripped.index(name) for name in SECTIONS]
    need(order == sorted(order), f"sections out of order: {order}")
    first = plain_lines(path_page(v1, client.list_path_versions(PROJECT), None), width=80)
    need(first[1] == "Defined 2026-10-01 by sue", f"state line for version 1 {first[1]!r}")
    need("Steps changed" not in first, "no previous: no Steps changed section")
    need("CWPs" not in first, "no line: no CWPs section")
    labelled = path_page(
        v2,
        versions,
        None,
        labels=Labels(code_labels={"PathReason": {"Access": "Access to the site"}}),
    )
    need(
        plain_lines(labelled, width=80)[1].endswith("reason Access to the site"),
        "the reason label comes from the PathReason list",
    )
    empty = plain_lines(path_page(v2, versions, None, previous=v2), width=80)
    need("No steps changed" in empty, "unchanged versions say so")
    passed("page")


def open_screen(
    client: FakeClient,
    size: tuple[int, int],
    steps: Callable[[Any, PathScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = PathScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, PathScreen), "the path screen did not open")
        await steps(pilot, screen)

    run_pilot(app, go, size=size)


def check_keys() -> None:
    async def steps(pilot: Any, screen: PathScreen) -> None:
        need(screen.view is not None and screen.view.version == 2, "opens on version 2")
        await pilot.press("left_square_bracket")
        await settle(pilot)
        need(screen.view is not None and screen.view.version == 1, "[ shows version 1")
        need(len(screen.shown) == 1, f"version 1 has one step: {len(screen.shown)}")
        await pilot.press("right_square_bracket")
        await settle(pilot)
        need(screen.view is not None and screen.view.version == 2, "] shows version 2")
        need(len(screen.shown) == 2, f"version 2 has two steps: {len(screen.shown)}")
        await pilot.press("v")
        await settle(pilot)
        need(screen.compare, "v turns the comparison on")
        need([row.cwa for row in screen.shown] == ["A1", "A2"], "compare rows in order")
        await pilot.press("v")
        await settle(pilot)
        need(not screen.compare and len(screen.shown) == 2, "v again shows the steps")
        await pilot.press("v")
        await settle(pilot)
        need(screen.compare, "v turns the comparison on again")
        await pilot.press("left_square_bracket")
        await settle(pilot)
        need(
            screen.view is not None and screen.view.version == 1,
            "[ with compare on shows version 1",
        )
        need(not screen.compare, "[ to version 1 turns the comparison off")
        need(len(screen.shown) == 1, f"version 1 shows its steps: {len(screen.shown)}")
        await pilot.press("right_square_bracket")
        await settle(pilot)
        need(screen.view is not None and screen.view.version == 2, "] shows version 2 again")
        need(len(screen.shown) == 2, f"version 2 shows its steps again: {len(screen.shown)}")
        await pilot.press("left_square_bracket")
        await settle(pilot)
        await pilot.press("v")
        await settle(pilot)
        need(not screen.compare, "v at version 1 does not turn the comparison on")
        need(
            NO_EARLIER in static_of(screen, "#log-status"), "v at version 1 says no earlier version"
        )
        await pilot.press("right_square_bracket")
        await settle(pilot)

    open_screen(seeded(), (120, 40), steps)
    passed("keys")


def check_mount(width: int) -> None:
    async def steps(pilot: Any, screen: PathScreen) -> None:
        lines = screen_text(pilot.app).splitlines()
        too_wide = [line for line in lines if len(line) > width]
        need(not too_wide, f"lines wider than {width}: {too_wide[:1]}")
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row with Number and Subject")
        need("A1 · Area A1" in "\n".join(lines), "no subject shown")
        if width >= 170:
            panel = panel_of(screen)
            need("Path of construction · version 2" in panel, f"panel {panel!r}")
            need("Re-sequenced 2026-10-15" in panel, "panel has no state line")
            need("Versions" in panel and "current" in panel, "panel has no versions")
            need("P123-CWP-0001" in panel, "panel has no CWPs of the highlighted step")

    open_screen(seeded(), (width, 40), steps)
    passed(f"mount {width}")


def check_missing() -> None:
    client = seeded()

    def gone(project: str, version: int | None = None) -> PathView:
        raise RecordNotFoundError(f"no path version {version}")

    client.get_path = gone  # type: ignore[method-assign]

    async def steps(pilot: Any, screen: PathScreen) -> None:
        status = static_of(screen, "#log-status")
        need("no path version" in status, f"no status line: {status!r}")

    open_screen(client, (120, 40), steps)
    passed("missing")


def main() -> int:
    try:
        check_no_textual()
        check_lines()
        check_compare()
        check_page()
        check_keys()
        for width in WIDTHS:
            check_mount(width)
        check_missing()
    except Failed as exc:
        print(f"FAIL {exc}")
        return 1
    print("T05c ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
