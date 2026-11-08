"""Acceptance for P2-I2-T07b: the IWP log and the IWP screen on the fake client (P2-I2 T07b).

The fake is ``FakeClient`` with ``seed_iwp``: four IWPs (CIV-0001 Issued, CIV-0002 Draft with no
foreman, PIP-0001 Draft with scope by type and 3 open constraints, PIP-0002 Ready), mounted in a
Textual pilot. No network, no pytest.

Prints ``PASS mount 80``, ``PASS mount 170``, ``PASS keys``, ``PASS enter``, ``PASS missing`` and
``PASS words``, then ``T07b ok``. Exits 1 on the first failure.

Run: ``uv run python dev/accept/P2-I2/T07b.py``.
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
from helpers import panel_of, run_pilot, screen_text, settle  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable, Static  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.widgets.iwp_register import IwpRegisterScreen, IwpScreen  # noqa: E402

HEIGHT = 44
FIRST = f"{PROJECT}-IWP-CIV-0001"  # sorted first by number; Issued; foreman sue
PIP1 = f"{PROJECT}-IWP-PIP-0001"  # scope by type, 3 open constraints
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
SIGNED_IN = "user:sue"  # the foreman of PIP-0002 and CIV-0001


def need(cond: bool, name: str) -> None:
    if not cond:
        print(f"FAIL {name}", flush=True)
        sys.exit(1)


def seeded() -> FakeClient:
    client = FakeClient()
    seed_iwp(client)
    return client


def mount(client: FakeClient, width: int, actor: str, steps: Any) -> TlApp:
    """Mount the IWP log at ``width`` columns as ``actor``; ``steps(pilot, app, screen)`` runs in
    the pilot."""
    app = TlApp(client, scope=SCOPE, actor=actor)

    async def go(pilot: Pilot[None]) -> None:
        screen = IwpRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        await steps(pilot, app, screen)

    run_pilot(app, go, size=(width, HEIGHT))
    return app


def row_count(screen: IwpRegisterScreen) -> int:
    return screen.query_one("#log-table", DataTable).row_count


def count_after(keys: list[str], actor: str = SIGNED_IN) -> int:
    """The row count of the log after pressing ``keys`` in order."""
    found: list[int] = []

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        for key in keys:
            await pilot.press(key)
            await settle(pilot)
        found.append(row_count(screen))

    mount(seeded(), 170, actor, steps)
    return found[0]


def check_mount(width: int) -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        seen["text"] = screen_text(app)
        seen["panel"] = panel_of(screen)

    mount(seeded(), width, SIGNED_IN, steps)
    lines = seen["text"].splitlines()
    need(all(len(line) <= width for line in lines), f"mount {width} overflow")
    header = next((line for line in lines if "Number" in line and "State" in line), "")
    need(header != "", f"mount {width} header")
    need(header.find("Subject") <= header.find("State"), f"mount {width} subject position")
    if width >= 160:
        panel = seen["panel"]
        need(f"{FIRST} · Civil foundations" in panel, "mount 170 panel identity")
        need("Issued" in panel, "mount 170 panel state")
        need("2026-12-01 to 2026-12-15" in panel and "80 h" in panel, "mount 170 panel summary")
    print(f"PASS mount {width}", flush=True)


def check_keys() -> None:
    base = count_after([])
    need(base == 4, "keys base count")
    need(count_after(["s"]) != base, "keys s")
    need(count_after(["d"]) != base, "keys d")
    need(count_after(["m"], SIGNED_IN) == 2, "keys m uses the actor")
    need(count_after(["m"], "user:kim") == 0, "keys m with another actor")
    need(count_after(["r"]) == 1, "keys r")
    print("PASS keys", flush=True)


def check_enter() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        # the cursor starts on CIV-0001; two Downs reach PIP-0001
        await pilot.press("down", "down")
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen
        seen["text"] = screen_text(app)

    mount(seeded(), 170, SIGNED_IN, steps)
    opened = seen["screen"]
    need(isinstance(opened, IwpScreen), "enter pushes IwpScreen")
    need(opened.number == PIP1, "enter names the IWP")
    text = seen["text"]
    need("Scope" in text and "pinned" in text, "enter scope and drawings")
    need("3 open" in text, "enter open constraints")
    print("PASS enter", flush=True)


def check_missing() -> None:
    seen: dict[str, str] = {}
    app = TlApp(seeded(), scope=SCOPE, actor=SIGNED_IN)

    async def go(pilot: Pilot[None]) -> None:
        screen = IwpScreen(seeded(), PROJECT, "NO-SUCH")
        app.push_screen(screen)
        await settle(pilot)
        seen["status"] = str(screen.query_one("#iwp-status", Static).content)

    run_pilot(app, go, size=(120, HEIGHT))
    need(seen["status"].startswith("! "), "missing error status")
    need("Traceback" not in seen["status"], "missing no traceback")
    print("PASS missing", flush=True)


def check_words() -> None:
    texts: list[str] = []

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        texts.append(screen_text(app))
        texts.append(panel_of(screen))

    mount(seeded(), 170, SIGNED_IN, steps)
    for text in texts:
        need(HEX32.search(text) is None, "words no 32-hex id")
    print("PASS words", flush=True)


def main() -> None:
    check_mount(80)
    check_mount(170)
    check_keys()
    check_enter()
    check_missing()
    check_words()
    print("T07b ok", flush=True)


if __name__ == "__main__":
    main()
