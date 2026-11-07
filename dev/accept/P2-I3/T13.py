"""Acceptance for P2-I3-T13: the materials registry glue (MCP actions and tools, TUI keys, keymap).

Checks, each printed as ``PASS <check>``; the first failure prints ``FAIL <check>: <detail>`` and
exits 1:

1. every name in ``MATERIALS_MCP_ACTIONS`` is in ``tl_mcp.identity.MCP_ACTIONS``;
2. an in-process MCP server built with the real ``build_server`` lists the ten materials tools;
3. ``TlApp`` binds one key per new materials screen, and no key is bound twice in ``TlApp``;
4. each new key has exactly one ``KEYMAP`` row, and each row names its binding;
5. each key pushes its screen on a copy of ``.accept/p2-i3.db`` (build it with
   ``dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db`` first) at 100 columns, and saves
   ``.accept/shots/T13-<screen>.svg``.

Not checked here: the navigation panel entries (``widgets/nav_tree.py`` has no entry for any
module view yet; see the T13 report, Blocked).

    uv run python dev/accept/P2-I3/T13.py
"""

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
ACTOR_AGENT = "agent:triage"
SIZE = (100, 40)
sys.path[:0] = [str(ROOT / "packages/tl-api/tests"), str(ROOT / "packages/tl-tui/tests")]
os.environ.setdefault("TL_ENV", "dev")

from harness import ALICE  # noqa: E402
from helpers import settle  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mcp.identity import MCP_ACTIONS  # noqa: E402
from tl_mcp.materials_tools import MATERIALS_MCP_ACTIONS  # noqa: E402
from tl_mcp.server import build_server  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.keymap import KEYMAP  # noqa: E402
from tl_tui.widgets.item_library import ItemLibraryScreen  # noqa: E402
from tl_tui.widgets.location_screen import LocationScreen  # noqa: E402
from tl_tui.widgets.movement_screen import MovementLogScreen  # noqa: E402
from tl_tui.widgets.mto_screen import MtoLinesScreen  # noqa: E402
from tl_tui.widgets.receipt_log import ReceiptLogScreen  # noqa: E402
from tl_tui.widgets.stock_screen import StockScreen  # noqa: E402

# (key, action, screen class, short name for the SVG, keymap description)
NEW_SCREENS: tuple[tuple[str, str, type, str], ...] = (
    ("S", "stock", StockScreen, "stock"),
    ("M", "movements", MovementLogScreen, "movements"),
    ("E", "receipts", ReceiptLogScreen, "receipts"),
    ("D", "mto_lines", MtoLinesScreen, "mto-lines"),
    ("I", "items", ItemLibraryScreen, "items"),
    ("W", "locations", LocationScreen, "locations"),
)
MATERIALS_TOOLS = 10


def check(ok: bool, name: str, detail: str = "") -> None:
    if not ok:
        raise AssertionError(f"{name}: {detail}")
    print(f"PASS {name}")


def check_mcp_names() -> None:
    missing = sorted(MATERIALS_MCP_ACTIONS - MCP_ACTIONS)
    check(not missing, "materials actions are in MCP_ACTIONS", str(missing))
    check(
        len(MATERIALS_MCP_ACTIONS) == MATERIALS_TOOLS,
        "ten materials actions",
        str(len(MATERIALS_MCP_ACTIONS)),
    )


def check_mcp_tools(db: Path, lake: Path) -> None:
    from tl_adapters.db import as_target, make_uow_factory

    factory = make_uow_factory(as_target(db))
    server = build_server(factory, actor=ACTOR_AGENT, lake_dir=lake)
    names = {t.name for t in asyncio.run(server.list_tools())}
    # an action is ``mcp.<tool>``; the server lists the tool by its bare name
    absent = sorted(a for a in MATERIALS_MCP_ACTIONS if a.removeprefix("mcp.") not in names)
    check(not absent, "server lists the ten materials tools", str(absent))


def check_keys() -> None:
    seen: dict[str, str] = {}
    for binding in TlApp.BINDINGS:
        keys = [k.strip() for k in str(binding.key).split(",")]  # type: ignore[union-attr]
        for key in keys:
            if key in seen:
                raise AssertionError(f"key {key!r} bound to {seen[key]} and {binding.action}")
            seen[key] = str(binding.action)
    for key, action, _cls, _name in NEW_SCREENS:
        check(seen.get(key) == action, f"{key} binds {action}", str(seen.get(key)))
    check(True, "one binding per new screen, no duplicate key in TlApp")


def check_keymap() -> None:
    for key, _action, _cls, _name in NEW_SCREENS:
        rows = [e for e in KEYMAP if e.owner == "TlApp" and e.binding == key]
        check(len(rows) == 1, f"keymap has one row for {key}", str(len(rows)))
        check(rows[0].keys == key, f"keymap row {key} shows its key", rows[0].keys)


async def press_each(db: Path) -> None:
    client = EmbeddedClient(SqliteUowFactory(db), actor=ALICE)
    app = TlApp(client, scope=f"project:{PROJECT}", actor=ALICE, is_admin=False)
    SHOTS.mkdir(parents=True, exist_ok=True)
    async with app.run_test(size=SIZE) as pilot:
        await settle(pilot)
        for key, _action, cls, name in NEW_SCREENS:
            await pilot.press(key)
            await settle(pilot)
            check(isinstance(app.screen, cls), f"{key} opens {name}", type(app.screen).__name__)
            (SHOTS / f"T13-{name}.svg").write_text(app.export_screenshot(title=name))
            await pilot.press("escape")
            await settle(pilot)
            check(not isinstance(app.screen, cls), f"Esc closes {name}", "")


def main() -> int:
    if not SEED.exists():
        print(f"FAIL ledger: {SEED} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    try:
        check_mcp_names()
        check_keys()
        check_keymap()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "tl.db"
            shutil.copy(SEED, db)
            check_mcp_tools(db, Path(tmp) / "lake")
            asyncio.run(press_each(db))
    except AssertionError as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
