"""The Phase 0 screenshot tour: what the platform core does, shown on a seeded demo ledger.

    uv run python dev/tour/phase0.py [--out docs/reports/tour/phase-0]

It builds a fresh SQLite ledger in a temporary directory (`tl init --dev`, a made-up piping and
valves project `P123`, named people and one agent), then

* drives the real TUI headless with Textual's pilot and saves SVG screenshots of the key screens;
* runs the real `tl` commands, an API client, an MCP server and a webhook receiver in this process
  and renders what they print as terminal SVGs.

Everything is local: no network, no secrets (the documented dev account `demo` / `demo`), no
personal data. The clock and the ULIDs are frozen (see `tourkit.py`), so a second run writes the
same bytes. A step that does not do what the tour says it does raises, and the run fails.

The text of the tour is `docs/reports/PHASE-0-TOUR.md`; its section numbers match the file names
here (`01-...` to `13-...`).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import shlex
import shutil
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import tourkit as tk
from textual.pilot import Pilot
from textual.widgets import Input
from tourkit import Transcript, Workspace, expect

REPO = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
P = ("--project", PROJECT)
AMY = ("--actor", "user:amy")  # a design engineer
RAJ = ("--actor", "user:raj")  # the lead engineer
DEMO = ("--actor", "user:demo")  # the admin of the dev setup
RECEIVER_PORT = 18099
QUERY = "(conformance:warning OR conformance:nonconformant) psets.valve_data.size_in>=3"


# --- running and showing commands ------------------------------------------------------------


class Session:
    """Runs `tl` commands and keeps what a transcript should show."""

    def __init__(self, ws: Workspace) -> None:
        self.ws = ws

    def run(self, *argv: str, ok: bool = True, stdin: str | None = None) -> tuple[str, str]:
        """Run `tl <argv>`; return ``(the line a person types, what it printed)``."""
        output = self.ws.tl(*argv, ok=ok, stdin=stdin)
        shown = self.ws.clean("tl " + shlex.join(argv))
        return shown, output

    def quiet(self, *argv: str, ok: bool = True, stdin: str | None = None) -> str:
        return self.ws.tl(*argv, ok=ok, stdin=stdin)


# --- the seeded project ----------------------------------------------------------------------


def seed(ws: Workspace) -> None:
    """A small piping and valves project: records, psets, one workflow, posts. Not shown."""
    s = Session(ws)
    s.quiet("init", "--dev")
    s.quiet("login", "demo", stdin="demo\n")
    tk.CLOCK.advance(minutes=20)
    # Numbered records (the shot of the numbering is made by `section_numbering`).
    s.quiet("record", "create", *P, "--title", "NCR: weld porosity", *AMY)
    s.quiet("record", "create", *P, "--title", "Weld map WM-12", *AMY)
    valves = [
        ("FV-1001", "Feed ctrl valve"),
        ("FV-1002", "Reflux valve"),
        ("HV-2001", "Suction isolation"),
        ("HV-2002", "Discharge check"),
        ("XV-3001", "ESD valve"),
        ("PSV-4001", "Relief valve"),
    ]
    for key, title in valves:
        s.quiet("record", "create", *P, "--key", key, "--title", title, *AMY)
    s.quiet(
        "pset",
        "set",
        *P,
        "FV-1001",
        "valve_data",
        "size_in=4",
        "body_material=SS316L",
        "manufacturer=Acme Flow",
        "tag_no=FV-1001",
        "fail_action=FC",
        *AMY,
    )
    s.quiet(
        "pset",
        "set",
        *P,
        "FV-1001",
        "valve_data",
        "--layer",
        "custom",
        "x.fat_witness_by=client",
        *AMY,
    )
    s.quiet("pset", "set", *P, "FV-1002", "valve_data", "size_in=6", "body_material=XX", *AMY)
    s.quiet(
        "pset",
        "set",
        *P,
        "HV-2001",
        "valve_data",
        "size_in=8",
        "body_material=CS",
        "manufacturer=Beta Valves",
        "tag_no=HV-2001",
        *AMY,
    )
    s.quiet(
        "pset",
        "set",
        *P,
        "HV-2002",
        "valve_data",
        "size_in=6",
        "body_material=SS316L",
        "manufacturer=Beta Valves",
        "tag_no=HV-2002",
        *AMY,
    )
    s.quiet(
        "pset",
        "set",
        *P,
        "XV-3001",
        "valve_data",
        "size_in=10",
        "body_material=DUPLEX",
        "manufacturer=Acme Flow",
        "fail_action=FC",
        "tag_no=XV-3001",
        *AMY,
    )
    s.quiet("pset", "set", *P, "PSV-4001", "valve_data", "size_in=3", "body_material=CS", *AMY)
    s.quiet("wf", "transition", *P, "P123-REC-0001", "submit", *AMY)
    s.quiet(
        "feed",
        "post",
        *P,
        "FV-1002 body material must be corrected to SS316L before FAT #FV-1002 #hold",
        "--importance",
        "high",
        *AMY,
    )
    s.quiet(
        "feed", "post", *P, "Weld map WM-12 rev B is out for the NCR #P123-REC-0002 #decision", *RAJ
    )
    tk.CLOCK.advance(minutes=30)


# --- 01 records and numbering ----------------------------------------------------------------


def section_numbering(ws: Workspace) -> None:
    """Keys come from the numbering service, in the transaction that creates the record."""
    sh = tk.Shell(ws, "A key from the numbering service", 150)
    sh.note("the two records were created without a key: the numbering pattern gave their keys")
    sh.run("record", "show", *P, "P123-REC-0001")
    sh.run("events", "tail", *P, "-n", "4")
    ws.save("01b-numbering-cli", sh.transcript.svg())
    keys = events_of(ws, "Numbering.Allocated")
    expect(keys == ["P123-REC-0001", "P123-REC-0002"], f"numbering gave {keys}")


# --- the TUI tour ----------------------------------------------------------------------------


def grid_of(app: Any) -> Any:
    from tl_tui.widgets.grid import RecordGrid

    return app.query_one("#grid", RecordGrid)


async def back_to_grid(pilot: Pilot[Any], app: Any) -> None:
    """Escape out of a record view (or a panel) until the grid is showing."""
    for _ in range(4):
        if len(app.query("RecordView")) == 0 and "Key" in tk.screen_text(app):
            break
        await pilot.press("escape")
        await tk.settle(pilot, 3)
    await tk.until(pilot, lambda: len(app.query("RecordView")) == 0, "the grid")


async def open_record(pilot: Pilot[Any], app: Any, key: str) -> None:
    """From the grid: move to the row with ``key`` and open it."""
    grid = grid_of(app)
    keys = [row["key"] for row in grid.rows]
    expect(key in keys, f"{key} is not in the grid: {keys}")
    await pilot.press("home")
    await tk.settle(pilot, 2)
    for _ in range(keys.index(key)):
        await pilot.press("down")
    await tk.settle(pilot, 2)
    await pilot.press("enter")
    await tk.until(pilot, lambda: len(app.query("RecordView")) > 0, f"the record view of {key}")
    await tk.until(pilot, lambda: key in tk.screen_text(app), f"{key} on screen")


async def open_tab(pilot: Pilot[Any], tab: str, app: Any, needle: str) -> None:
    await pilot.press(tab)
    await tk.until(pilot, lambda: needle in tk.screen_text(app), f"{needle!r} on the {tab} tab")


async def tui_tour(ws: Workspace, pilot: Pilot[Any], app: Any) -> None:
    await tk.until(pilot, lambda: bool(grid_of(app).rows), "the grid rows")
    await tk.until(pilot, lambda: "FV-1001" in tk.screen_text(app), "the grid on screen")

    # 01 the record grid
    tk.shot_tui(
        ws,
        app,
        "01a-record-grid",
        "Throughline: the record grid",
        "FV-1001",
        "nonconformant",
        "P123-REC-00",
    )

    # 02 psets and conformance
    await open_record(pilot, app, "FV-1001")
    await open_tab(pilot, "2", app, "Nominal size")
    tk.shot_tui(
        ws,
        app,
        "02a-psets-conforming",
        "Psets of FV-1001: company standard, project extension",
        "Valve data",
        "Body material",
        "FAT witness",
    )
    await back_to_grid(pilot, app)
    await open_record(pilot, app, "FV-1002")
    await open_tab(pilot, "2", app, "Nominal size")
    tk.shot_tui(
        ws,
        app,
        "02b-psets-nonconformant",
        "Psets of FV-1002: a value outside its code list",
        "nonconformant",
        "XX",
    )
    await pilot.press("e")
    await tk.until(
        pilot,
        lambda: "Save" in tk.screen_text(app) or "ctrl+s" in tk.screen_text(app).lower(),
        "the edit form",
    )
    tk.shot_tui(
        ws,
        app,
        "02c-edit-form",
        "The edit form is generated from the effective schema",
        "Nominal size",
    )
    await pilot.press("escape")
    await tk.settle(pilot, 4)

    # 03 links and expected links, 04 workflow
    await back_to_grid(pilot, app)
    await open_record(pilot, app, "P123-REC-0001")
    await open_tab(pilot, "3", app, "expected but missing")
    tk.shot_tui(
        ws,
        app,
        "03a-links-expected-missing",
        "A link the workflow expects is missing",
        "expected but missing: supporting record",
    )
    await pilot.press("w")
    await tk.until(pilot, lambda: "blocked" in tk.screen_text(app), "the workflow menu")
    tk.shot_tui(
        ws,
        app,
        "04a-workflow-blocked",
        "Approve is blocked until the expected link exists",
        "Approve",
        "blocked",
        "expected_links",
    )
    await pilot.press("escape")
    await tk.settle(pilot, 4)
    tk.CLOCK.advance(minutes=15)
    await pilot.press("l")
    await tk.until(pilot, lambda: len(app.screen.query("#picker-search")) > 0, "the link picker")
    app.screen.query_one("#picker-search", Input).value = "WM-12"
    await tk.until(pilot, lambda: "P123-REC-0002" in tk.screen_text(app), "the picker's result")
    tk.shot_tui(
        ws,
        app,
        "03b-link-picker",
        "Link this record: search by key or title",
        "WM-12",
        "P123-REC-0002",
    )
    await pilot.press("enter")
    await tk.until(pilot, lambda: "expected but missing" not in tk.screen_text(app), "the new link")
    await tk.settle(pilot, 4)
    tk.shot_tui(
        ws,
        app,
        "03c-links-satisfied",
        "The link exists, so the expectation is met",
        "P123-REC-0002",
    )
    tk.CLOCK.advance(minutes=5)
    await pilot.press("w")
    await tk.until(pilot, lambda: "State: Review" in tk.screen_text(app), "the workflow menu again")
    await tk.settle(pilot, 4)
    tk.shot_tui(
        ws,
        app,
        "04b-workflow-allowed",
        "The same menu once the link is there",
        "Approve",
        "allowed",
    )
    await pilot.press("enter")
    await tk.until(pilot, lambda: "Approved" in tk.screen_text(app), "the transition")
    await tk.settle(pilot, 4)
    await open_tab(pilot, "4", app, "Transitioned")
    tk.shot_tui(
        ws,
        app,
        "04c-workflow-history",
        "The transition is an event in the record's history",
        "Approved",
    )
    await open_tab(pilot, "5", app, "P123-REC-0002")
    tk.shot_tui(
        ws,
        app,
        "03d-trace",
        "Trace: the records reachable through links",
        "P123-REC-0001",
        "P123-REC-0002",
    )
    await back_to_grid(pilot, app)

    # 05 one query language: the filter bar
    await pilot.press("slash")
    await tk.settle(pilot, 3)
    app.screen.query_one("#filter-input", Input).value = QUERY
    await pilot.press("enter")
    await tk.until(pilot, lambda: "matches" in tk.screen_text(app), "the filter result")
    tk.shot_tui(
        ws,
        app,
        "05a-filter-bar",
        "The filter bar speaks the query language",
        "psets.valve_data.size_in>=3",
        "2 matches",
        technical=True,  # the bar echoes the query text the person typed, with its field paths
    )
    await pilot.press("slash")  # focus the bar, clear it, apply, then close it
    await tk.settle(pilot, 2)
    app.screen.query_one("#filter-input", Input).value = ""
    await pilot.press("enter")
    await tk.settle(pilot, 6)
    await pilot.press("slash", "escape")
    await tk.settle(pilot, 3)
    expect(
        "matches" not in tk.screen_text(app),
        "the filter bar is still open:\n" + tk.screen_text(app),
    )

    # 06 the feed
    await pilot.press("F")
    await tk.until(
        pilot,
        lambda: "Feed" in tk.screen_text(app) and "#hold" in tk.screen_text(app),
        "the feed pane",
    )
    tk.shot_tui(
        ws,
        app,
        "06a-feed-pane",
        "The project feed: posts and aggregated event cards",
        "amy",
        "raj",
        "created",
        "set properties",
    )
    await pilot.press("p")
    await tk.until(pilot, lambda: len(app.screen.query("#composer-input")) > 0, "the composer")
    app.screen.query_one("#composer-input", Input).value = "Hydrotest slipped to Thursday #FV-10"
    await tk.until(
        pilot, lambda: "FV-1001" in tk.screen_text(app).split("New post")[-1], "tag suggestions"
    )
    tk.shot_tui(
        ws,
        app,
        "06b-composer",
        "The composer completes tags from the services",
        "New post",
        "FV-1001",
    )
    await pilot.press("escape", "escape")  # the suggestions, then the composer
    await tk.until(
        pilot, lambda: len(app.screen.query("#composer-input")) == 0, "the composer to close"
    )

    # 11 about:config
    await pilot.press("f9")
    await tk.until(pilot, lambda: "about:config" in tk.screen_text(app), "about:config")
    await tk.until(pilot, lambda: "feed.signal_tags" in tk.screen_text(app), "the settings rows")
    tk.shot_tui(
        ws,
        app,
        "11a-about-config",
        "about:config: every setting, where its value comes from, who locked it",
        "feed.reactions.enabled",
        "locked",
        "project",
    )
    await pilot.press("escape")
    await tk.settle(pilot, 3)


def configure(ws: Workspace) -> list[tuple[str, str]]:
    """The settings story of section 11 (run before the TUI tour, which shows its result)."""
    s = Session(ws)
    steps = [
        s.run(
            "config",
            "set",
            "webhooks.retry.max_hours",
            "12",
            "--company",
            "--reason",
            "retries stop after 12 h (customer SLA)",
            *DEMO,
        ),
        s.run(
            "config",
            "lock",
            "feed.reactions.enabled",
            "--reason",
            "reactions are part of the audit trail",
            *DEMO,
        ),
        s.run("config", "set", "feed.reactions.enabled", "false", *P, *RAJ, ok=False),
        s.run("config", "set", "feed.signal_tags", "safety,hold,decision,ncr,fat", *P, *RAJ),
        s.run("config", "get", "feed.signal_tags", *P, "--long"),
        s.run("config", "history", "feed.signal_tags"),
    ]
    ws.shot_cli("11b-config-cli", "tl config: layers, locks and reasons", steps, width=120)
    return steps


# --- 06 live updates -------------------------------------------------------------------------


async def live_tour(ws: Workspace, pilot: Pilot[Any], app: Any) -> None:
    await tk.until(pilot, lambda: bool(grid_of(app).rows), "the live grid rows")
    await tk.until(pilot, lambda: "FV-1001" in tk.screen_text(app), "the live grid on screen")
    tk.CLOCK.advance(minutes=10)
    s = Session(ws)
    await asyncio.to_thread(
        s.quiet, "pset", "set", *P, "HV-2001", "valve_data", "body_material=SS316L", *RAJ
    )
    grid = grid_of(app)

    def marked() -> bool:
        row = next((r for r in grid.rows if r["key"] == "HV-2001"), None)
        return row is not None and grid.is_marked(row["id"])

    await tk.until(pilot, marked, "the grid to mark the record changed elsewhere", timeout=10)
    tk.shot_tui(
        ws,
        app,
        "06c-live-change-elsewhere",
        "Another writer changed HV-2001: this screen repainted and marked it",
        "HV-2001",
    )


# --- 05 the same query through the API and MCP -----------------------------------------------


def section_query(ws: Workspace, server: Any) -> None:
    from fastapi.testclient import TestClient
    from tl_api.app import create_app
    from tl_api.backend import open_backend
    from tl_api.settings import ApiSettings

    settings = ApiSettings.from_env()
    backend = open_backend(settings.db_path)
    try:
        client = TestClient(create_app(backend, settings=settings))
        sign_in = client.post("/auth/sign-in", json={"username": "demo", "password": "demo"})
        expect(sign_in.status_code == 200, f"sign-in answered {sign_in.status_code}")
        headers = {"Authorization": "Bearer " + sign_in.json()["token"]}
        query = QUERY
        got = client.get("/records", params={"scope": SCOPE, "q": query}, headers=headers)
        expect(got.status_code == 200, f"/records answered {got.status_code}")
        rows = got.json()
        count = client.get("/records/count", params={"scope": SCOPE, "q": query}, headers=headers)
        t = Transcript("The same query over the REST API (in-process client)", 120)
        t.comment("sign in as the dev account demo; the token is kept out of this transcript")
        t.command("POST /auth/sign-in  {username: demo, password: ...}")
        t.output(f"{sign_in.status_code} OK  (a 12-hour session token)")
        t.blank()
        t.command(f"GET /records?scope={SCOPE}&q={query}")
        t.output(f"{got.status_code} OK  {len(rows)} record(s)")
        for row in rows:
            p = row["psets"]["valve_data"]
            t.output(
                f"  {row['key']:<9} {row['title']:<18} size_in={p.get('size_in')}  "
                f"conformance={row['conformance']}  v{row['version']}"
            )
        t.blank()
        t.command(f"GET /records/count?scope={SCOPE}&q=status:null")
        n = client.get(
            "/records/count", params={"scope": SCOPE, "q": "status:null"}, headers=headers
        )
        t.output(f"{n.status_code} OK  {n.json()}")
        ws.save("05b-query-api", t.svg())
        expect(count.status_code == 200, "count failed")
        expect(len(rows) >= 1, "the API query found nothing")
    finally:
        backend.close()
    found = asyncio.run(tk.call_tool(server, "search_records", scope=SCOPE, q=QUERY))
    expect(
        {r["key"] for r in found["records"]} == {r["key"] for r in rows},
        "MCP and the API answered the same query differently",
    )
    m = Transcript("The same query through MCP: the read tool search_records", 120)
    m.comment("the agent acts through its own token; reading needs no proposal")
    m.command(f'mcp tools/call search_records {{scope: "{SCOPE}", q: "{QUERY}"}}')
    m.output(f"total {found['total']}")
    for record in found["records"]:
        p = record["psets"]["valve_data"]
        m.output(
            f"  {record['key']:<9} {record['title']:<18} size_in={p.get('size_in')}  "
            f"conformance={record['conformance']}  v{record['version']}"
        )
    m.blank()
    m.comment("the TUI filter bar, the REST API and this tool are one parser and one executor")
    ws.save("05c-query-mcp", m.svg())


# --- 07 agent proposals ----------------------------------------------------------------------


def section_proposals(ws: Workspace, server: Any, token: str) -> None:
    from fastapi.testclient import TestClient
    from tl_api.app import create_app
    from tl_api.backend import open_backend
    from tl_api.client import ApiClient
    from tl_api.errors import ApiError
    from tl_api.settings import ApiSettings
    from tl_core.services.commands import CreateRecord

    t = Transcript("An agent proposes over MCP; a person decides", 120)
    t.comment("an admin made the agent account and issued it a token (shown once, hidden here)")
    t.command("tl admin user add triage --kind agent")
    t.command("tl admin token issue triage --label 'triage assistant'")
    t.output("tla_...  (kept by the agent's host, read from TL_AGENT_TOKEN)")
    t.blank()
    tools = asyncio.run(server.list_tools())
    names = sorted(tool.name for tool in tools)
    for forbidden in ("accept_proposal", "reject_proposal"):
        expect(forbidden not in names, f"an agent has the tool {forbidden}")
    t.command("mcp tools/list   (as agent:triage)")
    t.output(" ".join(names))
    t.output("no accept_proposal, no reject_proposal: an agent cannot decide")
    t.blank()
    found = asyncio.run(tk.call_tool(server, "search_records", scope=SCOPE, q="key:FV-1002"))
    t.command(f'mcp tools/call search_records {{scope: "{SCOPE}", q: "key:FV-1002"}}')
    record = found["records"][0]
    t.output(
        f"total {found['total']}: {record['key']} {record['title']} v{record['version']} "
        f"conformance={record['conformance']}"
    )
    t.blank()
    proposed = asyncio.run(
        tk.call_tool(
            server,
            "update_psets",
            record="FV-1002",
            scope=SCOPE,
            pset="valve_data",
            layer="standard",
            values={"body_material": "SS316L", "manufacturer": "Acme Flow"},
        )
    )
    proposal = proposed["proposal"]
    t.command(
        'mcp tools/call update_psets {record: "FV-1002", pset: "valve_data", '
        'values: {body_material: "SS316L", manufacturer: "Acme Flow"}}'
    )
    t.output(f"status: {proposal['status']}   proposal: {proposal['proposal_id']}")
    t.output(f"summary: {proposal['summary']}")
    t.output(proposed["message"])
    after = asyncio.run(tk.call_tool(server, "get_record", record="FV-1002", scope=SCOPE))
    expect(after["version"] == record["version"], "the agent's proposal changed the record")
    t.blank()
    t.command('mcp tools/call get_record {record: "FV-1002"}')
    t.output(
        f"version {after['version']} (unchanged), body_material "
        f"{after['psets']['valve_data'].get('body_material')!r}"
    )
    t.blank()
    queue = ws.tl("proposal", "ls", *P)
    t.command(f"tl proposal ls --project {PROJECT}")
    t.output(queue)
    pid = proposal["proposal_id"]
    t.command(f"tl proposal show {pid}")
    t.output(ws.tl("proposal", "show", pid))
    t.command(f"tl proposal accept {pid} --actor user:raj")
    t.output(ws.tl("proposal", "accept", pid, *RAJ))
    settings = ApiSettings.from_env()
    backend = open_backend(settings.db_path)
    try:
        http = TestClient(create_app(backend, settings=settings), raise_server_exceptions=False)
        robot = ApiClient("http://testserver", token, http=http)
        try:
            robot.create_record(
                CreateRecord(
                    actor="agent:triage",
                    source="api",
                    scope=SCOPE,
                    record_type="core.Record",
                    title="Direct write",
                )
            )
        except ApiError as exc:
            refusal = f"{exc.status} {exc.error}"
        else:
            raise tk.TourFailed("an agent token created a record directly")
    finally:
        backend.close()
    t.blank()
    t.command("POST /commands/CreateRecord   (with the agent's token)")
    t.output(f"refused: {refusal}")
    t.blank()
    t.command("tl events tail --project P123 -n 3")
    tail = ws.tl("events", "tail", *P, "-n", "3")
    t.output(tail)
    expect("Pset.ValuesSet" in tail, "the accepted proposal wrote no pset event")
    record_view = ws.tl("pset", "get", *P, "FV-1002")
    expect("SS316L" in record_view, "the accepted proposal did not change the psets")
    t.command("tl pset get --project P123 FV-1002")
    t.output(record_view)
    ws.save("07-agent-proposals", t.svg())


# --- 08 webhooks -----------------------------------------------------------------------------


class Receiver:
    """A loopback HTTP server that knows only the Standard Webhooks recipe, not our signing code."""

    def __init__(self) -> None:
        self.key = b""
        self.good: list[dict[str, Any]] = []
        self.bad = 0
        lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (the http.server API)
                body = self.rfile.read(int(self.headers.get("content-length", 0))).decode()
                message_id = self.headers.get("webhook-id", "")
                stamp = self.headers.get("webhook-timestamp", "0")
                mac = hmac.new(outer.key, f"{message_id}.{stamp}.{body}".encode(), hashlib.sha256)
                wanted = base64.b64encode(mac.digest()).decode()
                offered = [
                    part.split(",", 1)[1]
                    for part in self.headers.get("webhook-signature", "").split()
                    if "," in part
                ]
                ok = any(hmac.compare_digest(wanted, got) for got in offered)
                with lock:
                    if ok:
                        outer.good.append(
                            {"id": message_id, "stamp": stamp, "event": json.loads(body)}
                        )
                    else:
                        outer.bad += 1
                self.send_response(200 if ok else 401)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

        try:  # a fixed port keeps the subscription event, and so the hash chain, the same
            self.server = ThreadingHTTPServer(("127.0.0.1", RECEIVER_PORT), Handler)
        except OSError:
            print(f"warning: port {RECEIVER_PORT} is busy; the archive digests will differ")
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.port}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def section_webhook(ws: Workspace) -> None:
    s = Session(ws)
    receiver = Receiver()
    try:
        t = Transcript("A signed webhook to an external receiver (loopback)", 120)
        t.comment("the receiver is a few lines of standard-library Python on 127.0.0.1")
        cmd, out = s.run(
            "webhook",
            "add",
            "--name",
            "Site system",
            "--url",
            receiver.url,
            *P,
            "--event-type",
            "Pset.ValuesSet",
        )
        secret = next(line for line in out.splitlines() if line.startswith("secret "))
        receiver.key = base64.b64decode(secret.split()[1].removeprefix("whsec_"))
        t.command(cmd)
        t.output(tk.redact(out, "secret "))
        before = len(receiver.good)
        mix = [
            ("pset", "set", *P, "FV-1002", "valve_data", "size_in=6.5", *AMY),
            ("record", "create", *P, "--key", "FV-1003", "--title", "Bypass valve", *AMY),
            ("pset", "set", *P, "FV-1003", "valve_data", "size_in=2", *AMY),
            ("feed", "post", *P, "Bypass valve FV-1003 added #FV-1003", *AMY),
        ]
        for argv in mix:
            cmd, out = s.run(*argv)
            t.command(cmd)
            t.output(out)
        cmd, out = s.run("webhook", "run", "--once", "--allow-host", "127.0.0.1")
        t.command(cmd)
        t.output(out)
        cmd, out = s.run("webhook", "ls", *P)
        t.command(cmd)
        t.output(out)
        sent = sorted(receiver.good[before:], key=lambda item: item["event"]["tlseq"])
        expect(receiver.bad == 0, f"the receiver rejected {receiver.bad} deliveries")
        expect(len(sent) == 2, f"expected 2 deliveries, got {len(sent)}")
        types = {item["event"]["type"] for item in sent}
        expect(types == {"tl.core.Pset.ValuesSet.v1"}, f"the filter let {types} through")
        t.blank()
        t.comment("what the receiver saw: it recomputed each HMAC-SHA256 itself and they matched")
        for item in sent:
            event = item["event"]
            t.output(f"webhook-id {item['id']}  signature verified")
            t.output(
                f"  type {event['type']}  tlseq {event['tlseq']}  tlactor {event['tlactor']}  "
                f"subject {event['subject']}"
            )
        t.output(
            "not delivered: Record.Created and the feed post (they do not match the subscription)"
        )
        ws.save("08-webhook-delivery", t.svg())
    finally:
        receiver.close()


# --- 09 archive, verify, restore -------------------------------------------------------------


def section_archive(ws: Workspace) -> None:
    s = Session(ws)
    tk.fixed_archive_key()
    t = Transcript("A signed, hash-chained archive and a restore from it alone", 130)
    for argv in (
        ("ledger", "verify"),
        ("archive", "keygen", "--key", "archive.key"),
        ("archive", "seal", "--archive", "archive", "--key", "archive.key", "--max-events", "20"),
        ("archive", "verify", "--archive", "archive", "--public-key", "archive.pub"),
    ):
        cmd, out = s.run(*argv)
        t.command(cmd)
        t.output(out)
    # Tamper with a copy: change one byte of a payload in the second segment.
    shutil.copytree("archive", "tampered")
    segments = sorted(Path("tampered", "segments").iterdir())
    victim = segments[-1] / "events.ndjson"
    victim.chmod(0o644)
    data = victim.read_bytes()
    marker = b"Beta Valves" if b"Beta Valves" in data else b"FV-1002"
    victim.write_bytes(data.replace(marker, marker[:-1] + b"x", 1))
    t.blank()
    t.comment("flip one byte of one payload in a COPY of the archive (Beta Valves to Beta Valvex)")
    t.comment("then verify the copy")
    cmd, out = s.run(
        "archive", "verify", "--archive", "tampered", "--public-key", "archive.pub", ok=False
    )
    t.command(cmd)
    t.output(out, error=True)
    expect("divergence" in out, "the tampered archive did not report a divergence")
    cmd, out = s.run(
        "restore", "--from-archive", "archive", "--db", "restored.db", "--public-key", "archive.pub"
    )
    t.blank()
    t.command(cmd)
    t.output(out)
    columns = "seq, event_id, stream_id, event_type, payload, recorded_at, hash"
    original = sqlite3.connect(ws.db).execute(f"SELECT {columns} FROM events ORDER BY seq")
    restored = sqlite3.connect("restored.db").execute(f"SELECT {columns} FROM events ORDER BY seq")
    a, b = original.fetchall(), restored.fetchall()
    expect(a == b, "the restored events differ from the original")
    keys = "SELECT key, title, status, version FROM cur_core_record ORDER BY key"
    expect(
        sqlite3.connect(ws.db).execute(keys).fetchall()
        == sqlite3.connect("restored.db").execute(keys).fetchall(),
        "the restored current state differs",
    )
    t.output(f"checked: {len(b)} restored events identical to the original, current state equal")
    ws.save("09-archive-verify-restore", t.svg())


# --- 10 the lake -----------------------------------------------------------------------------


def section_lake(ws: Workspace) -> None:
    s = Session(ws)
    t = Transcript("The analytics copy: DuckLake, synced by ledger sequence", 120)
    sql = (
        "SELECT conformance, count(*) AS records, round(avg(pset__valve_data__size_in), 1) "
        "AS avg_size_in FROM cur_core_record WHERE key LIKE '%V-%' GROUP BY conformance "
        "ORDER BY conformance"
    )
    steps = [
        ("lake", "sync"),
        ("lake", "status"),
        ("lake", "query", sql),
        (
            "lake",
            "query",
            "SELECT event_type, count(*) AS n FROM events GROUP BY event_type "
            "ORDER BY n DESC, event_type LIMIT 6",
        ),
    ]
    for argv in steps:
        cmd, out = s.run(*argv)
        t.command(cmd)
        t.output(out)
    for refused in ("DROP TABLE events", "SELECT * FROM read_csv('/etc/passwd')"):
        cmd, out = s.run("lake", "query", "--", refused, ok=False)
        t.command(cmd)
        t.output(out, error=True)
    ws.save("10-lake-query", t.svg())


# --- 12 extension record types ---------------------------------------------------------------


def section_types(ws: Workspace) -> None:
    s = Session(ws)
    shutil.copytree(REPO / "schema" / "fixtures" / "types", "types")
    t = Transcript("A company record type from a folder of files", 120)
    steps = [
        s.run("types", "sync", "types"),
        s.run("types", "sync", "types"),
        s.run("types", "ls"),
        s.run("types", "show", "co.acme.SafetyObservation@1.0.0"),
        s.run("config", "get", "co.acme.lift_plan.max_load_tonnes", "--long"),
    ]
    for cmd, out in steps:
        t.command(cmd)
        t.output(out if out.strip() else "(nothing to register: the second sync is a no-op)")
    ws.save("12a-extension-types-cli", t.svg())


async def types_tour(ws: Workspace, pilot: Pilot[Any], app: Any) -> None:
    await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the type grid")
    await pilot.press("n")
    await tk.until(
        pilot, lambda: "New co.acme.SafetyObservation" in tk.screen_text(app), "the generated form"
    )
    await tk.settle(pilot, 4)
    tk.shot_tui(
        ws,
        app,
        "12b-extension-type-form",
        "A new SafetyObservation: the form is generated from the type's files",
        "Observed on",
        "Severity",
        "Location",
    )


# --- 13 parity and exit evidence -------------------------------------------------------------


def section_parity(ws: Workspace) -> None:
    t = Transcript("Evidence kept from the Phase 0 gates (stored, not re-run by this tour)", 120)
    t.comment(
        "figures copied from docs/reports/PHASE-0.md section 3; the runs take 30 minutes or more"
    )
    t.command("just test-parity")
    t.output("2166 passed on SQLite and Postgres, no skips (32 m 39 s)")
    t.command("just test")
    t.output("5302 passed, 1 skipped, 16 deselected (19 m 49 s)")
    t.command("just test-tui")
    t.output("608 passed, 26 snapshots (3 m 56 s)")
    t.command("just demo P0-I8")
    t.output("PASS exit-1 TUI / API / MCP, exit-2 live, exit-3 webhook, exit-4 restore, ... (84 s)")
    ws.save("13-parity-and-gates", t.svg())


# --- the tour --------------------------------------------------------------------------------


def events_of(ws: Workspace, event_type: str) -> list[str]:
    rows = sqlite3.connect(ws.db).execute(
        "SELECT payload FROM events WHERE event_type = ? ORDER BY seq", (event_type,)
    )
    return [json.loads(row[0]).get("key", "") for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/reports/tour/phase-0")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    tk.freeze()
    ws = Workspace(out)
    try:
        print("seeding the demo ledger", flush=True)
        seed(ws)
        section_numbering(ws)
        configure(ws)

        from tl_tui.main import build_app

        app = build_app(ws.db, PROJECT, live=False, actor="user:demo", is_admin=True)
        print("the TUI tour", flush=True)
        tk.run_tui(ws, app, lambda pilot: tui_tour(ws, pilot, app))

        live = build_app(ws.db, PROJECT, live=True, actor="user:demo")
        print("live updates", flush=True)
        tk.run_tui(ws, live, lambda pilot: live_tour(ws, pilot, live))

        print("the other doors: API, MCP, webhooks", flush=True)
        server, agent_backend, token = tk.agent_server(ws, "triage")
        section_query(ws, server)
        section_proposals(ws, server, token)
        agent_backend.close()
        section_webhook(ws)
        section_archive(ws)
        section_lake(ws)
        section_types(ws)
        typed = build_app(
            ws.db, PROJECT, live=False, actor="user:demo", record_type="co.acme.SafetyObservation"
        )
        tk.run_tui(ws, typed, lambda pilot: types_tour(ws, pilot, typed), size=(140, 60))
        section_parity(ws)
    finally:
        ws.close()
    print(f"wrote {len(ws.written)} screenshots to {out}")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
