"""Driver for dev/demos/P2-INSP.sh: the clauses that are not a `tl` command.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`).
The API is the running `tl serve` at TL_API_URL, read with `ApiClient` as a person (a session token
from `sessions.sign_in`); the TUI runs `TlApp` over an `EmbeddedClient` and is reached by the
palette entry whose id is `inspections`; the MCP tools run on a server built by `build_server` as
the actor named. Each mode prints one ``ok <what>`` line per check; the shell prints the
``PASS clause N`` line once the mode has returned. A miss prints ``FAIL <what>`` and exits 1.
Files the shell passes (the proposal id, the show text, the list and export files) live in
``P2_INSP_WORKDIR``.

Modes (first argument):

* ``clause5 KEY``: KEY is an inspection planned on a record restricted from uma. As uma, the API
  answers KEY and the key of a missing inspection the same way (404, one text), the MCP get answers
  the same as for the missing key, and the MCP list lacks KEY; as the agent, the same.
* ``clause6 KEY SHOW``: the API (as uma) gives the fields `tl insp show` printed (the file SHOW
  holds that output); the TUI log at 170x44, reached by the palette entry `inspections`, shows KEY
  with its state; the MCP list and get (as uma) agree with the API; no record or verify tool is an
  action.
* ``clause6-propose IWP PIDFILE``: the agent's propose_inspection on IWP is pending; its proposal
  id is written to PIDFILE.
* ``export LS CSV JSONL``: the rows of `tl insp ls` (the file LS) and of `tl insp export` (CSV and
  JSONL) are the same rows, field by field.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
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
from tl_tui.widgets.inspection_log import InspectionLogScreen

PASSWORDS = {  # the documented dev passwords the shell seeds the people with
    "uma": "a long passphrase for uma",
    "sue": "a long passphrase for sue",
    "dora": "a long passphrase for dora",
}
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
AGENT = "agent:triage"  # an agent account: no person behind it, so it reads at the lowest class
MISSING = "P123-INS-9999"  # a key that never existed
SCREEN_SIZE = (170, 44)
EMPTY = "—"  # how `tl insp show` prints a field with no value
MODES = ("clause5", "clause6", "clause6-propose", "export")
#: The record and verify tools must never be an agent's action.
CLOSED_PREFIXES = ("mcp.record_", "mcp.verify_")


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
        self.workdir = Path(os.environ["P2_INSP_WORKDIR"])
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
    """The MCP server for ``actor``; the inspection tools are registered by build_server."""

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


def api_error(get: Callable[[str], object], key: str) -> tuple[int, str]:
    """The status and text of the API's answer for ``key``. A 404 reaches the client as the
    service's RecordNotFoundError (status 404); other error bodies as ApiError."""
    try:
        get(key)
    except RecordNotFoundError as exc:
        return 404, str(exc)
    except ApiError as exc:
        return exc.status, exc.message
    miss(f"the API answered {key} as a found inspection")


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
    """The text of the inspection log reached from the palette, at 170 x 44, once it shows key."""
    client = EmbeddedClient(world.backend, actor=actor)
    app = TlApp(client, scope=SCOPE, actor=actor)
    label = next(c.label for c in APP_COMMANDS if c.id == "inspections")
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
                if isinstance(app.screen, InspectionLogScreen) and has_row(screen_text(app), key):
                    break
                await pilot.pause(0.1)
            captured["screen"] = type(app.screen).__name__
            captured["text"] = screen_text(app)

    asyncio.run(scenario())
    check(
        captured.get("screen") == "InspectionLogScreen",
        f"the palette did not open the log: {captured}",
    )
    return captured["text"]


def show_fields(show_file: Path) -> dict[str, str]:
    """The state line and the `label  value` lines `tl insp show` printed, as label -> value."""
    lines = show_file.read_text().splitlines()
    fields: dict[str, str] = {"state": lines[1]}
    for line in lines[2:]:
        if len(line) > 16 and line[16:] and not line.startswith(" "):
            fields[line[:16].strip()] = line[16:].strip()
    return fields


def clause5(hidden: str) -> None:
    world = World()
    try:
        uma = world.api("uma")
        status_h, text_h = api_error(lambda k: uma.get_inspection(PROJECT, k), hidden)
        status_m, text_m = api_error(lambda k: uma.get_inspection(PROJECT, k), MISSING)
        check(
            status_h == 404 and status_m == 404,
            f"the API gave {status_h} ({text_h}) and {status_m} ({text_m})",
        )
        check(text_h == text_m, f"the API texts differ: {text_h!r} and {text_m!r}")
        ok(f"API as uma: {hidden} and {MISSING} both answer 404 '{text_h}'")
        for actor in ("user:uma", AGENT):
            tool_h = mcp_error(world, actor, "get_inspection", project=PROJECT, key=hidden)
            tool_m = mcp_error(world, actor, "get_inspection", project=PROJECT, key=MISSING)
            check(
                without_key(tool_h, hidden) == without_key(tool_m, MISSING),
                f"the MCP texts differ for {actor}: {tool_h!r} and {tool_m!r}",
            )
            listed = {
                r["key"]
                for r in rows_of(mcp_read(world, actor, "list_inspections", project=PROJECT))
            }
            check(hidden not in listed, f"the MCP list as {actor} holds {hidden}")
            ok(f"MCP as {actor}: get answers as for a missing key; the list lacks {hidden}")
    finally:
        world.close()


def clause6(key: str, show_file: str) -> None:
    world = World()
    try:
        api = world.api("uma")
        detail = api.get_inspection(PROJECT, key)
        row = detail.row
        shown = show_fields(Path(show_file))
        api_fields = {
            "state": row.state,
            "Point": row.point,
            "Subject": row.subject_key or EMPTY,
            "For": row.for_key or EMPTY,
            "Inspector": row.inspector or EMPTY,
            "Scheduled": row.scheduled_for or EMPTY,
            "Result": row.result or EMPTY,
            "Verified by": detail.verified_by or EMPTY,
            "Version": str(detail.version),
        }
        for label, value in api_fields.items():
            check(
                shown.get(label) == value, f"{label}: the API {value!r}, show {shown.get(label)!r}"
            )
        ok(f"API as uma: {key} has the fields `tl insp show` prints (state {row.state})")

        text = tui_log_text(world, "user:uma", key)
        check(has_row(text, key, row.state), f"the TUI log does not show {key} as {row.state}")
        ok(f"TUI at 170x44, palette entry inspections: the log shows {key} as {row.state}")

        listed = [
            r
            for r in rows_of(mcp_read(world, "user:uma", "list_inspections", project=PROJECT))
            if r["key"] == key
        ]
        check(
            len(listed) == 1 and listed[0]["state"] == row.state,
            f"the MCP list row: {listed}",
        )
        got = flat(mcp_read(world, "user:uma", "get_inspection", project=PROJECT, key=key))
        check(
            got.get("state") == row.state and got.get("point") == row.point,
            f"the MCP get differs from the API: {got}",
        )
        ok(f"MCP as uma: list_inspections and get_inspection agree with the API on {key}")

        closed = [a for a in MCP_ACTIONS if a.startswith(CLOSED_PREFIXES)]
        check(closed == [], f"record or verify tools are MCP actions: {closed}")
        check("mcp.list_inspections" in MCP_ACTIONS, "list_inspections is not an MCP action")
        ok("no MCP tool named record_* or verify_* is in MCP_ACTIONS")
    finally:
        world.close()


def clause6_propose(iwp: str, pid_file: str) -> None:
    world = World()
    try:
        server = mcp_server(world, AGENT)
        proposed = mcp_call(
            server,
            "propose_inspection",
            project=PROJECT,
            subject_key=iwp,
            title="Witness point proposed by the agent",
            point="witness",
        )
        pid = proposed["proposal"]["proposal_id"]
        check(proposed["proposal"]["status"] == "pending", f"the proposal is {proposed}")
        Path(pid_file).write_text(pid + "\n")
        ok(f"the agent's propose_inspection is pending ({pid}) on {iwp}")
    finally:
        world.close()


def dash(value: str | None) -> str:
    """The `tl insp ls` cell of a value: ``-`` for none."""
    return "-" if value is None or value == "" else value


def export_mode(ls_file: str, csv_file: str, jsonl_file: str) -> None:
    lines = Path(ls_file).read_text().splitlines()
    total = lines[-1] if lines else ""
    check(re.fullmatch(r"\d+ of \d+", total) is not None, f"the list has no total line: {total!r}")
    listed = [line.split("  ") for line in lines[:-1]]
    check(all(len(cells) == 9 for cells in listed), f"a list row has not nine cells: {listed}")
    exported_csv = list(csv.DictReader(io.StringIO(Path(csv_file).read_text())))
    exported_jsonl = [json.loads(line) for line in Path(jsonl_file).read_text().splitlines()]
    check(
        len(listed) == len(exported_csv) == len(exported_jsonl),
        f"row counts: ls {len(listed)}, csv {len(exported_csv)}, jsonl {len(exported_jsonl)}",
    )
    # `tl insp ls` cell index -> the export column it must equal (the title is not exported)
    pairs = (
        (0, "number"),
        (2, "state"),
        (3, "point"),
        (4, "subject"),
        (5, "for"),
        (6, "inspector"),
        (7, "scheduled"),
        (8, "result"),
    )
    for index, column in pairs:
        for cells, csv_row, json_row in zip(listed, exported_csv, exported_jsonl, strict=True):
            from_csv = dash(csv_row[column])
            from_json = dash(None if json_row[column] is None else str(json_row[column]))
            check(
                cells[index] == from_csv == from_json,
                f"{column}: ls {cells[index]!r}, csv {from_csv!r}, jsonl {from_json!r}",
            )
    ok(f"export: {len(listed)} rows; csv and jsonl agree with ls {total} on {len(pairs)} fields")


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    handlers: dict[str, Callable[..., None]] = {
        "clause5": clause5,
        "clause6": clause6,
        "clause6-propose": clause6_propose,
        "export": export_mode,
    }
    if mode not in MODES:
        raise SystemExit(f"unknown mode {mode!r}; the modes are {', '.join(MODES)}")
    expected = {"clause5": 1, "clause6": 2, "clause6-propose": 2, "export": 3}[mode]
    if len(args) != expected:
        raise SystemExit(f"{mode} takes {expected} argument(s)")
    handlers[mode](*args)


if __name__ == "__main__":
    main(sys.argv)
