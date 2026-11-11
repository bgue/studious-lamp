"""Driver for dev/demos/P2-PUNCH.sh: the clauses that are not a `tl` command.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`).
The API is the running `tl serve` at TL_API_URL, read with `ApiClient` as a person (a session token
from `sessions.sign_in`); the TUI runs `TlApp` over an `EmbeddedClient` and is reached by the
palette entry whose id is `punch`; the MCP tools run on a server built by `build_server` as the
actor named. Each mode prints one ``ok <what>`` line per check; the shell prints the
``PASS clause N`` line once the mode has returned. A miss prints ``FAIL <what>`` and exits 1.
Files the shell passes (the proposal id, the show text) live in ``P2_PUNCH_WORKDIR``.

Modes (first argument):

* ``clause5 KEY``: KEY is an item raised from a restricted correspondence item. As uma, the API
  answers KEY and the key of a missing item the same way (404, one text), the MCP get answers the
  same as for the missing key, and the MCP list lacks KEY; as the agent, the MCP get answers the
  same and the list lacks KEY.
* ``clause6 KEY IWP SHOW``: the API (as uma) gives the fields `tl punch show` printed (the file SHOW
  holds that output); the TUI log at 170x44, reached by the palette entry `punch`, shows KEY with
  its state; the MCP list and get (as uma) agree with the API; no clear or verify tool is an action.
* ``clause6-propose IWP PIDFILE``: the agent's propose_punch_item from IWP is pending; its proposal
  id is written to PIDFILE.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

from textual.widgets import Input
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_uow_factory
from tl_api.client import ApiClient
from tl_api.errors import ApiError
from tl_core import confidentiality as cf
from tl_core.auth import sessions
from tl_core.services.errors import RecordNotFoundError
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.server import build_server
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.punch_log import PunchLogScreen

PASSWORDS = {  # the documented dev passwords the shell seeds the people with
    "uma": "a long passphrase for uma",
    "sue": "a long passphrase for sue",
    "dora": "a long passphrase for dora",
}
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
AGENT = "agent:triage"  # an agent account: no person behind it, so it reads at the lowest class
MISSING = "P123-PUN-9999"  # a key that never existed
SCREEN_SIZE = (170, 44)
MODES = ("clause5", "clause6", "clause6-propose")
#: The state-changing tools that must never be an agent's action.
CLOSED_TOOLS = ("mcp.clear_punch_item", "mcp.verify_punch_item")


def ok(text: str) -> None:
    print(f"ok {text}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


class World:
    """The ledger in TL_DB, its API at TL_API_URL, and the people's sessions."""

    def __init__(self) -> None:
        self.target = as_target(os.environ["TL_DB"])
        self.backend = open_backend(self.target)
        self.workdir = Path(os.environ["P2_PUNCH_WORKDIR"])
        self.url = os.environ["TL_API_URL"]

    def viewer(self, actor: str) -> cf.Viewer:
        with self.backend(True) as uow:
            return cf.viewer_for_actor(uow.conn(), actor)

    def api(self, name: str) -> ApiClient:
        _, token = sessions.sign_in(self.backend, username=name, password=PASSWORDS[name])
        return ApiClient(self.url, token)

    def close(self) -> None:
        self.backend.close()


def mcp_server(world: World, actor: str) -> Any:
    """The MCP server for ``actor``; the punch tools are registered by build_server."""

    def allow(who: str, action: str, resource: str) -> None:
        if action not in MCP_ACTIONS:
            raise PermissionError(f"{action} is not allowed for {who}")

    return build_server(
        make_uow_factory(world.target),
        actor=actor,
        authorize_hook=allow,
        lake_dir=world.workdir / "lake",
    )


def mcp_call(server: Any, tool: str, **arguments: Any) -> Any:
    try:
        result = asyncio.run(server.call_tool(tool, arguments))
    except Exception as exc:  # a failed tool is raised by the server (ToolError), not returned
        raise RuntimeError(str(exc)) from exc
    if result.is_error:
        raise RuntimeError(" ".join(getattr(block, "text", "") for block in result.content))
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def mcp_read(world: World, actor: str, tool: str, **arguments: Any) -> Any:
    """A read tool as ``actor``: the viewer the MCP reads use is the actor's own."""
    with cf.use_viewer(world.viewer(actor)):
        return mcp_call(mcp_server(world, actor), tool, **arguments)


def mcp_error(world: World, actor: str, tool: str, **arguments: Any) -> str:
    """The error text a read tool gives as ``actor``; a call that succeeds is a miss."""
    try:
        mcp_read(world, actor, tool, **arguments)
    except RuntimeError as exc:
        return str(exc)
    miss(f"{tool} as {actor} answered {arguments} instead of an error")


def rows_of(page: Any) -> list[dict[str, Any]]:
    """The rows of a list result (a dict with ``rows``, or the list itself)."""
    if isinstance(page, dict) and "rows" in page:
        return list(page["rows"])
    return list(page)


def flat(detail: dict[str, Any]) -> dict[str, Any]:
    """A detail result with its row fields at the top level."""
    return {**detail.get("row", {}), **{k: v for k, v in detail.items() if k != "row"}}


def api_error(client: ApiClient, key: str) -> tuple[int, str]:
    """The status and text of the API's answer for ``key``. A 404 reaches the client as the
    service's RecordNotFoundError (status 404); other error bodies as ApiError."""
    try:
        client.get_punch_item(PROJECT, key)
    except RecordNotFoundError as exc:
        return 404, str(exc)
    except ApiError as exc:
        return exc.status, exc.message
    miss(f"the API answered {key} as a found item")


def without_key(text: str, key: str) -> str:
    return text.replace(key, "<key>")


async def _settle(pilot: Any) -> None:
    """Let the key press and the workers of a screen finish (as the TUI tests do)."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


def screen_text(app: Any) -> str:
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


def has_row(text: str, *cells: str) -> bool:
    return any(all(cell in line for cell in cells) for line in text.splitlines())


def tui_log_text(world: World, actor: str, key: str) -> str:
    """The text of the punch log reached from the palette, at 170 x 44, once it shows ``key``."""
    client = EmbeddedClient(world.backend, actor=actor)
    app = TlApp(client, scope=SCOPE, actor=actor)
    label = next(c.label for c in APP_COMMANDS if c.id == "punch")
    captured: dict[str, str] = {}

    async def scenario() -> None:
        async with app.run_test(size=SCREEN_SIZE) as pilot:
            await _settle(pilot)
            await pilot.press("ctrl+p")
            await _settle(pilot)
            app.screen.query_one("#palette-input", Input).value = label
            await _settle(pilot)
            await pilot.press("enter")
            for _ in range(150):
                await _settle(pilot)
                if isinstance(app.screen, PunchLogScreen) and has_row(screen_text(app), key):
                    break
                await pilot.pause(0.1)
            captured["screen"] = type(app.screen).__name__
            captured["text"] = screen_text(app)

    asyncio.run(scenario())
    check(
        captured.get("screen") == "PunchLogScreen", f"the palette did not open the log: {captured}"
    )
    return captured["text"]


def show_fields(show_file: Path) -> dict[str, str]:
    """The `label  value...` lines `tl punch show` printed, as label -> the cells after it."""
    fields: dict[str, str] = {}
    for line in show_file.read_text().splitlines():
        label, *cells = line.split("  ")
        if label in (
            "state",
            "subject",
            "category",
            "area",
            "system",
            "due",
            "assignee",
            "raised by",
            "raised from",
            "cleared",
            "verified",
        ):
            value = "  ".join(cells) if label == "subject" else (cells[0] if cells else "-")
            fields[label] = value
    return fields


def clause5(hidden: str) -> None:
    world = World()
    try:
        uma = world.api("uma")
        status_h, text_h = api_error(uma, hidden)
        status_m, text_m = api_error(uma, MISSING)
        check(status_h == 404 and status_m == 404, f"the API gave {status_h} and {status_m}")
        check(text_h == text_m, f"the API texts differ: {text_h!r} and {text_m!r}")
        ok(f"API as uma: {hidden} and {MISSING} both answer 404 '{text_h}'")
        for actor in ("user:uma", AGENT):
            tool_h = mcp_error(world, actor, "get_punch_item", project=PROJECT, key=hidden)
            tool_m = mcp_error(world, actor, "get_punch_item", project=PROJECT, key=MISSING)
            check(
                without_key(tool_h, hidden) == without_key(tool_m, MISSING),
                f"the MCP texts differ for {actor}: {tool_h!r} and {tool_m!r}",
            )
            listed = {
                r["key"]
                for r in rows_of(mcp_read(world, actor, "list_punch_items", project=PROJECT))
            }
            check(hidden not in listed, f"the MCP list as {actor} holds {hidden}")
            ok(f"MCP as {actor}: get answers as for a missing key; the list lacks {hidden}")
    finally:
        world.close()


def clause6(key: str, iwp: str, show_file: str) -> None:
    world = World()
    try:
        api = world.api("uma")
        detail = api.get_punch_item(PROJECT, key)
        shown = show_fields(Path(show_file))
        api_fields = {
            "state": detail.row.state,
            "subject": detail.row.subject,
            "category": detail.row.category,
            "area": detail.row.area or "-",
            "system": detail.row.system or "-",
            "due": detail.row.due_on or "-",
            "assignee": detail.row.assignee or "-",
            "raised by": detail.row.raised_by,
            "raised from": detail.row.source_key or "-",
            "cleared": detail.cleared_by or "-",
            "verified": detail.verified_by or "-",
        }
        for label, value in api_fields.items():
            check(
                shown.get(label) == value, f"{label}: the API {value!r}, show {shown.get(label)!r}"
            )
        ok(f"API as uma: {key} has the fields `tl punch show` prints (state {detail.row.state})")

        text = tui_log_text(world, "user:uma", key)
        check(has_row(text, key, "Verified"), f"the TUI log does not show {key} as Verified")
        ok(f"TUI at 170x44, palette entry punch: the log shows {key} as Verified")

        listed = [
            r
            for r in rows_of(mcp_read(world, "user:uma", "list_punch_items", project=PROJECT))
            if r["key"] == key
        ]
        check(len(listed) == 1 and listed[0]["state"] == "Verified", f"the MCP list row: {listed}")
        got = flat(mcp_read(world, "user:uma", "get_punch_item", project=PROJECT, key=key))
        check(
            got.get("state") == detail.row.state and got.get("subject") == detail.row.subject,
            f"the MCP get differs from the API: {got}",
        )
        ok(f"MCP as uma: list_punch_items and get_punch_item agree with the API on {key}")

        for name in CLOSED_TOOLS:
            check(name not in MCP_ACTIONS, f"{name} is an MCP action")
        ok("no MCP clear or verify tool is in MCP_ACTIONS")
    finally:
        world.close()


def clause6_propose(iwp: str, pid_file: str) -> None:
    world = World()
    try:
        server = mcp_server(world, AGENT)
        proposed = mcp_call(
            server,
            "propose_punch_item",
            project=PROJECT,
            subject="Gasket proposed by the agent",
            from_key=iwp,
        )
        pid = proposed["proposal"]["proposal_id"]
        check(proposed["proposal"]["status"] == "pending", f"the proposal is {proposed}")
        Path(pid_file).write_text(pid + "\n")
        ok(f"the agent's propose_punch_item is pending ({pid}) from {iwp}")
    finally:
        world.close()


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    handlers: dict[str, Callable[..., None]] = {
        "clause5": clause5,
        "clause6": clause6,
        "clause6-propose": clause6_propose,
    }
    if mode not in MODES:
        raise SystemExit(f"unknown mode {mode!r}; the modes are {', '.join(MODES)}")
    expected = {"clause5": 1, "clause6": 3, "clause6-propose": 2}[mode]
    if len(args) != expected:
        raise SystemExit(f"{mode} takes {expected} argument(s)")
    handlers[mode](*args)


if __name__ == "__main__":
    main(sys.argv)
