"""Driver for dev/demos/P1-I5.sh: what a person, a client and an agent see of the correspondence.

Modes (first argument), each ending in a PASS line for its clause:

* ``make-eml PATH``: writes the message clause 5 reads in (a reply with a PDF attached).
* ``clocks``: clause 3. The clocks screen (F12, then 3) on the ledger shows the reply's clock with
  the days left on the project calendar.
* ``hidden``: clause 6. A restricted item does not exist for a user, for the API as that user, or
  for an agent; the answer for it is the answer for a number that was never used.
* ``reads``: clause 7. The same register through the API, the TUI (F12) and an agent's MCP tools,
  and an agent's triage is a proposal, not a decision.

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AMY_PASSWORD, TL_DEMO_AGENT_TOKEN, TL_DEMO_REPLY, TL_DEMO_SECRET, TL_DEMO_RECEIVED. Every
expectation is an assert: a failing demo exits non-zero. Nothing printed holds a password or token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


def make_eml(path: str) -> None:
    """A reply from the contractor's domain to 'Revised programme', with a PDF attached."""
    message = EmailMessage()
    message["From"] = "Ann Acme <ann@acme.example>"
    message["To"] = "site@throughline.example"
    message["Subject"] = "RE: Revised programme"
    message["Message-ID"] = "<programme-reply-1@acme.example>"
    message["Date"] = formatdate()
    message.set_content("Thank you. The marked-up programme is attached.\n")
    message.add_attachment(
        b"%PDF-1.7 marked-up programme\n",
        maintype="application",
        subtype="pdf",
        filename="programme-markup.pdf",
    )
    Path(path).write_bytes(bytes(message))
    say(f"wrote {path}")


async def clocks_screen(db: str) -> tuple[str, str]:
    """Open the correspondence screen (F12) as demo, show the clocks (3): the table, the detail."""
    from textual.widgets import DataTable, Static
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.correspondence_screen import CorrespondenceScreen

    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo")
        async with app.run_test(size=(180, 48)) as pilot:
            await pilot.press("f12")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, CorrespondenceScreen)
            await pilot.press("3")
            await pilot.pause()
            assert screen.query_one("#corr-table", DataTable).row_count >= 1
            wanted = os.environ["TL_DEMO_REPLY"]
            keys = [c.item_number for c in screen.clocks]
            assert wanted in keys, keys
            screen.query_one("#corr-table", DataTable).move_cursor(row=keys.index(wanted))
            await pilot.pause()
            clock = screen.current_clock()
            assert clock is not None
            return (
                "\n".join(str(c) for c in (clock.key, clock.due_on, clock.days_left)),
                str(screen.query_one("#corr-detail", Static).render()),
            )
    finally:
        client.close()


def clocks() -> None:
    from datetime import date, timedelta

    found, detail = asyncio.run(clocks_screen(os.environ["TL_DB"]))
    key, due, left = found.splitlines()
    assert due == (date.today() + timedelta(days=14)).isoformat(), due
    assert left == "14", left
    assert "calendar P123-default@1" in detail, detail
    say(f"clocks screen: {key} due {due}, {left} days left")
    passed(3, "the clocks screen shows the reply's 14-calendar-day clock with 14 days left")


def hidden() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url, secret = os.environ["TL_DEMO_URL"], os.environ["TL_DEMO_SECRET"]
    amy = ApiClient(url, sign_in(url, "amy", os.environ["TL_DEMO_AMY_PASSWORD"]).token)
    boss = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        assert secret in [x.number for x in boss.list_correspondence(PROJECT)]
        assert secret not in [x.number for x in amy.list_correspondence(PROJECT)]
        answers: list[str] = []
        for number in (secret, "P123-COR-9999"):
            try:
                amy.get_correspondence(PROJECT, number)
            except Exception as exc:
                answers.append(f"{type(exc).__name__}: {str(exc).replace(number, '<number>')}")
            else:
                raise AssertionError(f"amy read {number}")
        assert answers[0] == answers[1], answers
        say(f"amy: {answers[0]}")
        assert secret not in [c.item_number for c in amy.list_clocks(PROJECT, open_only=False)]
    finally:
        amy.close()
        boss.close()
    passed(
        6, "a restricted item does not exist for a user: not in lists, and its answer is the same"
    )


async def agent_session(db: str, token: str, received: str) -> dict[str, Any]:
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={"TL_AGENT_TOKEN": token, "TL_DB": db, "TL_ENV": os.environ.get("TL_ENV", "dev")},
    )
    async with Client(params) as mcp:
        names = {t.name for t in (await mcp.list_tools()).tools}
        assert {"list_correspondence", "suggest_triage", "propose_triage"} <= names
        listed = await mcp.call_tool("list_correspondence", {"project": PROJECT})
        assert not listed.is_error and listed.structured_content is not None
        suggested = await mcp.call_tool("suggest_triage", {"project": PROJECT, "number": received})
        assert not suggested.is_error and suggested.structured_content is not None
        proposed = await mcp.call_tool(
            "propose_triage",
            {"project": PROJECT, "number": received, "domain": "general", "subtype": "letter"},
        )
        assert not proposed.is_error and proposed.structured_content is not None
        return {
            "listed": listed.structured_content,
            "suggested": suggested.structured_content,
            "proposed": proposed.structured_content,
        }


async def register_screen(db: str) -> list[str]:
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.correspondence_screen import CorrespondenceScreen

    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo")
        async with app.run_test(size=(180, 48)) as pilot:
            await pilot.press("f12")
            await pilot.pause()
            assert isinstance(app.screen, CorrespondenceScreen)
            return [line.number for line in app.screen.lines]
    finally:
        client.close()


def reads() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    received = os.environ["TL_DEMO_RECEIVED"]
    api = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        via_api = [x.number for x in api.list_correspondence(PROJECT)]
        before = len(api.get_correspondence(PROJECT, received).clocks)
    finally:
        api.close()
    via_tui = asyncio.run(register_screen(db))
    assert via_api == via_tui, (via_api, via_tui)
    say(f"API and TUI register: {len(via_api)} lines, the same in the same order")
    found = asyncio.run(agent_session(db, os.environ["TL_DEMO_AGENT_TOKEN"], received))
    listed = (
        [x["number"] for x in found["listed"]["result"]]
        if "result" in found["listed"]
        else [x["number"] for x in found["listed"]]
    )
    assert os.environ["TL_DEMO_SECRET"] not in listed, listed
    assert found["suggested"]["domain"] == "general"
    say(f"MCP: suggest_triage {found['suggested']['domain']}/{found['suggested']['subtype']}")
    again = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        item = again.get_correspondence(PROJECT, received)
        assert item.state == "Received" and len(item.clocks) == before, item.state
        pending = [
            x
            for x in again.list_proposals(SCOPE)
            if received in x.summary and x.status == "pending"
        ]
        assert len(pending) == 1, pending
    finally:
        again.close()
    say(f"MCP: propose_triage made a pending proposal ({pending[0].summary}); still Received")
    passed(
        7, "the API, the TUI and an agent read the same register; an agent's triage is a proposal"
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "make-eml":
        make_eml(sys.argv[2])
    elif mode == "clocks":
        clocks()
    elif mode == "hidden":
        hidden()
    elif mode == "reads":
        reads()
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
