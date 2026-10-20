"""Driver for dev/demos/P1-I6.sh: what a person, a controller, an agent and the TUI see of RFIs and
Commercial notices.

Modes (first argument), each ending in a PASS line for its clause:

* ``screen``: clause 8. The TUI (Ctrl+G) lists the RFIs for a person and for a controller, and the
  Commercial register only for the controller; the evidence view shows the trail of the notice.
* ``hidden``: clause 3. A restricted notice does not exist for a user, for the API as that user:
  the answer for it is the answer for a number that was never used, and the RFI shows no escalation.
* ``agent``: clause 8. An agent reads the RFI log over MCP and finds no Commercial item: its
  answer for a notice is the answer for a number that was never used.
* ``csv FILE``: clause 6. The exported file is private and its cells that start like a formula are
  quoted.

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AGENT_TOKEN, TL_DEMO_RFI, TL_DEMO_NOTICE. Every expectation is an assert: a failing demo
exits non-zero. Nothing printed holds a password or token.
"""

from __future__ import annotations

import asyncio
import csv
import os
import stat
import sys
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


async def screen_of(db: str, actor: str, notice: str) -> dict[str, Any]:
    """Open Ctrl+G as ``actor``: the RFI numbers, the notice numbers, and the evidence trail."""
    from textual.widgets import DataTable
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.domain_screen import DomainScreen

    client = EmbeddedClient.for_target(db, actor=actor)
    try:
        app = TlApp(client, scope=SCOPE, actor=actor)
        async with app.run_test(size=(200, 50)) as pilot:
            await pilot.press("ctrl+g")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DomainScreen)
            rfis = [x.number for x in (screen.rfi_log.lines if screen.rfi_log else [])]
            await pilot.press("2")
            await pilot.pause()
            notices = [x.number for x in (screen.notices.lines if screen.notices else [])]
            trail: list[str] = []
            if notice in notices:
                screen.query_one("#dom-table", DataTable).move_cursor(row=notices.index(notice))
                await pilot.pause()
                await pilot.press("e")
                await pilot.pause()
                assert screen.trail is not None
                trail = [n.key or "" for n in screen.trail.nodes]
                assert screen.query_one("#dom-table", DataTable).row_count == len(trail)
            return {"rfis": rfis, "notices": notices, "trail": trail}
    finally:
        client.close()


def screen() -> None:
    db = os.environ["TL_DB"]
    rfi, notice = os.environ["TL_DEMO_RFI"], os.environ["TL_DEMO_NOTICE"]
    plain = asyncio.run(screen_of(db, "user:amy", notice))
    boss = asyncio.run(screen_of(db, "user:demo", notice))
    assert rfi in plain["rfis"] and plain["rfis"] == boss["rfis"], (plain, boss)
    assert plain["notices"] == [], plain  # the notices are restricted: none is listed for amy
    assert notice in boss["notices"], boss
    assert boss["trail"][:2] == [notice, rfi], boss["trail"]  # the notice, and the RFI it came from
    say(f"Ctrl+G, amy: RFIs {plain['rfis']}, notices {plain['notices']}")
    say(f"Ctrl+G, a controller: notices {boss['notices']}; evidence trail {boss['trail']}")
    passed(
        8,
        "the TUI lists the RFIs for everyone, "
        "the notices and their evidence trail only for a controller",
    )


async def agent_session(db: str, token: str, rfi: str, notice: str) -> dict[str, Any]:
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={"TL_AGENT_TOKEN": token, "TL_DB": db, "TL_ENV": os.environ.get("TL_ENV", "dev")},
    )
    async with Client(params) as mcp:
        names = {t.name for t in (await mcp.list_tools()).tools}
        assert {"list_rfis", "get_rfi", "list_commercial_items", "get_commercial_item"} <= names
        found = await mcp.call_tool("list_rfis", {"project": PROJECT})
        assert not found.is_error and found.structured_content is not None
        notices = await mcp.call_tool("list_commercial_items", {"project": PROJECT})
        assert not notices.is_error and notices.structured_content is not None
        answers: list[str] = []
        for number in (notice, "P123-EW-9999"):
            reply = await mcp.call_tool(
                "get_commercial_item", {"project": PROJECT, "number": number}
            )
            assert reply.is_error
            text = "".join(getattr(part, "text", "") for part in reply.content)
            answers.append(text.replace(number, "<number>"))
        return {
            "rfis": found.structured_content,
            "notices": notices.structured_content,
            "answers": answers,
        }


def agent() -> None:
    rfi, notice = os.environ["TL_DEMO_RFI"], os.environ["TL_DEMO_NOTICE"]
    found = asyncio.run(
        agent_session(os.environ["TL_DB"], os.environ["TL_DEMO_AGENT_TOKEN"], rfi, notice)
    )
    lines = found["rfis"].get("lines", found["rfis"].get("result", {}).get("lines", []))
    assert rfi in [x["number"] for x in lines], found["rfis"]
    listed = found["notices"].get("lines", found["notices"].get("result", {}).get("lines", None))
    assert not listed, found["notices"]
    assert found["answers"][0] == found["answers"][1], found["answers"]
    say(
        f"MCP: list_rfis has {rfi}; list_commercial_items is empty; "
        "get_commercial_item says the same as for an unused number"
    )
    passed(8, "an agent reads the RFI log and finds no Commercial item")


def csv_check(path: str) -> None:
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, oct(mode)
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "the export holds no change"
    by_number = {r["number"]: r for r in rows}
    quoted = [r for r in rows if r["title"].startswith("'=")]
    assert quoted, [r["title"] for r in rows]  # a title that starts like a formula is quoted
    statuses = {r["cost_status"] for r in rows}
    assert statuses <= {"pending", "approved"}, statuses
    assert {r["currency"] for r in rows} >= {"USD", "EUR"}, rows  # two currencies, never added
    say(f"{path}: mode {oct(mode)}, {len(rows)} changes ({', '.join(sorted(by_number))})")
    passed(
        6, "the export is private, quotes what a spreadsheet would run, and keeps currencies apart"
    )


def hidden() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url, notice = os.environ["TL_DEMO_URL"], os.environ["TL_DEMO_NOTICE"]
    rfi = os.environ["TL_DEMO_RFI"]
    amy = ApiClient(url, sign_in(url, "amy", os.environ["TL_DEMO_AMY_PASSWORD"]).token)
    boss = ApiClient(url, sign_in(url, "demo", "demo").token)
    try:
        assert notice in [x.number for x in boss.list_commercial(PROJECT).lines]
        assert amy.list_commercial(PROJECT).lines == []
        answers: list[str] = []
        for number in (notice, "P123-EW-9999"):
            try:
                amy.get_commercial(PROJECT, number)
            except Exception as exc:
                answers.append(f"{type(exc).__name__}: {str(exc).replace(number, '<number>')}")
            else:
                raise AssertionError(f"amy read {number}")
        assert answers[0] == answers[1], answers
        say(f"amy: {answers[0]}")
        assert amy.get_rfi(PROJECT, rfi).escalations == []
        assert [e.number for e in boss.get_rfi(PROJECT, rfi).escalations] == [notice]
    finally:
        amy.close()
        boss.close()
    say("the RFI lists its escalation for a controller and none for a user")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "screen":
        screen()
    elif mode == "hidden":
        hidden()
    elif mode == "agent":
        agent()
    elif mode == "csv":
        csv_check(sys.argv[2])
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
