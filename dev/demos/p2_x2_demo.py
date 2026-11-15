"""Driver for dev/demos/P2-X2.sh: the agent's filings and the five-reader read (P2-X2 T05).

The agent files through an MCP server built as the agent (as in ``p2_x1_demo.py``); admin acts are
`tl` commands in the shell. Clause 6 makes amy's record privileged through a test-only class source
(as X1's clause 5 does) and reads the held count and the stopped list as five readers. Each mode
prints ``ok`` lines, or ``FAIL`` and exits 1. Values pass to the shell as notes in P2_X2_WORKDIR.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, NoReturn

from sqlalchemy import text
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_uow_factory, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.auth import sessions
from tl_core.modules import ConfidentialSource
from tl_core.services import agent_scope, agent_stop
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.server import build_server

PASSWORDS = {"amy": "a long passphrase for amy", "bob": "a long passphrase for bob"}
PASSWORDS["dora"] = "a long passphrase for dora"  # the dev passwords the shell seeds
SCOPE = "project:P1"
AGENT = "agent:triage"  # an agent account: no person behind it
CLASS_TABLE = "demo_x2_class"  # test-only class source for clause 6
CLEAR_TABLE = "demo_x2_clearance"
#: The five readers of clause 6 (kind, actor); the lowest reader has no account.
READERS = (
    ("admin", "user:demo"),
    ("user", "user:bob"),
    ("controller", "user:dora"),
    ("lowest", None),
    ("named", "user:amy"),
)
#: Held proposals per reader: the privileged one counts only for amy, who is named on it.
EXPECTED_HELD = {"admin": 1, "user": 1, "controller": 1, "lowest": 1, "named": 2}
MODES = ("clause1", "clause2", "clause3", "clause4", "clause5", "clause6")


def ok(text_: str) -> None:
    print(f"ok {text_}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


class World:
    """The ledger in TL_DB, the running API at TL_API_URL, and the notes shared with the shell."""

    def __init__(self) -> None:
        self.target = as_target(os.environ["TL_DB"])
        self.backend = open_backend(self.target)
        self.workdir = Path(os.environ["P2_X2_WORKDIR"])
        self.url = os.environ["TL_API_URL"]

    def note(self, name: str, value: str = "") -> str:
        """Write ``value`` to a note for the shell, or read the note ``name`` when no value."""
        path = self.workdir / name
        if value:
            path.write_text(f"{value}\n", encoding="utf-8")
        return path.read_text(encoding="utf-8").strip()

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
        with self.backend(True) as uow:
            return list(uow.conn().execute(text(sql), params or {}).all())

    def pending(self) -> int:
        sql = "SELECT COUNT(*) FROM cur_proposals WHERE scope = :s AND status = 'pending'"
        return int(self.query(sql, {"s": SCOPE})[0][0])

    def agent_server(self) -> Any:
        """The MCP server for the agent; its write tools are registered by build_server."""

        def allow(who: str, action: str, resource: str) -> None:
            if action not in MCP_ACTIONS:
                raise PermissionError(f"{action} is not allowed for {who}")

        return build_server(
            make_uow_factory(self.target),
            actor=AGENT,
            authorize_hook=allow,
            lake_dir=self.workdir / "lake",
        )

    def filing(self, title: str, key: str, scope: str = SCOPE) -> str:
        """One agent filing (a pending create_record proposal): its id. A refusal raises."""
        args = {"scope": scope, "title": title, "key": key}
        try:
            result = asyncio.run(self.agent_server().call_tool("create_record", args))
        except Exception as exc:  # the refusal is raised by the server (ToolError)
            raise RuntimeError(str(exc)) from exc
        if result.is_error:
            raise RuntimeError(" ".join(getattr(b, "text", "") for b in result.content))
        content = result.structured_content  # unwrapped as in p2_x1_demo.py's mcp_call
        body = content["result"] if set(content) == {"result"} else content
        return str(body["proposal"]["proposal_id"])

    def refusal(self, scope: str, key: str) -> str:
        """The text a filing on ``scope`` is refused with; a filing that gets in is a miss."""
        try:
            self.filing("X2 refused filing", key, scope)
        except RuntimeError as exc:
            return str(exc)
        return miss(f"a filing on {scope} was not refused")

    def amy_creates(self, title: str, key: str) -> str:
        """amy's HTTP CreateRecord on SCOPE; the id of the new record (its stream id)."""
        _, token = sessions.sign_in(self.backend, username="amy", password=PASSWORDS["amy"])
        body = {"scope": SCOPE, "record_type": "core.Record", "title": title, "key": key}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        request = urllib.request.Request(
            f"{self.url}/commands/CreateRecord",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (loopback)
            return str(json.loads(response.read())["stream_id"])

    def close(self) -> None:
        self.backend.close()


def clause1() -> None:
    world = World()
    try:
        before = world.query("SELECT COUNT(*) FROM cur_proposals")[0][0]
        no_word = world.refusal(SCOPE, "X2-C1")
        missing = world.refusal("project:NOSUCH", "X2-C1")
        # the service's refusal names the scope it refuses; compare the texts without the scope
        same = no_word.replace(SCOPE, "<scope>") == missing.replace("project:NOSUCH", "<scope>")
        check(same, f"the refusals differ: {no_word!r} vs {missing!r}")
        check(world.query("SELECT COUNT(*) FROM cur_proposals")[0][0] == before, "a refusal stored")
        ok(f"no module word on {SCOPE}: refused with the text a missing scope gets")
        ok("the refused filings stored no proposal")
    finally:
        world.close()


def clause2() -> None:
    world = World()
    try:
        record_id = world.amy_creates("X2 valve", "X2-PRIV")
        world.note("record-privileged.id", record_id)
        pid = world.filing("X2 agent filing A", record_id)  # the key carries the record's id
        world.note("proposal-a.id", pid)
        check(world.pending() == 1, f"{world.pending()} pending after the first filing")
        ok(f"with the word the agent's filing is pending: {pid}")
        ok("the filing carries one of amy's records (the privileged one of clause 6)")
    finally:
        world.close()


def clause3() -> None:
    world = World()
    try:
        check(world.pending() == 1, f"{world.pending()} pending before the cap test")
        filed: list[str] = []
        refusal = ""
        for n in range(5):
            try:
                filed.append(world.filing(f"X2 cap filing {n}", f"X2-C3-{n}"))
            except RuntimeError as exc:
                refusal = str(exc)
                break
        check(refusal != "", "the queue cap refused no filing within 5 tries")
        # the MCP server prefixes its own error line; the service's fixed text ends it
        check(refusal.endswith(agent_scope.QUEUE_FULL_TEXT), f"the refusal is {refusal!r}")
        check(not any(c.isdigit() for c in refusal), "the refusal shows a count")
        check(world.pending() == 2, f"{world.pending()} pending at the cap")
        world.note("proposal-b.id", filed[0])
        ok("the cap refuses the filing past two pending with the fixed text; no digit in it")
        ok(f"the filing that got in is pending: {filed[0]}")
    finally:
        world.close()


def clause4() -> None:
    world = World()
    try:
        try:
            world.filing("X2 stopped", "X2-C4")
        except RuntimeError as exc:
            stop_text = str(exc)
        else:
            miss("a stopped agent's filing was accepted")
        check(stop_text.endswith(agent_stop.STOPPED_TEXT), f"the stop refusal is {stop_text!r}")
        check(not any(c.isdigit() for c in stop_text), "the stop text shows a count")
        accept_err = world.note("accept-stopped.err")
        check(agent_stop.STOPPED_TEXT in accept_err, f"the accept refusal is {accept_err!r}")
        with world.backend(True) as uow:
            held = agent_stop.held_count(uow.conn(), AGENT, cf.LOWEST)
        check(held == world.pending() == 2, f"held {held}, pending {world.pending()}")
        world.note("held-expected", str(held))
        ok("a new filing is refused with the stop text, which names no count")
        ok(f"accept is refused; {held} pending proposals show as held")
    finally:
        world.close()


def clause5() -> None:
    world = World()
    try:
        pid = world.filing("X2 resumed filing", "X2-C5")
        check(world.pending() == 2, f"{world.pending()} pending after the resumed filing")
        types = [
            str(r[0])
            for r in world.query(
                "SELECT event_type FROM events "
                "WHERE event_type IN ('Agent.Stopped','Agent.Resumed') ORDER BY seq"
            )
        ]
        check(types == ["Agent.Stopped", "Agent.Resumed"], f"ledger types are {types}")
        ok(f"the filing after resume is pending: {pid}")
        ok(f"ledger types in order: {', '.join(types)}")
    finally:
        world.close()


def clause6() -> None:
    world = World()
    original = cf.confidential_sources
    try:
        record_id = world.note("record-privileged.id")
        setup = (
            f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)",
            f"CREATE TABLE {CLEAR_TABLE} (record_id TEXT NOT NULL, account TEXT NOT NULL)",
            f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES ('{record_id}', 'privileged')",
            f"INSERT INTO {CLEAR_TABLE} (record_id, account) VALUES ('{record_id}', 'user:amy')",
        )
        with open_uow(world.target) as uow:
            for statement in setup:
                uow.conn().execute(text(statement))
        source = ConfidentialSource(
            record_types=frozenset({"core.Record"}),
            table=CLASS_TABLE,
            id_column="id",
            class_column="cls",
            clearance_table=CLEAR_TABLE,
            clearance_record_column="record_id",
            clearance_account_column="account",
        )
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # the test-only class source
        held_for: dict[str, int] = {}
        for kind, actor in READERS:
            with world.backend(True) as uow:
                conn = uow.conn()
                viewer = cf.viewer_for_actor(conn, actor) if actor else cf.LOWEST
                held_for[kind] = agent_stop.held_count(conn, AGENT, viewer)
                rows = agent_stop.list_stopped(conn, viewer)
            check(sum(r.agent == AGENT for r in rows) == 1, f"the {kind} reader sees no row")
            dumped = json.dumps([r.model_dump() for r in rows])
            check(record_id not in dumped, f"the {kind} reader's list names the hidden record")
        check(held_for == EXPECTED_HELD, f"held by reader: {held_for}")
        ok("held by reader: admin 1, user 1, controller 1, lowest 1, named 2")
        ok("the stopped list names no hidden record for any of the five readers")
    finally:
        cf.confidential_sources = original
        world.close()


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in MODES or len(argv) != 2:
        raise SystemExit(f"usage: p2_x2_demo.py {{{'|'.join(MODES)}}}")
    globals()[mode]()


if __name__ == "__main__":
    main(sys.argv)
