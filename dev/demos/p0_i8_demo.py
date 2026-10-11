"""Driver for dev/demos/P0-I8.sh: the Phase 0 exit (brief 16) on a simulated project.

The script has started `tl serve` over a temporary ledger and seeded a simulated project
(`project:sim-exit`). This driver shows, and asserts, the four exit clauses. Each ends in a
`PASS` line, and any failure prints `DEMO FAILED` and exits non-zero:

  exit-1  create, link and set psets on a generic record through the TUI (Textual Pilot, headless,
          against the server), the REST API and MCP (an agent proposes, a person accepts);
  exit-2  live updates between two TUIs: two remote clients on one server, one writes, the other
          repaints within the 2 s of brief 15;
  exit-3  an external receiver (a stdlib HTTP server in this file that knows only the Standard
          Webhooks recipe, not our signing code) gets a signed event for a filtered subscription;
  exit-4  a full restore: the ledger archive is sealed and verified, replayed into a new database,
          and the restored `cur_*` state equals the original (SQLite, and Postgres when reachable).

Extras: a setting changed through the API applies to the running server without a restart, and a
tampered archive is refused.

Environment (set by the script): TL_DB, TL_API_URL, TL_TOKENS, TL_DEMO_WORK, TL_DEMO_SCOPE and the
TL_DEMO_TOKEN_* variables. Every `tl` call is a subprocess, as a person would type it.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mcp_types import CallToolResult
from sqlalchemy import text
from textual.pilot import Pilot
from textual.widgets import Input
from tl_adapters.db import make_engine, read_tx
from tl_adapters.postgres import admin
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.client import ApiClient
from tl_api.errors import ApiError
from tl_core.projection.defaults import default_registry
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.feed import PostToFeed
from tl_core.services.feed_actions import ReactToPost
from tl_core.services.links import AddLink
from tl_core.services.psets import SetPsetValues
from tl_mcp.server import build_server
from tl_tui.app import TlApp
from tl_tui.remote import RemoteClient
from tl_tui.widgets.edit_form import EditForm, editor_id
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.link_picker import LinkPicker
from tl_tui.widgets.new_record_form import NewRecordForm
from tl_tui.widgets.record_view import RecordView
from tl_tui.widgets.settings_screen import SettingsScreen

URL = os.environ["TL_API_URL"]
DB = os.environ["TL_DB"]
WORK = Path(os.environ["TL_DEMO_WORK"])
SCOPE = os.environ["TL_DEMO_SCOPE"]
PROJECT = SCOPE.split(":", 1)[1]
ALICE = os.environ["TL_DEMO_TOKEN_ALICE"]
BOB = os.environ["TL_DEMO_TOKEN_BOB"]
AGENT = os.environ["TL_DEMO_TOKEN_TRIAGE"]
LIVE_BUDGET_S = 2.0  # brief 15: a change is visible to other clients in under 2 s
KEY_TUI, KEY_API, KEY_MCP = "EXIT-TUI-1", "EXIT-API-1", "EXIT-MCP-1"
REQUIRED = (
    "exit-1 TUI",
    "exit-1 API",
    "exit-1 MCP",
    "exit-2 live",
    "exit-3 webhook",
    "exit-4 restore",
    "settings live",
)

passes: list[str] = []


def say(message: str) -> None:
    print(f"   {message}", flush=True)


def step(title: str) -> None:
    print(f"\n== {title}", flush=True)


def passed(clause: str, message: str) -> None:
    passes.append(clause)
    print(f"PASS {clause}: {message}", flush=True)


def fail(message: str) -> None:
    print(f"DEMO FAILED: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def expect(condition: object, message: str) -> None:
    if not condition:
        fail(message)


async def until(
    predicate: Callable[[], object], timeout: float, what: str, pilot: Pilot[Any] | None = None
) -> float:
    """Wait for ``predicate()`` to hold; return the seconds it took. Fails the demo on a timeout."""
    start = time.monotonic()
    while not predicate():
        expect(time.monotonic() - start < timeout, f"timed out waiting for {what}")
        if pilot is not None:
            await pilot.pause(0.02)
        else:
            await asyncio.sleep(0.02)
    return time.monotonic() - start


def screen_text(app: TlApp) -> str:
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


def run_tl(*args: str, expect_failure: bool = False) -> str:
    """Run `tl <args>` in a subprocess and return its stdout.

    A non-zero exit fails the demo (or, with ``expect_failure``, a zero exit does). Lines that
    start with ``secret`` are never echoed.
    """
    done = subprocess.run(
        ["uv", "run", "tl", *args], env=os.environ, capture_output=True, text=True, check=False
    )
    shown = [ln for ln in done.stdout.splitlines() if not ln.startswith("secret ")]
    errors = [ln for ln in done.stderr.splitlines() if "UV_NATIVE_TLS" not in ln]
    if expect_failure:
        expect(done.returncode != 0, f"tl {' '.join(args)} should have failed")
    else:
        expect(
            done.returncode == 0,
            f"tl {' '.join(args)} exited {done.returncode}: {' '.join(errors or shown)}",
        )
    first = (shown or errors or [""])[0]
    say(f"$ tl {' '.join(args)}" + (f"\n       {first[:150]}" if first else ""))
    return done.stdout


def fields(output: str) -> dict[str, str]:
    """The `name value` lines of a tl command's output."""
    found: dict[str, str] = {}
    for line in output.splitlines():
        name, _, value = line.partition(" ")
        found[name] = value
    return found


# --- an external receiver that knows only the Standard Webhooks recipe -----------------------


class ExternalReceiver:
    """A loopback HTTP server standing in for an external system (decision D14).

    It checks each POST the way the Standard Webhooks specification describes (HMAC-SHA256 of
    ``<id>.<timestamp>.<body>`` with the base64 key after ``whsec_``, a timestamp within five
    minutes) using only the standard library, so a pass does not rest on our own signing code.
    """

    def __init__(self) -> None:
        self.key = b""
        self.good: list[dict[str, Any]] = []
        self.bad: list[str] = []
        self._lock = threading.Lock()
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (the http.server API)
                body = self.rfile.read(int(self.headers.get("content-length", 0))).decode()
                message_id = self.headers.get("webhook-id", "")
                stamp = self.headers.get("webhook-timestamp", "0")
                mac = hmac.new(
                    receiver.key, f"{message_id}.{stamp}.{body}".encode(), hashlib.sha256
                )
                wanted = base64.b64encode(mac.digest()).decode()
                header = self.headers.get("webhook-signature", "")
                offered = [part.split(",", 1)[1] for part in header.split() if "," in part]
                fresh = abs(time.time() - int(stamp)) < 300
                ok = fresh and any(hmac.compare_digest(wanted, got) for got in offered)
                with receiver._lock:
                    if ok:
                        receiver.good.append({"id": message_id, "event": json.loads(body)})
                    else:
                        receiver.bad.append(message_id)
                self.send_response(200 if ok else 401)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def set_secret(self, whsec: str) -> None:
        self.key = base64.b64decode(whsec.removeprefix("whsec_"))

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


# --- read-only helpers over the ledger file --------------------------------------------------


def ledger_rows(sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        return conn.execute(sql, params).fetchall()


def head_seq() -> int:
    return int(ledger_rows("SELECT COALESCE(MAX(seq), 0) FROM events")[0][0])


def grid_row(grid: RecordGrid, key: str) -> dict[str, Any] | None:
    return next((row for row in grid.rows if row["key"] == key), None)


def psets_of(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("psets") or {}


def valve_data(record: dict[str, Any]) -> dict[str, Any]:
    found = psets_of(record).get("valve_data", {})
    return found if isinstance(found, dict) else {}


# --- exit-1 and exit-2: the TUI, the API, MCP, and a second TUI ------------------------------


async def tui_create_link_pset(
    app: TlApp, pilot: Pilot[Any], api: ApiClient, link_to: dict[str, Any]
) -> dict[str, Any]:
    """In the TUI: `n` creates a record, `l` links it, `e` sets a title and psets."""
    await pilot.press("n")
    await pilot.pause()
    form = app.screen
    expect(isinstance(form, NewRecordForm), "the new-record form did not open")
    form.query_one("#new_key Input", Input).value = KEY_TUI
    form.query_one("#new_title Input", Input).value = "Exit demo gate valve"
    await pilot.pause()
    await pilot.press("ctrl+s")
    await until(lambda: api.get_record(SCOPE, KEY_TUI) is not None, 5, "the new record", pilot)
    await until(lambda: len(app.query(RecordView)) == 1, 5, "the record view", pilot)
    record = api.get_record(SCOPE, KEY_TUI)
    assert record is not None

    await pilot.press("l")
    await pilot.pause()
    expect(isinstance(app.screen, LinkPicker), "the link picker did not open")
    app.screen.query_one("#picker-search", Input).value = link_to["key"]
    await pilot.pause(0.5)
    await pilot.press("enter")
    await until(lambda: len(api.links_of(record["id"])) >= 1, 5, "the link", pilot)

    await pilot.press("e")
    await pilot.pause()
    edit = app.screen
    expect(isinstance(edit, EditForm), "the edit form did not open")
    edit.query_one(f"#{editor_id('title')} Input", Input).value = "Exit demo gate valve (edited)"
    size = edit.query_one(f"#{editor_id('psets.valve_data.size_in')} Input", Input)
    size.value = "4"
    maker = edit.query_one(f"#{editor_id('psets.valve_data.manufacturer')} Input", Input)
    maker.value = "Acme"
    await pilot.pause()
    await pilot.press("ctrl+s")
    await until(
        lambda: (
            (api.get_record(SCOPE, KEY_TUI) or {}).get("title") == "Exit demo gate valve (edited)"
        ),
        5,
        "the saved edit",
        pilot,
    )
    saved = api.get_record(SCOPE, KEY_TUI)
    assert saved is not None
    return saved


async def clause_tui(
    app_a: TlApp, pilot_a: Pilot[Any], alice: ApiClient, target: dict[str, Any]
) -> dict[str, Any]:
    step("exit-1 (TUI): user:alice creates, links and sets psets with the keys n, l and e")
    record = await tui_create_link_pset(app_a, pilot_a, alice, target)
    links = alice.links_of(record["id"])
    kinds = [event.event_type for event in alice.history(record["id"])]
    say(f"{KEY_TUI}: {record['title']!r}, {len(links)} link, valve_data {valve_data(record)}")
    say("events: " + ", ".join(kinds))
    expect(len(links) == 1, "the TUI link is missing")
    expect(valve_data(record).get("manufacturer") == "Acme", "the TUI pset value is missing")
    expect(kinds[0] == "Record.Created" and "Pset.ValuesSet" in kinds, "events are missing")
    passed(
        "exit-1 TUI",
        f"{KEY_TUI} created, linked to {target['key']} and given psets in the TUI",
    )
    return record


async def clause_live(grid_b: RecordGrid, pilot_b: Pilot[Any], alice: ApiClient) -> dict[str, Any]:
    step("exit-2: the second TUI (user:bob) shows what the first one did, within 2 s")
    await until(
        lambda: (
            (row := grid_row(grid_b, KEY_TUI)) is not None
            and row["title"].endswith("(edited)")
            and grid_b.is_marked(row["id"])
        ),
        LIVE_BUDGET_S + 3,
        "the second TUI to show the first one's edit",
        pilot_b,
    )
    say("bob's grid has the record alice created in her TUI, marked as changed elsewhere")
    current = alice.get_record(SCOPE, KEY_TUI)
    assert current is not None
    started = time.monotonic()
    alice.update_record(
        UpdateRecord(
            actor="user:alice",
            source="api",
            scope=SCOPE,
            stream_id=current["id"],
            expected_version=current["version"],
            changes={"title": "Exit demo gate valve (rev B)"},
        )
    )
    await until(
        lambda: (row := grid_row(grid_b, KEY_TUI)) is not None and row["title"].endswith("(rev B)"),
        LIVE_BUDGET_S,
        "the second TUI to repaint",
        pilot_b,
    )
    latency = time.monotonic() - started
    expect(latency < LIVE_BUDGET_S, f"the live update took {latency:.2f} s")
    passed(
        "exit-2 live",
        f"bob's TUI repainted {latency * 1000:.0f} ms after alice's write (budget 2000 ms)",
    )
    refreshed = alice.get_record(SCOPE, KEY_TUI)
    assert refreshed is not None
    return refreshed


async def clause_api(
    alice: ApiClient, grid_b: RecordGrid, pilot_b: Pilot[Any], target: dict[str, Any]
) -> None:
    step("exit-1 (API): user:alice creates, links and sets psets over REST")
    made = alice.create_record(
        CreateRecord(
            actor="user:alice",
            source="api",
            scope=SCOPE,
            record_type="core.Record",
            key=KEY_API,
            title="Exit demo check valve",
        )
    )
    alice.add_link(
        AddLink(
            actor="user:alice",
            source="api",
            scope=SCOPE,
            from_id=made.stream_id,
            to_id=target["id"],
        )
    )
    alice.set_pset_values(
        SetPsetValues(
            actor="user:alice",
            source="api",
            scope=SCOPE,
            stream_id=made.stream_id,
            expected_version=made.version,
            pset="valve_data",
            layer="standard",
            values={"size_in": 6, "manufacturer": "Beta"},
        )
    )
    record = alice.get_record(SCOPE, KEY_API)
    assert record is not None
    expect(len(alice.links_of(record["id"])) == 1, "the API link is missing")
    expect(valve_data(record).get("size_in") == 6, "the API pset value is missing")
    passed(
        "exit-1 API", f"{KEY_API} created, linked to {KEY_TUI} and given psets through /commands"
    )
    await until(
        lambda: grid_row(grid_b, KEY_API) is not None, LIVE_BUDGET_S + 1, "bob sees it", pilot_b
    )
    say("bob's TUI shows it too")


async def clause_mcp(
    alice: ApiClient,
    bob: ApiClient,
    grid_b: RecordGrid,
    pilot_b: Pilot[Any],
    target: dict[str, Any],
) -> None:
    step("exit-1 (MCP): agent:triage proposes, user:bob accepts (MCP writes are propose-only)")
    factory = SqliteUowFactory(Path(DB))
    server = build_server(factory, actor="agent:triage")

    async def tool(name: str, **arguments: Any) -> dict[str, Any]:
        result = await server.call_tool(name, arguments)
        assert isinstance(result, CallToolResult) and result.structured_content is not None
        return result.structured_content

    try:
        title = "Exit demo relief valve"
        created = await tool("create_record", scope=SCOPE, title=title, key=KEY_MCP)
        expect(alice.get_record(SCOPE, KEY_MCP) is None, "the agent wrote a record directly")
        bob.accept_proposal(created["proposal"]["proposal_id"])
        record = alice.get_record(SCOPE, KEY_MCP)
        expect(record is not None, "the accepted proposal created no record")
        linked = await tool(
            "link_records", from_record=KEY_MCP, to_record=target["key"], scope=SCOPE
        )
        set_psets = await tool(
            "update_psets",
            record=KEY_MCP,
            scope=SCOPE,
            pset="valve_data",
            layer="standard",
            values={"size_in": 8, "manufacturer": "Gamma"},
        )
    finally:
        factory.close()
    assert record is not None
    expect(not alice.links_of(record["id"]), "the agent linked a record directly")
    bob.accept_proposal(linked["proposal"]["proposal_id"])
    bob.accept_proposal(set_psets["proposal"]["proposal_id"])
    done = alice.get_record(SCOPE, KEY_MCP)
    assert done is not None
    expect(len(alice.links_of(done["id"])) == 1, "the accepted link is missing")
    expect(valve_data(done).get("size_in") == 8, "the accepted pset values are missing")
    events = alice.history(done["id"])
    who = {(event.actor, event.source) for event in events}
    expect(who == {("user:bob", "mcp:triage")}, f"unexpected attribution {who}")
    say(f"{len(events)} events on the record, all by user:bob with source mcp:triage")
    try:
        ApiClient(URL, AGENT).create_record(
            CreateRecord(
                actor="agent:triage",
                source="api",
                scope=SCOPE,
                record_type="core.Record",
                key="EXIT-X",
                title="refused",
            )
        )
    except ApiError as exc:
        expect(exc.error == "agent_must_propose", f"unexpected refusal {exc.error}")
        say(f"the agent's token is refused over REST: {exc.status} {exc.error}")
    else:
        fail("an agent token created a record over REST")
    passed(
        "exit-1 MCP",
        f"{KEY_MCP} created, linked and given psets by proposals from agent:triage "
        "that bob accepted",
    )
    await until(lambda: grid_row(grid_b, KEY_MCP) is not None, LIVE_BUDGET_S + 1, "bob", pilot_b)


async def clause_settings(
    alice: ApiClient, bob: ApiClient, app_b: TlApp, pilot_b: Pilot[Any]
) -> None:
    step("extra: a setting changed through the API applies to the running server, no restart")
    body = f"Valves #{KEY_TUI} and #{KEY_API}."
    post = alice.feed_post(
        PostToFeed(actor="user:alice", source="api", scope=SCOPE, body=body)
    ).stream_id
    layer = f"project:{PROJECT}"

    def react(client: ApiClient, actor: str) -> None:
        client.feed_react(
            ReactToPost(actor=actor, source="api", scope=SCOPE, post_id=post, reaction="ack")
        )

    react(bob, "user:bob")  # the platform default allows reactions
    changed = alice.set_setting("feed.reactions.enabled", layer=layer, value=False, reason="demo")
    expect(changed.effective.value is False, "the setting did not change")
    try:
        react(alice, "user:alice")
    except Exception as exc:  # noqa: BLE001 - the API maps the refusal to its own class
        say(f"a reaction is refused while the setting is off: {exc}")
    else:
        fail("a reaction was accepted while feed.reactions.enabled is false")
    await pilot_b.press("f9")
    await pilot_b.pause()
    expect(isinstance(app_b.screen, SettingsScreen), "the about:config screen did not open")
    app_b.screen.query_one("#settings-filter", Input).value = "feed.reactions"
    await pilot_b.pause(0.5)
    shown = screen_text(app_b)
    expect("feed.reactions.enabled" in shown and "false" in shown.lower(), "bob's about:config")
    say("bob's about:config screen shows feed.reactions.enabled = false")
    await pilot_b.press("escape")
    await pilot_b.pause()
    alice.reset_setting("feed.reactions.enabled", layer=layer)
    react(alice, "user:alice")
    passed(
        "settings live",
        "feed.reactions.enabled=false refused reactions at once and reset allowed them again",
    )


# --- exit-3: the external webhook receiver ---------------------------------------------------


async def clause_webhook(receiver: ExternalReceiver, first_seq: int) -> None:
    step("exit-3: the external receiver gets a signed event for the filtered subscription")
    count = (
        "SELECT COUNT(*) FROM events WHERE seq >= ? AND scope = ? "
        "AND event_type {} 'Pset.ValuesSet'"
    )
    wanted = ledger_rows(count.format("="), first_seq, SCOPE)[0][0]
    others = ledger_rows(count.format("<>"), first_seq, SCOPE)[0][0]
    say(f"since the subscription: {wanted} Pset.ValuesSet events and {others} of other kinds")
    expect(wanted >= 3 and others > wanted, "the demo did not make a mix of events")
    for _ in range(4):
        await asyncio.to_thread(run_tl, "webhook", "run", "--once", "--allow-host", "127.0.0.1")
        if len(receiver.good) >= wanted:
            break
    expect(not receiver.bad, f"the receiver rejected {len(receiver.bad)} deliveries")
    expect(len(receiver.good) == wanted, f"expected {wanted} deliveries, got {len(receiver.good)}")
    types = {message["event"]["type"] for message in receiver.good}
    expect(types == {"tl.core.Pset.ValuesSet.v1"}, f"the filter let other events through: {types}")
    sample = receiver.good[0]["event"]
    say(
        f"{len(receiver.good)} deliveries, each signed and verified; first: tlseq {sample['tlseq']}"
    )
    passed(
        "exit-3 webhook",
        f"{wanted} signed events verified by an independent receiver; {others} unmatched not sent",
    )


# --- exit-4: restore -------------------------------------------------------------------------


def sqlite_tables(path: str) -> list[str]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        found = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cur\\_%' ESCAPE '\\'"
        )
        return sorted(row[0] for row in found)


def sqlite_dump(path: str, table: str) -> list[str]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        columns = sorted(row[1] for row in conn.execute(f'PRAGMA table_info("{table}")'))
        select = ", ".join(f'"{name}"' for name in columns)
        return sorted(repr(row) for row in conn.execute(f'SELECT {select} FROM "{table}"'))


def engine_snapshot(target: str) -> dict[str, list[Any]]:
    """Every `cur_*` table of the registry (sorted rows) and the ledger's rows, on any dialect."""
    dialect = "postgres" if target.startswith("postgresql://") else "sqlite"
    names: set[str] = set()
    for projector in default_registry().all():
        for statement in projector.ddl(dialect):
            found = re.match(r"\s*CREATE TABLE IF NOT EXISTS (cur_\w+)", statement)
            if found:
                names.add(found.group(1))
    engine = make_engine(target)
    try:
        with read_tx(engine) as conn:
            out: dict[str, list[Any]] = {}
            for table in sorted(names):
                rows = conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
                out[table] = sorted((tuple(sorted(dict(row).items())) for row in rows), key=repr)
            out["events"] = [
                tuple(row) for row in conn.execute(text("SELECT * FROM events ORDER BY seq")).all()
            ]
            return out
    finally:
        engine.dispose()


def restore_into_postgres(archive: Path, pub: Path) -> None:
    """The same archive into a scratch Postgres database; the tables must equal the SQLite ones."""
    base = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    if not admin.reachable(base):
        print("SKIP exit-4 restore (postgres): no Postgres at TL_PG_URL", flush=True)
        return
    name = f"tl_demo_{os.getpid()}_{int(time.time()) % 100000}"
    admin.create_database(base, name)
    url = admin.database_url(base, name)
    try:
        run_tl("restore", "--from-archive", str(archive), "--db", url, "--public-key", str(pub))
        run_tl("ledger", "verify", "--db", url)
        expect(
            engine_snapshot(DB) == engine_snapshot(url), "the Postgres restore differs from SQLite"
        )
        passed(
            "exit-4 restore (postgres)",
            f"the archive restored into Postgres gives the same events and cur_ tables ({name})",
        )
    finally:
        admin.drop_database(base, name)


def clause_restore() -> None:
    step("exit-4: full restore from the ledger archive, verified")
    archive, restored = WORK / "archive", WORK / "restored.db"
    key, pub = WORK / "archive.key", WORK / "archive.pub"
    run_tl("archive", "keygen", "--key", str(key))
    sealed = run_tl("archive", "seal", "--archive", str(archive), "--key", str(key))
    at = re.search(r"archive is at seq (\d+)", sealed)
    manifest = re.search(r"manifest_sha256 ([0-9a-f]{64})", sealed)
    expect(at is not None and manifest is not None, f"unexpected seal output {sealed!r}")
    assert at is not None and manifest is not None
    expect(int(at.group(1)) == head_seq(), "the archive does not reach the head of the ledger")
    run_tl(
        "archive", "verify", "--archive", str(archive), "--public-key", str(pub),
        "--expect-last-seq", at.group(1), "--expect-manifest", manifest.group(1),
    )  # fmt: skip

    tampered = WORK / "tampered"
    shutil.copytree(archive, tampered)
    victim = sorted((tampered / "segments").iterdir())[0] / "events.ndjson"
    victim.chmod(0o644)
    victim.write_bytes(victim.read_bytes().replace(b"Acme", b"Acne", 1))
    run_tl(
        "archive", "verify", "--archive", str(tampered), "--public-key", str(pub),
        expect_failure=True,
    )  # fmt: skip
    say("a tampered copy of the archive is refused; the untouched archive still verifies")

    run_tl(
        "restore", "--from-archive", str(archive), "--db", str(restored), "--public-key", str(pub)
    )
    events = "SELECT seq, event_id, stream_id, event_type, payload, recorded_at, hash FROM events"
    with sqlite3.connect(f"file:{restored}?mode=ro", uri=True) as conn:
        again = conn.execute(events + " ORDER BY seq").fetchall()
    expect(ledger_rows(events + " ORDER BY seq") == again, "the restored events differ")
    tables = sqlite_tables(DB)
    expect(tables == sqlite_tables(str(restored)), "the restored database has other cur_ tables")
    rows = 0
    for table in tables:
        original = sqlite_dump(DB, table)
        expect(original == sqlite_dump(str(restored), table), f"{table} differs after the restore")
        rows += len(original)
    run_tl("ledger", "verify", "--db", str(restored))
    run_tl(
        "archive", "verify", "--archive", str(archive), "--public-key", str(pub),
        "--deep", "--db", str(restored),
    )  # fmt: skip
    say(f"{len(again)} events identical; {len(tables)} cur_ tables, {rows} rows equal")
    passed(
        "exit-4 restore",
        f"{len(again)} events restored from the archive alone; {len(tables)} current-state "
        "tables equal; hash chains and archive verify",
    )
    restore_into_postgres(archive, pub)


# --- the run ---------------------------------------------------------------------------------


async def phases() -> None:
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # Textual routes INFO lines to stdout
    started = time.monotonic()
    alice, bob = ApiClient(URL, ALICE), ApiClient(URL, BOB)
    seeded = alice.list_records(SCOPE, limit=50)
    expect(len(seeded) >= 5, f"the simulated project has only {len(seeded)} records")
    target = next((r for r in seeded if "valve" in (r["title"] or "").lower()), seeded[0])
    step(f"the simulated project {SCOPE}: records written by a seeded team")
    say(f"{len(seeded)} records listed; {target['key']} {target['title']!r} will be a link target")

    # The filtered subscription is made first: only events after it can be delivered.
    receiver = ExternalReceiver()
    made = fields(
        run_tl(
            "webhook",
            "add",
            "--project",
            PROJECT,
            "--name",
            "Exit demo receiver",
            "--url",
            receiver.url,
            "--mode",
            "delta",
            "--event-type",
            "Pset.ValuesSet",
        )  # fmt: skip
    )
    receiver.set_secret(made["secret"])
    first_seq = head_seq() + 1

    tui_a, tui_b = RemoteClient.connect(URL, ALICE), RemoteClient.connect(URL, BOB)
    app_a = TlApp(
        tui_a.as_client(), scope=SCOPE, mode="remote", actor="user:alice",
        feed=tui_a.change_feed(SCOPE),
    )  # fmt: skip
    app_b = TlApp(
        tui_b.as_client(), scope=SCOPE, mode="remote", actor="user:bob",
        feed=tui_b.change_feed(SCOPE),
    )  # fmt: skip
    async with app_a.run_test(size=(120, 40)) as pilot_a, app_b.run_test(size=(120, 40)) as pilot_b:
        grid_a = app_a.query_one("#grid", RecordGrid)
        grid_b = app_b.query_one("#grid", RecordGrid)
        await until(lambda: grid_a.rows and grid_b.rows, 10, "both grids to load", pilot_a)
        await pilot_b.pause(0.5)
        await clause_tui(app_a, pilot_a, alice, target)
        record = await clause_live(grid_b, pilot_b, alice)
        await clause_api(alice, grid_b, pilot_b, record)
        await clause_mcp(alice, bob, grid_b, pilot_b, record)
        await clause_settings(alice, bob, app_b, pilot_b)
        await pilot_b.pause(0.3)
    tui_a.close()
    tui_b.close()

    await clause_webhook(receiver, first_seq)
    receiver.close()
    clause_restore()

    missing = [clause for clause in REQUIRED if clause not in passes]
    expect(not missing, f"clauses without a PASS: {missing}")
    print(f"\nall {len(passes)} clauses passed in {time.monotonic() - started:.0f} s", flush=True)


async def main() -> None:
    try:
        await phases()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())
