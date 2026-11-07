"""Acceptance for P2-I1-T05e: the CWA register text (``tl_tui.cwa_text``) and its screen
(``tl_tui.widgets.cwa_register``), on the ``seed_awp`` fake. No database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05e.py``. Prints ``PASS <check>`` per check, then
``T05e ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import SCOPE, FakeClient  # noqa: E402
from fakes_awp import PROJECT, seed_awp  # noqa: E402
from helpers import panel_of, run_pilot, screen_text, settle, static_of  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_awp.views import CwaRow  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.cwa_text import (  # noqa: E402
    CwaLine,
    cwa_cells,
    cwa_lines,
    cwa_page,
    cwa_summary,
    visible_lines,
)
from tl_tui.layout import plain_lines  # noqa: E402
from tl_tui.widgets.cwa_register import CwaRegisterScreen  # noqa: E402

WIDTHS = (80, 170)


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def check_no_textual() -> None:
    code = "import sys; sys.modules['textual'] = None\nimport tl_tui.cwa_text\nprint('imported')"
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    need(done.returncode == 0 and "imported" in done.stdout, f"textual imported: {done.stderr}")
    passed("no textual")


def seeded_client() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    return client


def by_code(lines: list[CwaLine], code: str) -> CwaLine:
    return next(line for line in lines if line.row.code == code)


def check_lines(client: FakeClient) -> None:
    cwas = client.list_cwas(PROJECT)
    path = client.get_path(PROJECT)
    cwps = client.list_cwps(PROJECT)
    lines = cwa_lines(cwas, path, cwps)
    codes = [line.row.code for line in lines]
    need(codes == ["A1", "A2"], f"order {codes}")
    need(by_code(lines, "A1").position == 1 and by_code(lines, "A2").position == 2, "positions")
    need(by_code(lines, "A1").steps == 2, "the path of version 2 has two steps")
    need(len(by_code(lines, "A1").cwps) == 2 and len(by_code(lines, "A2").cwps) == 1, "CWPs")
    need(cwa_cells(by_code(lines, "A1"))[3] == "2", "CWP count cell")
    need(len(visible_lines(lines, False)) == 1, "the retired A2 is hidden by default")
    need(len(visible_lines(lines, True)) == 2, "show_retired keeps every area")
    extra = CwaRow(id="CWA-A0", code="A0", title="Area A0", location_text=None, retired=False)
    off = cwa_lines([extra, *cwas], path, cwps)
    need([line.row.code for line in off] == ["A1", "A2", "A0"], "an area off the path is last")
    need(cwa_cells(off[-1])[2] == "—", "an area off the path reads — for its position")
    bare = cwa_lines(cwas, None, [])
    need([line.row.code for line in bare] == ["A1", "A2"], "no path: order by code")
    need(all(line.position is None and line.steps == 0 for line in bare), "no path: no positions")
    passed("lines")


def check_page(client: FakeClient) -> None:
    lines = cwa_lines(
        client.list_cwas(PROJECT), client.get_path(PROJECT), client.list_cwps(PROJECT)
    )
    a1 = by_code(lines, "A1")
    need(cwa_summary(a1) == "Position 1 of 2 · 2 CWPs · 65.5 h", f"summary {cwa_summary(a1)!r}")
    for width in WIDTHS:
        text = plain_lines(cwa_page(a1, panel=True), width=width)
        print(f"-- width {width}")
        print("\n".join(text))
        for heading in ("Location", "CWPs"):
            need(heading in [line.strip() for line in text], f"no heading {heading!r}")
        need(not any(line.strip() in ("Files", "Links") for line in text), "Files shown")
    technical = plain_lines(cwa_page(a1, technical=True), width=80)
    need(any("CWA-A1" in line for line in technical), "technical mode lacks the id")
    plain = plain_lines(cwa_page(a1), width=80)
    need(not any("CWA-A1" in line for line in plain), "plain mode shows the id")
    empty = CwaLine(row=by_code(lines, "A2").row, position=None, cwps=(), steps=2)
    need("No CWPs in this area" in plain_lines(cwa_page(empty), width=80), "no note when empty")
    passed("page")


def check_retired(client: FakeClient) -> None:
    # the seed has one retired area (A2); the screen hides it until r is pressed
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def steps(pilot: Any, screen: CwaRegisterScreen) -> None:
        need(len(screen.shown) == 1, f"retired hidden at first: {len(screen.shown)} rows")
        await pilot.press("r")
        await settle(pilot)
        need(len(screen.shown) == 2, f"r shows the retired area: {len(screen.shown)} rows")
        await pilot.press("r")
        await settle(pilot)
        need(len(screen.shown) == 1, "r again hides it")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, CwaRegisterScreen), "the CWA register did not open")
        await steps(pilot, screen)

    run_pilot(app, go, size=(120, 40))
    passed("retired")


def check_mount(client: FakeClient, width: int) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, CwaRegisterScreen), "the CWA register did not open")
        lines = screen_text(pilot.app).splitlines()
        too_wide = [line for line in lines if len(line) > width]
        need(not too_wide, f"lines wider than {width}: {too_wide[:1]}")
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row with Number and Subject")
        need(header.index("Subject") < header.index("Position"), "Subject starts after column 3")
        need("Area A1" in "\n".join(lines), "no subject shown")
        if width >= 170:
            panel = panel_of(screen)
            need("A1 · Area A1" in panel and "Active" in panel, f"panel {panel!r}")
            need("Position 1 of 2 · 2 CWPs · 65.5 h" in panel, f"panel summary {panel!r}")
        status = static_of(screen, "#log-status")
        need(not status.startswith("!"), f"an error in the status line: {status!r}")

    run_pilot(app, go, size=(width, 40))
    passed(f"mount {width}")


def check_missing() -> None:
    client = seeded_client()

    def no_path(project: str, version: int | None = None) -> None:
        raise RecordNotFoundError(f"no path {project!r} at version {version!r}")

    client.get_path = no_path  # type: ignore[method-assign]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(len(screen.shown) == 1, f"the area list is empty without a path: {len(screen.shown)}")
        need(cwa_cells(screen.shown[0])[2] == "—", "no path: the position reads —")
        status = static_of(screen, "#log-status")
        need(not status.startswith("!"), f"no path is an error: {status!r}")

    run_pilot(app, go, size=(120, 40))
    passed("missing")


def main() -> int:
    client = seeded_client()
    checks: list[tuple[str, Callable[[], None]]] = [
        ("no textual", check_no_textual),
        ("lines", lambda: check_lines(client)),
        ("page", lambda: check_page(client)),
        ("retired", lambda: check_retired(seeded_client())),
    ]
    for width in WIDTHS:
        checks.append((f"mount {width}", lambda w=width: check_mount(seeded_client(), w)))
    checks.append(("missing", check_missing))
    try:
        for _, run in checks:
            run()
    except Failed as exc:
        print(f"FAIL {exc}")
        return 1
    print("T05e ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
