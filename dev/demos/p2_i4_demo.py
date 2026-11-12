"""Driver for dev/demos/P2-I4.sh: the clause-4 checks that are not a `tl req` or `tl wo` command.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`)
and runs the API in process with the test client, the way dev/demos/p2_i3_demo.py does; the TUI
screens are reached through the command palette (`TlApp.action_palette`, the command ids of
`tl_tui.commands`) over an `EmbeddedClient`; the MCP tools run on a server built by `build_server`.
Each mode prints one ``PASS clause 4: <what was checked>`` line per check; a miss prints
``FAIL <what>`` and exits 1. The people are the ones the shell script seeded (documented dev
passwords, as in the P2-I3 demo). Token and lake files go to ``P2_I4_WORKDIR``.

Modes (first argument):

* ``clause4 CLI_STATE LABOUR_COUNT``: the state of P123-REQ-MAT-0001 that ``tl req show`` printed
  (CLI_STATE) is the state the API client, the palette screens and the MCP tools give; an agent's
  propose_requisition (labour, for the IWP) is pending and adds no row until uma accepts it, and
  then P123-REQ-LAB-<LABOUR_COUNT + 1> exists with requester user:uma. (No refusal check: no account
  on this ledger lacks requisitions.view, decision D-r3h.)
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

from fastapi.testclient import TestClient
from textual.widgets import Input
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_uow_factory
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_mcp.requisition_tools import REQUISITION_MCP_ACTIONS
from tl_mcp.server import build_server
from tl_tui.app import TlApp
from tl_tui.commands import command_by_id
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.requisition_register import RequisitionLogScreen
from tl_tui.widgets.work_order_backlog import WorkOrderBacklogScreen

PASSWORDS = {  # the documented dev passwords the script seeds the people with
    "uma": "a long passphrase for uma",
    "sue": "a long passphrase for sue",
}
PROJECT = "P123"
P123 = f"project:{PROJECT}"
AGENT = "agent:triage"  # the agent that proposes a labour requisition (no account; a proposal only)
IWP = "P123-IWP-PIP-0001"
MAT = "P123-REQ-MAT-0001"
WO = "P123-WO-0001"
SCREEN_SIZE = (170, 44)  # the width and height the clause names


def passed(clause: int, text_: str) -> None:
    print(f"PASS clause {clause}: {text_}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


class World:
    """The ledger in TL_DB, its API in process, and one signed-in test client per person."""

    def __init__(self) -> None:
        target = as_target(os.environ["TL_DB"])
        self.target = target
        self.backend = open_backend(target)
        workdir = Path(os.environ["P2_I4_WORKDIR"])
        self.workdir = workdir
        settings = ApiSettings(db_path=target, tokens_path=workdir / "tokens.json")
        self.app = create_app(
            self.backend, settings=settings, tokens=TokenStore(workdir / "tokens.json")
        )
        self.clients: dict[str, TestClient] = {}
        self.tokens: dict[str, str] = {}

    def token(self, name: str) -> str:
        if name not in self.tokens:
            _principal, token = sessions.sign_in(
                self.backend, username=name, password=PASSWORDS[name]
            )
            self.tokens[name] = token
            client = TestClient(self.app, raise_server_exceptions=False)
            client.headers.update({"Authorization": f"Bearer {token}"})
            self.clients[name] = client
        return self.tokens[name]

    def client(self, name: str) -> TestClient:
        self.token(name)
        return self.clients[name]

    def api(self, name: str) -> ApiClient:
        return ApiClient("http://testserver", self.token(name), http=self.client(name))

    def close(self) -> None:
        self.backend.close()


def allow(actor: str, action: str, resource: str) -> None:
    """The MCP authorise hook of this demo: the requisition tools are allowed to the actor.

    Every other action is refused, as the authorise hook of a real agent does (ADR-0009).
    """
    if action not in REQUISITION_MCP_ACTIONS:
        raise PermissionError(f"{action} is not allowed for {actor}")


def mcp_server(world: World, actor: str) -> Any:
    lake = world.workdir / "lake"
    return build_server(
        make_uow_factory(world.target), actor=actor, authorize_hook=allow, lake_dir=lake
    )


def mcp_call(server: Any, tool: str, **arguments: Any) -> Any:
    result = asyncio.run(server.call_tool(tool, arguments))
    if result.is_error:
        raise RuntimeError(" ".join(getattr(block, "text", "") for block in result.content))
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def has_row(screen: str, *cells: str) -> bool:
    """Some line of a screen holds the cells, in this order."""
    pattern = r".*".join(re.escape(cell) for cell in cells)
    return any(re.search(pattern, line) for line in screen.splitlines())


async def settle(pilot: Any) -> None:
    """Let the key press and the workers of a screen finish (as the TUI tests do)."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


def screen_text(app: Any) -> str:
    """The rendered screen as plain text, one line per terminal row."""
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


def palette_screen(
    world: World,
    actor: str,
    command_id: str,
    text_filter: str,
    ready: Callable[[str], bool],
) -> tuple[type[Any], str]:
    """Open the screen of a palette command by its id, as a person would: the palette
    (``action_palette``) is opened, the command's label typed, and Enter pressed; then the log's
    filter box (``#log-filter``) takes ``text_filter``. Returns the class of the screen that opened
    and its text at 170 x 44 once ``ready`` holds (a bounded wait)."""
    label = command_by_id(command_id)
    check(label is not None, f"the palette has no command {command_id}")
    assert label is not None
    client = EmbeddedClient(world.backend, actor=actor)
    app = TlApp(client, scope=P123, actor=actor)
    captured: dict[str, Any] = {}

    async def scenario() -> None:
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await settle(pilot)
            app.action_palette()
            await settle(pilot)
            app.screen.query_one("#palette-input", Input).value = label.label
            await settle(pilot)
            await pilot.press("enter")
            await settle(pilot)
            app.screen.query_one("#log-filter", Input).value = text_filter
            await settle(pilot)
            for _ in range(150):  # the log reads its rows in a worker; wait for the rows
                if ready(screen_text(app)):
                    break
                await pilot.pause(0.1)
            previous, same = "", 0
            for _ in range(200):  # and until the table has been drawn (the text is stable)
                await settle(pilot)
                await pilot.pause(0.2)
                current = screen_text(app)
                same = same + 1 if current == previous else 0
                previous = current
                if same >= 5:
                    break
            captured["class"] = type(app.screen)
            captured["text"] = previous

    asyncio.run(scenario())
    return captured["class"], captured["text"]


def clause4(cli_state: str, labour_count: str) -> None:
    """One state over the API, the palette screens and MCP; the agent's proposal waits for uma."""
    n = int(labour_count)
    world = World()
    try:
        api = world.api("uma")
        detail = api.get_requisition(PROJECT, MAT)
        check(
            detail.row.state == cli_state,
            f"the API says {detail.row.state}, tl req show {cli_state}",
        )
        listed = {r.key: r for r in api.list_requisitions(PROJECT, kind="material").rows}
        check(MAT in listed and listed[MAT].state == cli_state, f"the API list lacks {MAT}")
        passed(
            4,
            f"API get_requisition and list_requisitions agree with tl req show: {MAT} {cli_state}",
        )

        cls, text = palette_screen(
            world,
            "user:uma",
            "requisitions",
            MAT,
            ready=lambda t: has_row(t, MAT, cli_state),
        )
        check(
            cls is RequisitionLogScreen,
            f"the palette opened {cls.__name__}, not the requisition log",
        )
        check(
            has_row(text, MAT, cli_state), f"the requisition log lacks {MAT} {cli_state}:\n{text}"
        )
        cls, text = palette_screen(
            world,
            "user:uma",
            "requisitions",
            "P123-REQ-LAB-000",
            ready=lambda t: has_row(t, "P123-REQ-LAB-0002", "Cancelled"),
        )
        for key, state in (("P123-REQ-LAB-0001", "Rejected"), ("P123-REQ-LAB-0002", "Cancelled")):
            check(has_row(text, key, state), f"the requisition log lacks {key} {state}:\n{text}")
        passed(
            4,
            f"TUI palette 'requisitions' (170x44) shows {MAT} {cli_state} and the two labour keys",
        )

        cls, text = palette_screen(
            world,
            "user:uma",
            "work-orders",
            WO,
            ready=lambda t: has_row(t, WO, "Closed"),
        )
        check(cls is WorkOrderBacklogScreen, f"the palette opened {cls.__name__}, not the backlog")
        check(has_row(text, WO, "Closed"), f"the work order backlog lacks {WO} Closed:\n{text}")
        passed(4, f"TUI palette 'work-orders' (170x44) shows {WO} Closed")

        agent = mcp_server(world, AGENT)
        mcp_list = mcp_call(agent, "list_requisitions", project=PROJECT)
        pairs = sorted((r["key"], r["state"]) for r in mcp_list)
        api_pairs = sorted((r.key, r.state) for r in api.list_requisitions(PROJECT).rows)
        check(pairs == api_pairs, f"MCP list {pairs} differs from the API {api_pairs}")
        mcp_get = mcp_call(agent, "get_requisition", project=PROJECT, key=MAT)
        check(mcp_get["row"]["state"] == cli_state, f"MCP get says {mcp_get['row']['state']}")
        passed(
            4, f"MCP list_requisitions ({len(pairs)} rows) and get_requisition agree with the API"
        )

        before = len(api.list_requisitions(PROJECT, kind="labor").rows)
        proposed = mcp_call(
            agent,
            "propose_requisition",
            project=PROJECT,
            kind="labor",
            subject="Pipefitters, agent proposal",
            for_key=IWP,
            craft="Pipefitter",
            headcount=4,
            start_date="2026-11-16",
            end_date="2026-11-20",
        )
        pid = proposed["proposal"]["proposal_id"]
        check(proposed["proposal"]["status"] == "pending", f"the proposal is {proposed}")
        after = len(api.list_requisitions(PROJECT, kind="labor").rows)
        check(after == before, f"the proposal added a labour row: {before} to {after}")
        passed(4, f"an agent's propose_requisition ({pid}) is pending and adds no requisition row")

        accepted = world.client("uma").post(
            f"/proposals/{pid}/accept", params={"scope": P123}, json={}
        )
        check(
            accepted.status_code == 200,
            f"uma's accept: {accepted.status_code} {accepted.text[:160]}",
        )
        next_key = f"P123-REQ-LAB-{n + 1:04d}"
        made = api.get_requisition(PROJECT, next_key).row
        check(made.requester == "user:uma", f"{next_key} has requester {made.requester}")
        check(made.kind == "labor", f"{next_key} is {made.kind}")
        passed(4, f"uma accepts the proposal: {next_key} exists, requester user:uma")
    finally:
        world.close()


MODES = {"clause4": clause4}


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    if mode not in MODES:
        raise SystemExit(f"usage: p2_i4_demo.py {'|'.join(MODES)} [ARGS]")
    expected = {"clause4": 2}[mode]
    if len(args) != expected:
        raise SystemExit(f"{mode} takes {expected} argument(s)")
    MODES[mode](*args)


if __name__ == "__main__":
    main(sys.argv)
