"""Driver for dev/demos/P2-I2.sh: the clauses of the demo that are not a `tl` command.

Modes (first argument):

* ``receiver DIR``: a webhook receiver on a free loopback port until killed. It writes its port to
  ``DIR/receiver.port``, picks up its signing secret from ``DIR/receiver.secret`` when that file
  appears, and appends every POST it handled to ``DIR/receiver.log`` (one JSON object per line).
* ``propose IWP ITEM``: clause 8: an agent's ``propose_iwp_scope`` over MCP is pending, and ITEM is
  not on IWP yet. The proposal id is written to TL_DEMO_STATE for the script to accept as a person.
* ``received DIR IWP``: clause 4: the receiver verified an ``IWP.Ready`` event for IWP.
* ``screens IWP``: clause 9: the API, MCP, the TUI (IWP log, the IWP's readiness screen and the
  constraint log, reached through the palette at 170x44) and the web pages show IWP the same way.
* ``publish KEY``: clause 3: sue publishes the derived take-off KEY as MTO lines (the API).
* ``locations``: clause 3: sue (a materials superuser) defines the place stock is received into.
* ``oversize NUMBER``: clause 7: the TUI backlog's sizing view (key ``z``) flags NUMBER over size.
* ``backlog``: clause 9: the TUI backlog tile shows weeks per foreman.

Reads TL_DB (SQLite path or postgresql:// URL), TL_DEMO_URL (the API), TL_DEMO_AGENT_TOKEN and
TL_DEMO_STATE. Every expectation is an assert: a failing check exits non-zero. Nothing printed holds
a password or a token.
"""

from __future__ import annotations

import asyncio
import importlib
import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO_PASSWORD = "demo"  # the documented dev account (ADR-0009 section 9)
SIZE = (170, 44)


def say(text: str) -> None:
    print(f"   {text}")


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
            assert {"propose_iwp_scope", "get_iwp_readiness", "list_iwps"} <= names, names
            result = await mcp.call_tool(name, arguments)
            assert not result.is_error and result.structured_content is not None, result
            return result.structured_content

    return asyncio.run(session())


# --- clause 4: the receiver ----------------------------------------------------------------------


def receiver(directory: str) -> None:
    from tl_core.webhooks.receiver import DevReceiver

    out = Path(directory)
    seen = 0
    with DevReceiver() as server:
        (out / "receiver.port").write_text(str(server.port))
        secret_file = out / "receiver.secret"
        loaded = ""
        while True:
            if secret_file.exists():
                value = secret_file.read_text().strip()
                if value and value != loaded:
                    server.set_secrets([value])
                    loaded = value
            messages = server.messages()
            if len(messages) > seen:
                with (out / "receiver.log").open("a") as log:
                    for message in messages[seen:]:
                        log.write(
                            json.dumps(
                                {
                                    "path": message.path,
                                    "verified": message.verified,
                                    "duplicate": message.duplicate,
                                    "event": message.event(),
                                }
                            )
                            + "\n"
                        )
                seen = len(messages)
            import time

            time.sleep(0.1)


def received(directory: str, iwp: str) -> None:
    log = Path(directory, "receiver.log")
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    ready = [
        r
        for r in rows
        if r["verified"] and iwp in json.dumps(r["event"]) and "IWP.Ready" in json.dumps(r["event"])
    ]
    assert ready, f"the receiver verified no IWP.Ready for {iwp}: {len(rows)} POSTs"
    say(f"the receiver verified {len(ready)} IWP.Ready POST(s) for {iwp}")


# --- clause 8: the agent's proposal --------------------------------------------------------------


def propose(number: str, item: str) -> None:
    found = agent_session(
        "propose_iwp_scope",
        {"project": PROJECT, "iwp": number, "items": [item]},
    )
    proposal = found["proposal"]
    assert proposal["status"] == "pending", proposal
    assert proposal["tool"] == "propose_iwp_scope", proposal
    Path(os.environ["TL_DEMO_STATE"]).write_text(proposal["proposal_id"])
    say(f"the agent's proposal {proposal['proposal_id']} is pending; {item} is not on {number}")


# --- clause 9: the same state on every surface ---------------------------------------------------


def _api():
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    return ApiClient(url, sign_in(url, "demo", DEMO_PASSWORD).token)


def _web() -> Any:
    """A web client signed in as the demo account; its cookie is the session (no bearer token)."""
    import httpx

    url = os.environ["TL_DEMO_URL"]
    client = httpx.Client(base_url=url, headers={"Origin": url}, follow_redirects=False)
    response = client.post("/web/sign-in", data={"username": "demo", "password": DEMO_PASSWORD})
    assert response.status_code == 303, f"web sign-in answered {response.status_code}"
    return client


# the palette matches a command on its label; these words pick the one entry (no punctuation)
LABELS = {
    "iwps": "IWP log installation",
    "constraints": "Constraint log open",
    "backlog": "Backlog IWPs by view",
}
SCREENS = {
    "iwps": ("tl_tui.widgets.iwp_register", "IwpRegisterScreen"),
    "constraints": ("tl_tui.widgets.constraint_screen", "ConstraintScreen"),
    "backlog": ("tl_tui.widgets.backlog_screen", "BacklogScreen"),
}


async def _open(app: Any, pilot: Any, entry: str, minimum: int) -> Any:
    """Type the palette entry's label, press Enter, and wait for the screen's rows to load."""
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


async def _readiness_tui(number: str) -> bool:
    """The IWP log (palette), its first row's screen (Enter), then its readiness (key ``r``)."""
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.iwp_register import IwpScreen
    from tl_tui.widgets.readiness_screen import ReadinessScreen

    client = EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo", is_admin=True)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await _open(app, pilot, "iwps", 1)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, IwpScreen), f"enter opened {type(app.screen).__name__}"
            await pilot.press("r")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ReadinessScreen), f"r opened {type(screen).__name__}"
            for _ in range(100):
                await pilot.pause(0.05)
                if screen.rows:
                    break
            rows = [" ".join(c) for c in _cells(screen)]
            say(f"TUI readiness of {number}: {len(rows)} checks from the IWP screen")
            norm = [row.lower().replace("_", " ") for row in rows]
            return any("documents current" in row and " ok" in row for row in norm)
    finally:
        client.close()


async def _tui(entry: str, minimum: int, inspect: Callable[[Any], Any]) -> Any:
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


def _cells(screen: Any) -> list[list[str]]:
    return [list(screen.row_cells(row)) for row in screen.rows]


def screens(number: str) -> None:
    api = _api()
    try:
        detail = api.get_iwp(PROJECT, number)
        listed = {i.number for i in api.list_iwps(PROJECT)}
        readiness = api.get_iwp_readiness(PROJECT, number).model_dump_json()
    finally:
        api.close()
    assert number in listed, f"the API lists no {number}"
    assert detail.state == "Issued", f"the API shows {detail.state}"
    assert "documents_current" in readiness and '"ok"' in readiness, "the API readiness differs"
    say(f"API: {number} {detail.state}; readiness checks read back")

    mcp_iwps = agent_session("list_iwps", {"project": PROJECT})
    assert number in json.dumps(mcp_iwps), f"MCP list_iwps shows no {number}"
    mcp_ready = agent_session("get_iwp_readiness", {"project": PROJECT, "number": number})
    assert "documents_current" in json.dumps(mcp_ready), "MCP readiness differs"
    say(f"MCP: list_iwps and get_iwp_readiness read {number}")

    def register(screen: Any) -> dict[str, Any]:
        rows = _cells(screen)
        return {"found": any(cells and cells[0] == number for cells in rows)}

    assert asyncio.run(_tui("iwps", 1, register))["found"], f"the IWP log shows no {number}"
    assert asyncio.run(_readiness_tui(number)), f"the TUI readiness of {number} names no check"

    def constraints(screen: Any) -> dict[str, Any]:
        return {"rows": len(screen.rows)}

    assert asyncio.run(_tui("constraints", 1, constraints))["rows"] >= 1, "no constraint row"
    say("TUI: the IWP log and the constraint log, from the palette, show the same records")

    web = _web()
    try:
        page = web.get(f"/web/p/{PROJECT}/iwps")
        assert page.status_code == 200 and number in page.text, f"web iwps: {page.status_code}"
        ready_page = web.get(f"/web/p/{PROJECT}/readiness", params={"number": number})
        assert ready_page.status_code == 200, f"web readiness: {ready_page.status_code}"
        assert "Documents current" in ready_page.text, "the web readiness page names no check"
        cons = web.get(f"/web/p/{PROJECT}/constraints")
        assert cons.status_code == 200, f"web constraints: {cons.status_code}"
    finally:
        web.close()
    say("web: the IWP log, the readiness page and the constraint page answer for the same records")


def backlog() -> None:
    def tile(screen: Any) -> dict[str, Any]:
        return {"panel": plain(screen.panel_text(None)), "rows": _cells(screen)}

    shown = asyncio.run(_tui("backlog", 1, tile))
    text = " ".join(" ".join(c) for c in shown["rows"]) + shown["panel"]
    assert "user:frank" in text or "frank" in text, f"the backlog shows no foreman: {text[:200]}"
    assert "weeks" in text, "the backlog shows no weeks"
    say("backlog tile: weeks of ready work per foreman, from the palette")


def locations() -> None:
    """Clause 3's stock needs a place: sue (a materials superuser) defines the chain via the API."""
    import httpx
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    token = sign_in(url, "sue", "a long passphrase for sue").token
    chain = [
        ("P123", "Project P123 site", "project", None),
        ("WH1", "Main warehouse", "warehouse", "P123"),
        ("L2", "Laydown 2", "laydown", "WH1"),
    ]
    with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}) as client:
        for code, title, kind, parent in chain:
            body = {
                "scope": SCOPE,
                "code": code,
                "title": title,
                "kind": kind,
                "parent_code": parent,
            }
            made = client.post("/commands/DefineLocation", json=body)
            assert made.status_code == 200, f"DefineLocation {code}: {made.status_code}"
    say("sue defined the location chain P123 > WH1 > L2")


def publish(key: str) -> None:
    """Clause 3: sue publishes the derived take-off as an MTO through the API (no work package yet:
    the lines are assigned to the IWP by `tl mat mto assign`)."""
    import httpx
    from tl_adapters.db import open_uow
    from tl_api.client.auth import sign_in
    from tl_mod_documents.derivation import views as derivation_views

    with open_uow(os.environ["TL_DB"], readonly=True) as uow:
        found = derivation_views.find_derived(uow.conn(), SCOPE, key)
    url = os.environ["TL_DEMO_URL"]
    token = sign_in(url, "sue", "a long passphrase for sue").token
    with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}) as client:
        made = client.post(
            "/commands/PublishDerivedMto",
            json={
                "scope": SCOPE,
                "derived_id": found.id,
                "expected_content_rev": found.content_rev,
            },
        )
    assert made.status_code == 200, f"PublishDerivedMto: {made.status_code} {made.text[:200]}"
    say(f"sue published {key} as take-off lines")


async def _sizing(number: str) -> dict[str, Any]:
    """The backlog from the palette, then its sizing view (key ``z``): rows outside the bounds."""
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient

    client = EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo", is_admin=True)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            screen = await _open(app, pilot, "backlog", 1)
            await pilot.press("z")
            await pilot.pause(0.2)
            rows = [" ".join(_cells(screen)[i]) for i in range(len(screen.rows))]
            found = {"rows": rows, "panel": plain(screen.panel_text(None))}
            await pilot.press("escape")
            await pilot.pause()
            return found
    finally:
        client.close()


def oversize(number: str) -> None:
    found = asyncio.run(_sizing(number))
    text = " ".join(found["rows"]) + found["panel"]
    assert number in text, f"the sizing view shows no {number}: {text[:200]}"
    assert "over size" in text, "the sizing view shows no 'over size' flag"
    say(f"sizing view: {number} is over size (the hours are outside awp.iwp.size_hours)")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "oversize":
        oversize(sys.argv[2])
        return
    if mode == "locations":
        locations()
        return
    if mode == "publish":
        publish(sys.argv[2])
        return
    if mode == "receiver":
        receiver(sys.argv[2])
    elif mode == "propose":
        propose(sys.argv[2], sys.argv[3])
    elif mode == "received":
        received(sys.argv[2], sys.argv[3])
    elif mode == "screens":
        screens(sys.argv[2])
    elif mode == "backlog":
        backlog()
    else:
        sys.exit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
