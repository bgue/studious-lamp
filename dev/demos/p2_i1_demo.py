"""Driver for dev/demos/P2-I1.sh: the clauses of the demo that are not a `tl` command.

Modes (first argument):

* ``stale``: clause 3 (the part the CLI cannot show): a path move that names an expected version
  the path has already passed is refused as stale (``StaleVersionError``; the CLI always reads the
  current version). The script prints the clause line.
* ``propose``: clause 6: an agent's ``propose_cwp`` over MCP is pending, and no CWP is made by it
  yet. The proposal id is written to TL_DEMO_STATE for the script to accept as a person.
* ``screens NUMBER``: clause 7: the API (``GET /awp/cwps``), the TUI (CWP register, WBS tree and
  path screens, reached through the palette at 170x44) and the MCP tool ``list_cwps`` show the
  same CWP NUMBER.
* ``cwas``: clause 8: the TUI CWA register lists every CWA with its path position, CWP count and
  budget hours, as the API reads them.
* ``packages``: clause 9: the TUI external packages log lists both EWP references, ``Constraint
  source`` ``Yes`` on the one that is, with the CWPs that require them.

Reads TL_DB (SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AGENT_TOKEN and TL_DEMO_STATE. Every expectation is an assert: a failing check exits
non-zero. Nothing printed holds a password or a token.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)
SIZE = (170, 44)


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS clause {clause}: {text}")


def plain(renderable: Any) -> str:
    """The text a Rich renderable shows, without colour."""
    from rich.console import Console

    buffer = io.StringIO()
    Console(file=buffer, width=SIZE[0], color_system=None, legacy_windows=False).print(renderable)
    return buffer.getvalue()


def agent_session(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={
            "TL_AGENT_TOKEN": os.environ["TL_DEMO_AGENT_TOKEN"],
            "TL_DB": os.environ["TL_DB"],
            "TL_ENV": os.environ.get("TL_ENV", "dev"),
            "TL_OBJECT_ROOT": os.environ["TL_OBJECT_ROOT"],
            "PATH": os.environ.get("PATH", ""),
        },
    )

    async def session() -> dict[str, Any]:
        async with Client(params) as mcp:
            names = {t.name for t in (await mcp.list_tools()).tools}
            assert {"propose_cwp", "list_cwps"} <= names, names
            result = await mcp.call_tool(name, arguments)
            assert not result.is_error and result.structured_content is not None, result
            return result.structured_content

    return asyncio.run(session())


def stale() -> None:
    from tl_adapters.db import open_uow
    from tl_mod_awp.commands import MoveCwaInPath
    from tl_mod_awp.errors import StaleVersionError
    from tl_mod_awp.handlers.path import handle_move_cwa_in_path

    db = os.environ["TL_DB"]
    # the path is at version 2 (the script moved CWA-C once); version 1 is stale
    command = MoveCwaInPath(
        actor="user:demo",
        source="demo",
        scope=SCOPE,
        cwa_code="CWA-A",
        to_position=2,
        reason_code="Crew",
        expected_version=1,
    )
    try:
        with open_uow(db) as uow:
            handle_move_cwa_in_path(uow, command)
    except StaleVersionError as exc:
        say(f"refused: {exc}")
        return
    raise SystemExit("FAIL a path move with a stale expected version was accepted")


def propose() -> None:
    from sqlalchemy import text
    from tl_adapters.db import open_uow

    def cwp_count() -> int:
        with open_uow(os.environ["TL_DB"], readonly=True) as uow:
            return int(
                uow.conn()
                .execute(text("SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'"))
                .scalar_one()
            )

    before = cwp_count()
    found = agent_session(
        "propose_cwp",
        {
            "project": PROJECT,
            "discipline": "PIP",
            "title": "Proposed piping spool run",
            "cwa_code": "CWA-A",
            "budget_hours": "60",
        },
    )
    proposal = found["proposal"]
    assert proposal["status"] == "pending", proposal
    assert proposal["tool"] == "propose_cwp", proposal
    assert cwp_count() == before, "the proposal made a CWP before anyone accepted it"
    Path(os.environ["TL_DEMO_STATE"]).write_text(proposal["proposal_id"])
    say(f"the agent's proposal {proposal['proposal_id']} is pending; no CWP was made")


def _api():
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    return ApiClient(url, sign_in(url, *DEMO).token)


# the palette matches a command on its label; these words pick the one entry (no punctuation)
LABELS = {
    "cwps": "Work packages CWPs",
    "wbs": "WBS the work breakdown",
    "cwas": "Work areas CWAs",
    "path": "Path of construction the order",
    "packages": "External packages EWP",
}
SCREENS = {
    "cwps": ("tl_tui.widgets.cwp_register", "CwpRegisterScreen"),
    "wbs": ("tl_tui.widgets.wbs_screen", "WbsScreen"),
    "cwas": ("tl_tui.widgets.cwa_register", "CwaRegisterScreen"),
    "path": ("tl_tui.widgets.path_screen", "PathScreen"),
    "packages": ("tl_tui.widgets.package_log", "PackageLogScreen"),
}


async def _open(app: Any, pilot: Any, entry: str, minimum: int) -> Any:
    """Type the palette entry's label, press Enter, and wait for the screen's rows to load."""
    import importlib

    module_name, class_name = SCREENS[entry]
    screen_cls = getattr(importlib.import_module(module_name), class_name)
    await pilot.press("ctrl+p")
    await pilot.pause()
    await pilot.press(*[("space" if ch == " " else ch) for ch in LABELS[entry]])
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, screen_cls), f"{entry}: the palette opened {type(screen).__name__}"
    for _ in range(100):
        await pilot.pause(0.05)
        if len(screen.rows) >= minimum:
            break
    assert len(screen.rows) >= minimum, f"{entry}: {len(screen.rows)} rows"
    return screen


async def _tui(
    entry: str, minimum: int, inspect: Callable[[Any], dict[str, Any]]
) -> dict[str, Any]:
    """Open one awp screen through the palette at SIZE, let ``inspect`` read it, then close it."""
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient

    client = EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo", is_admin=True)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            screen = await _open(app, pilot, entry, minimum)
            found = inspect(screen)
            await pilot.press("escape")
            await pilot.pause()
            return found
    finally:
        client.close()


def _table(screen: Any) -> list[list[str]]:
    return [list(screen.row_cells(row)) for row in screen.rows]


def _rows_of(structured: dict[str, Any]) -> list[dict[str, Any]]:
    """The list an MCP tool returned: its ``result`` (or the only list in the answer)."""
    if isinstance(structured.get("result"), list):
        return structured["result"]
    lists = [v for v in structured.values() if isinstance(v, list)]
    assert len(lists) == 1, f"the MCP answer has {len(lists)} lists"
    return lists[0]


def _numbers(cells: list[str]) -> set[float]:
    return {float(c) for c in cells if re.fullmatch(r"-?\d+(\.\d+)?", c.strip())}


def screens(number: str) -> None:
    api = _api()
    try:
        api_cwp = api.get_cwp(PROJECT, number)
        listed = {c.number for c in api.list_cwps(PROJECT)}
        api_node = api.get_wbs_node(PROJECT, "1.1.1")
    finally:
        api.close()
    assert number in listed, f"the API lists no {number}"
    assert number in api_node.model_dump_json(), f"the API's node 1.1.1 shows no {number}"
    mcp = agent_session("list_cwps", {"project": PROJECT})
    assert number in {row["number"] for row in _rows_of(mcp)}, f"MCP list_cwps shows no {number}"

    def register(screen: Any) -> dict[str, Any]:
        cells = next((c for c in _table(screen) if c and c[0] == number), None)
        assert cells is not None, f"the CWP register shows no {number}"
        return {"cells": cells}

    def wbs(screen: Any) -> dict[str, Any]:
        row = next(r for r in screen.rows if r.code == "1.1.1")
        return {"panel": plain(screen.panel_text(row))}

    def path(screen: Any) -> dict[str, Any]:
        return {"text": " ".join(" ".join(c) for c in _table(screen))}

    shown = asyncio.run(_tui("cwps", 1, register))
    row_text = " ".join(shown["cells"])
    cwa = api_cwp.cwa or ""
    assert api_cwp.state in row_text and cwa in row_text, f"TUI row: {row_text}"
    panel = asyncio.run(_tui("wbs", 1, wbs))
    assert number in panel["panel"], f"the WBS node 1.1.1 panel shows no {number}"
    placed = asyncio.run(_tui("path", 1, path))
    assert cwa in placed["text"], f"the path screen shows no {cwa}"
    say(
        f"API {api_cwp.state} in {api_cwp.cwa}; TUI register row, WBS node 1.1.1 panel and path; "
        f"MCP list_cwps"
    )
    passed(
        7,
        f"the API, the TUI (CWP register, WBS tree, path at {SIZE[0]} columns) and MCP show "
        f"{number}",
    )


def cwas() -> None:
    api = _api()
    try:
        areas = api.list_cwas(PROJECT)
        cwps = api.list_cwps(PROJECT)
        path_view = api.get_path(PROJECT)
    finally:
        api.close()
    assert len(areas) == 4, f"{len(areas)} CWAs"
    position = {step.cwa: step.position for step in path_view.steps if step.cwa}
    expected: dict[str, tuple[int | None, int, float]] = {}
    for area in areas:
        mine = [c for c in cwps if c.cwa == area.code]
        expected[area.code] = (
            position.get(area.code),
            len(mine),
            sum(float(c.budget_hours or 0) for c in mine),
        )

    def register(screen: Any) -> dict[str, Any]:
        return {"rows": {cells[0]: cells for cells in _table(screen)}}

    shown = asyncio.run(_tui("cwas", 4, register))["rows"]
    for code, (place, count, hours) in expected.items():
        assert code in shown, f"the CWA register shows no {code}"
        numbers = _numbers(shown[code])
        assert float(count) in numbers, f"{code}: CWP count {count} not in {shown[code]}"
        assert hours in numbers or round(hours, 1) in numbers, f"{code}: hours {hours} not shown"
        assert place is None or float(place) in numbers, f"{code}: path place {place} not shown"
    say("; ".join(f"{c} place {p} CWPs {n} hours {h:g}" for c, (p, n, h) in expected.items()))
    passed(8, "the CWA register lists the 4 CWAs with path position, CWP count and budget hours")


def packages() -> None:
    api = _api()
    try:
        listed = {p.package_no: p for p in api.list_packages(PROJECT)}
    finally:
        api.close()
    assert {"EWP-0001", "EWP-0002"} <= set(listed), "the API lists no two EWP references"
    assert listed["EWP-0001"].constraint_source and not listed["EWP-0002"].constraint_source
    assert listed["EWP-0001"].cwps, "EWP-0001 is required by no CWP"

    def log(screen: Any) -> dict[str, Any]:
        rows = {cells[0]: cells for cells in _table(screen)}
        panels = {}
        for row in screen.rows:
            if row.package_no in ("EWP-0001", "EWP-0002"):
                panels[row.package_no] = plain(screen.panel_text(row))
        return {"rows": rows, "panels": panels}

    shown = asyncio.run(_tui("packages", 2, log))
    rows = shown["rows"]
    for number in ("EWP-0001", "EWP-0002"):
        assert number in rows, f"the packages log shows no {number}"
    constrained = [n for n in ("EWP-0001", "EWP-0002") if "Yes" in rows[n]]
    assert constrained == ["EWP-0001"], f"constraint source column: {constrained}"
    for cwp in listed["EWP-0001"].cwps:
        assert cwp in shown["panels"]["EWP-0001"], f"the EWP-0001 panel shows no {cwp}"
    say(f"constraint source Yes on EWP-0001; required by {', '.join(listed['EWP-0001'].cwps)}")
    passed(9, "the external packages log lists both EWP references, Constraint source Yes on one")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "stale":
        stale()
    elif mode == "propose":
        propose()
    elif mode == "screens":
        screens(sys.argv[2])
    elif mode == "cwas":
        cwas()
    elif mode == "packages":
        packages()
    else:
        sys.exit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
