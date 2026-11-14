"""Driver for dev/demos/P2-X1.sh: the clauses of the idempotency demo that are not a `tl` command.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`).
Clauses 1 to 4 send raw HTTP with ``urllib`` to the running `tl serve` at TL_API_URL, with a
person's session token (`sessions.sign_in`) or the agent token that the shell wrote to
P2_X1_WORKDIR/agent-token. The `Idempotency-Key` header is set by the caller. ``ApiClient`` is
not used: it would add keys of its own.

Clause 3's MCP half runs on a server built by `build_server` as the agent. Clause 5 runs the app
in process over the same ledger, with the test-only class source of
packages/tl-api/tests/test_idempotency_walk.py (a `core.Record` class read from a table), because
the `tl serve` process cannot be given that source. Clause 6 runs `tl_api.openapi --compat`
against scratch baselines in P2_X1_WORKDIR. The compat step reads BASELINE_PATH and the
route-built document, not OPENAPI_PATH, so the scratch changes are made to the baseline side.

Modes (first argument): ``clause1`` to ``clause6``. Each prints one ``ok <what>`` line per
check. The shell prints ``PASS clause N`` once the mode has returned. A miss prints
``FAIL <what>`` and exits 1. Nothing under docs/reference/ is written.
"""

from __future__ import annotations

import copy
import io
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any, NoReturn

from fastapi.testclient import TestClient
from sqlalchemy import text
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_uow_factory, open_uow
from tl_api.app import create_app
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.auth import sessions
from tl_core.modules import ConfidentialSource
from tl_core.services.idempotency import IN_PROGRESS_TEXT, MISMATCH_TEXT
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.server import build_server

PASSWORDS = {  # the dev passwords the shell seeds the people with
    "amy": "a long passphrase for amy",
    "bob": "a long passphrase for bob",
}
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
AGENT = "agent:triage"  # an agent account: no person behind it
FAKE_ID = "01J000000000000000000000"  # a record id that never existed
CLASS_TABLE = "demo_x1_class"  # test-only class source for clause 5
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
    """The ledger in TL_DB, the running API at TL_API_URL, and the people's sessions."""

    def __init__(self) -> None:
        self.target = as_target(os.environ["TL_DB"])
        self.backend = open_backend(self.target)
        self.workdir = Path(os.environ["P2_X1_WORKDIR"])
        self.url = os.environ["TL_API_URL"]

    def token(self, name: str) -> str:
        _, token = sessions.sign_in(self.backend, username=name, password=PASSWORDS[name])
        return token

    def agent_token(self) -> str:
        return (self.workdir / "agent-token").read_text(encoding="utf-8").strip()

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> int:
        with self.backend(True) as uow:
            return int(uow.conn().execute(text(sql), params or {}).scalar_one())

    def head(self) -> int:
        """The ledger's last sequence number: the count of events written so far."""
        with self.backend(True) as uow:
            return int(uow.ledger.head_seq())

    def events_on(self, stream_id: str) -> int:
        with self.backend(True) as uow:
            return len(uow.ledger.read_stream(stream_id))

    def close(self) -> None:
        self.backend.close()


def mcp_server(world: World, actor: str) -> Any:
    """The MCP server for ``actor``; the write tools are registered by build_server."""

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
    import asyncio

    try:
        result = asyncio.run(server.call_tool(tool, arguments))
    except Exception as exc:  # a failed tool is raised by the server (ToolError), not returned
        raise RuntimeError(str(exc)) from exc
    if result.is_error:
        raise RuntimeError(" ".join(getattr(block, "text", "") for block in result.content))
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def send(url: str, token: str, body: dict[str, Any], key: str | None = None) -> tuple[int, Any]:
    """POST ``body`` to ``url`` with the bearer token and, when given, the Idempotency-Key."""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (loopback)
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw.decode(errors="replace")


def record_body(title: str, key: str) -> dict[str, Any]:
    return {"scope": SCOPE, "record_type": "core.Record", "title": title, "key": key}


def create_url(world: World) -> str:
    return f"{world.url}/commands/CreateRecord"


def title_rows(world: World, title: str) -> int:
    return world.scalar("SELECT COUNT(*) FROM cur_core_record WHERE title = :t", {"t": title})


def clause1() -> None:
    world = World()
    try:
        amy = world.token("amy")
        body = record_body("C1 valve", "C1-REC")
        status, first = send(create_url(world), amy, body, "x1-c1-key")
        check(status == 200, f"the first send answered {status}: {first}")
        events_before = world.events_on(first["stream_id"])
        status, second = send(create_url(world), amy, body, "x1-c1-key")
        check(status == 200, f"the second send answered {status}: {second}")
        check(second == first, f"the second answer differs: {second} vs {first}")
        events_after = world.events_on(first["stream_id"])
        check(events_after == events_before, f"events {events_before} then {events_after}")
        rows = world.scalar("SELECT COUNT(*) FROM cur_core_record WHERE key = 'C1-REC'")
        check(rows == 1, f"{rows} records for one key")
        ok("one key, one body, sent twice by amy: both 200, the same answer")
        ok(f"{events_after} events on {first['stream_id']} before and after the replay; {rows} row")
    finally:
        world.close()


def clause2() -> None:
    world = World()
    try:
        amy = world.token("amy")
        status, first = send(create_url(world), amy, record_body("C2 pump", "C2-REC"), "x1-c2-key")
        check(status == 200, f"the first send answered {status}: {first}")
        head_before = world.head()
        status, answer = send(
            create_url(world), amy, record_body("C2 other pump", "C2-OTHER"), "x1-c2-key"
        )
        check(status == 409, f"same key, other body answered {status}: {answer}")
        check(answer.get("error") == "idempotency_mismatch", f"error is {answer}")
        check(answer.get("message") == MISMATCH_TEXT, f"message is {answer}")
        check(world.head() == head_before, "the mismatch wrote events")
        check(title_rows(world, "C2 other pump") == 0, "the mismatch wrote a record")
        ok(f"same key, other body: 409 idempotency_mismatch, the fixed text; {head_before} events")

        results: list[tuple[int, Any]] = []
        lock = threading.Lock()
        barrier = threading.Barrier(2)

        def race() -> None:
            barrier.wait()
            outcome = send(create_url(world), amy, record_body("C2 race", "C2-RACE"), "x1-c2-race")
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=race) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        check(len(results) == 2, f"only {len(results)} of 2 concurrent sends answered")
        statuses = sorted(code for code, _ in results)
        for code, answer in results:
            check(code in (200, 409), f"a concurrent send answered {code}: {answer}")
            if code == 409:
                check(answer.get("error") == "idempotency_in_progress", f"409 is {answer}")
                check(answer.get("message") == IN_PROGRESS_TEXT, f"409 text is {answer}")
        check(statuses.count(200) >= 1, f"no concurrent send was accepted: {statuses}")
        rows = world.scalar("SELECT COUNT(*) FROM cur_core_record WHERE key = 'C2-RACE'")
        check(rows == 1, f"{rows} records after two concurrent sends of one key")
        ok(f"two concurrent sends of one key: answers {statuses}, no 500; {rows} record after")
    finally:
        world.close()


def clause3() -> None:
    world = World()
    try:
        status, answer = send(
            create_url(world),
            world.agent_token(),
            record_body("C3 agent record", "C3-AGENT-HTTP"),
            "x1-c3-http",
        )
        check(status == 403, f"the agent's HTTP create answered {status}: {answer}")
        check(answer.get("error") == "agent_must_propose", f"error is {answer}")
        records = world.scalar("SELECT COUNT(*) FROM cur_core_record WHERE key = 'C3-AGENT-HTTP'")
        keys = world.scalar("SELECT COUNT(*) FROM idempotency_key WHERE actor = :a", {"a": AGENT})
        check(
            records == 0 and keys == 0, f"the refused create stored {records} records, {keys} keys"
        )
        ok("the agent's HTTP CreateRecord with a key: 403 agent_must_propose, 0 records stored")

        proposals_before = world.scalar("SELECT COUNT(*) FROM cur_proposals")
        server = mcp_server(world, AGENT)
        args = {
            "scope": SCOPE,
            "title": "C3 agent proposal",
            "key": "C3-AGENT-MCP",
            "idempotency_key": "x1-c3-mcp",
        }
        first = mcp_call(server, "create_record", **args)
        second = mcp_call(server, "create_record", **args)
        check(first == second, f"the MCP replay differs: {second} vs {first}")
        proposal_id = first["proposal"]["proposal_id"]
        check(proposal_id == second["proposal"]["proposal_id"], "the proposal ids differ")
        added = world.scalar("SELECT COUNT(*) FROM cur_proposals") - proposals_before
        check(added == 1, f"two MCP sends with one key added {added} proposal rows")
        ok(f"the agent's MCP create_record twice with one key: one proposal row ({proposal_id})")
    finally:
        world.close()


def clause4() -> None:
    world = World()
    try:
        amy = world.token("amy")
        bob = world.token("bob")
        shared = "x1-c4-shared"
        status, first = send(create_url(world), amy, record_body("C4 amy valve", "C4-AMY"), shared)
        check(status == 200, f"amy's send answered {status}: {first}")
        status, theirs = send(create_url(world), bob, record_body("C4 bob pump", "C4-BOB"), shared)
        check(status == 200, f"bob's send with the same key answered {status}: {theirs}")
        check(theirs["stream_id"] != first["stream_id"], "bob got amy's record")
        check(first["stream_id"] not in json.dumps(theirs), "bob's answer names amy's record")
        entries = world.scalar(
            "SELECT COUNT(*) FROM idempotency_key WHERE idem_key = :k", {"k": shared}
        )
        check(entries == 2, f"the shared key has {entries} entries, not 2")
        status, again = send(create_url(world), amy, record_body("C4 amy valve", "C4-AMY"), shared)
        check(status == 200 and again == first, f"amy's replay is {status}: {again}")
        ok(f"bob's same key: 200, his own record {theirs['stream_id']}; {entries} key entries")
        ok(f"amy's replay still answers her record {first['stream_id']}")
    finally:
        world.close()


def set_class(world: World, record_id: str, cls: str) -> None:
    with open_uow(world.target) as uow:
        found = (
            uow.conn()
            .execute(text(f"SELECT 1 FROM {CLASS_TABLE} WHERE id = :i"), {"i": record_id})
            .first()
        )
        if found is None:
            uow.conn().execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                {"i": record_id, "c": cls},
            )
        else:
            uow.conn().execute(
                text(f"UPDATE {CLASS_TABLE} SET cls = :c WHERE id = :i"),
                {"i": record_id, "c": cls},
            )


def clause5() -> None:
    world = World()
    original = cf.confidential_sources
    try:
        with open_uow(world.target) as uow:
            uow.conn().execute(
                text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)")
            )
        source = ConfidentialSource(
            record_types=frozenset({"core.Record"}),
            table=CLASS_TABLE,
            id_column="id",
            class_column="cls",
        )
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # the test-only class source
        client = TestClient(create_app(world.backend), raise_server_exceptions=False)
        auth = {"Authorization": f"Bearer {world.token('amy')}"}
        keyed = {**auth, "Idempotency-Key": "x1-c5-key"}
        title = "C5 restricted valve"
        request = record_body(title, "C5-REC")

        first = client.post("/commands/CreateRecord", json=request, headers=keyed)
        check(
            first.status_code == 200, f"the first send answered {first.status_code}: {first.text}"
        )
        record_id = first.json()["stream_id"]
        set_class(world, record_id, "internal")  # amy may read it while the key is in use
        visible = client.post("/commands/CreateRecord", json=request, headers=keyed)
        check(visible.json() == first.json(), f"the visible replay differs: {visible.text}")
        set_class(world, record_id, "privileged")  # the clearance drops: nobody is named on it
        replay = client.post("/commands/CreateRecord", json=request, headers=keyed)
        hidden = client.get(f"/records/{record_id}/actions", headers=auth)
        missing = client.get(f"/records/{FAKE_ID}/actions", headers=auth)
        check(title not in replay.text, f"the replay shows the title: {replay.text}")
        check(replay.status_code == missing.status_code == 404, f"replay {replay.status_code}")
        check(
            hidden.text.replace(record_id, FAKE_ID) == missing.text, "hidden differs from missing"
        )
        check(title not in hidden.text, "the hidden record shows its title")
        ok(f"replay after the clearance drop: {replay.status_code}, no title, as a missing id")
        ok(f"the record {record_id} is hidden from amy; its GET equals the GET of {FAKE_ID}")
    finally:
        cf.confidential_sources = original
        world.close()


def clause6() -> None:
    import tl_api.openapi as openapi

    repo = Path(__file__).resolve().parents[2]
    scratch = Path(os.environ["P2_X1_WORKDIR"])
    baseline = json.loads((repo / openapi.BASELINE_PATH).read_text(encoding="utf-8"))
    schemas = baseline["openapi"]["components"]["schemas"]
    record = schemas["RecordResponseBody"]  # a response with optional fields
    optional = [p for p in record["properties"] if p not in record.get("required", [])]
    check(bool(optional), "RecordResponseBody has no optional property to drop")

    removed = copy.deepcopy(baseline)  # the current document lacks this field: a removal
    removed["openapi"]["components"]["schemas"]["CommandResult"]["properties"]["demo_retired"] = {
        "type": "string"
    }
    added = copy.deepcopy(baseline)  # the current document has one more optional field
    del added["openapi"]["components"]["schemas"]["RecordResponseBody"]["properties"][optional[0]]
    for name, document in (("removed", removed), ("added", added)):
        (scratch / f"{name}-baseline.json").write_text(json.dumps(document), encoding="utf-8")
    openapi.OPENAPI_PATH = scratch / "openapi.json"  # scratch paths (compat reads the baseline)
    openapi.BASELINE_PATH = scratch / "removed-baseline.json"
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        code = openapi.main(["--compat"])
    check(code == 1, f"a removed response field passed compat (exit {code})")
    check(
        "demo_retired" in buffer.getvalue(),
        f"the refusal does not name the field: {buffer.getvalue()}",
    )
    first_line = buffer.getvalue().splitlines()[0]
    ok(f"a removed response field fails compat (exit 1): {first_line}")

    openapi.BASELINE_PATH = scratch / "added-baseline.json"
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        code = openapi.main(["--compat"])
    check(code == 0, f"an added optional field failed compat (exit {code}): {buffer.getvalue()}")
    ok(f"an added optional field ({optional[0]}, new in the current document) passes (exit 0)")


HANDLERS: dict[str, Callable[[], None]] = {
    "clause1": clause1,
    "clause2": clause2,
    "clause3": clause3,
    "clause4": clause4,
    "clause5": clause5,
    "clause6": clause6,
}


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in MODES or len(argv) != 2:
        raise SystemExit(f"usage: p2_x1_demo.py {{{'|'.join(MODES)}}}")
    HANDLERS[mode]()


if __name__ == "__main__":
    main(sys.argv)
