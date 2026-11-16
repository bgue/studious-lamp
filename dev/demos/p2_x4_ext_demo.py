"""Driver for dev/demos/P2-X4.sh part B: `ext_demo` through the API, the CLI and MCP (P2-X4 T05b).

Each mode is one process over the ledger in TL_DB (made by `tl init --dev`). The fixture module
`ext_demo` is added with `use_modules`; the app and the command table are built inside that block.
clause3 writes a note through the API (bob 200, vic 403, the agent bot 403) and through the CLI;
clause4 is an agent's MCP read, closed until its action is allowed; clause5 reads one note route as
five readers. Each mode prints ``ok`` lines, or ``FAIL`` and exits 1. Seeding is idempotent, and the
notes a mode writes carry a per-run suffix, so a repeat run on the same ledger passes.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import secrets
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import typer
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from tl_adapters.backend import open_backend
from tl_adapters.db import DbTarget, as_target, create_schema, make_uow_factory
from tl_core.auth import accounts, sessions
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.password import prepare_password
from tl_core.auth.queries import find_account
from tl_core.modules import load_modules, use_modules
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ext_demo"))

from load import ext_demo_spec  # noqa: E402  # pyright: ignore[reportMissingImports]

PASSWORD = "correct horse battery"  # the dev password the seeding gives every demo person
SCOPE = "project:P123"
ROUTE = "/modules/ext_demo/notes"
TOOL = "ext_demo_get_note"
OPEN, HIDDEN, MISSING = "N-OPEN", "N-HIDDEN", "N-NONE"
OPEN_TEXT, HIDDEN_TEXT = "words anyone may read", "words only a clearance may read"
NOT_FOUND = "no such note"
#: The five readers of clause5, in order; the first has no account and no token.
READERS = ("anonymous", "bot", "bob", "ctl", "boss")
#: What each reader may read (the keys that answer 200). The anonymous reader reads nothing.
MAY_READ: dict[str, set[str]] = {
    "anonymous": set(),
    "bot": {OPEN},
    "bob": {OPEN},
    "ctl": {OPEN, HIDDEN},
    "boss": {OPEN, HIDDEN},
}
MODES = ("clause3", "clause4", "clause5")


def ok(text_: str) -> None:
    print(f"ok {text_}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


@dataclass
class Ledger:
    """The ledger in TL_DB, the app over it, the tokens of the demo people and the workdir."""

    target: DbTarget
    backend: Any
    app: FastAPI
    tokens: dict[str, str]
    workdir: Path


def person(backend: Any, name: str, roles: list[str]) -> None:
    """Create a person account once; a repeat run finds it and leaves it as it is."""
    with backend(False) as uow:
        if find_account(uow.conn(), username=name) is None:
            accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=roles,
                password=prepare_password(PASSWORD),
                by="svc:demo",
            )


def seed_accounts(backend: Any) -> str:
    """The demo people, the agent `bot` and the viewer grant; returns bot's fresh agent token."""
    person(backend, "bob", ["user"])
    person(backend, "ctl", ["document_controller"])
    person(backend, "boss", ["admin"])
    with backend(False) as uow:
        if find_account(uow.conn(), username="vic") is None:
            vic = accounts.create_account(
                uow,
                username="vic",
                display_name="Vic",
                kind="person",
                roles=["user"],
                password=prepare_password(PASSWORD),
                by="svc:demo",
            )
            # vic holds only `viewer` for ext_demo: no `user` word, so no notes written
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:boss",
                    source="demo",
                    scope="company",
                    account_id=vic.account_id,
                    project=SCOPE,
                    module="ext_demo",
                    role="viewer",
                    reason="demo",
                ),
            )
    with backend(False) as uow:
        bot = find_account(uow.conn(), username="bot")
        if bot is None:
            bot = accounts.create_account(
                uow,
                username="bot",
                display_name="Bot",
                kind="agent",
                roles=["user"],
                password=None,
                by="svc:demo",
            )
    with backend(False) as uow:
        _, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="ext_demo",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:demo",
        )
    return token


def seed_notes(led: Ledger) -> None:
    """N-OPEN and N-HIDDEN, written once (the controller reads both, so it sees a note present)."""
    from tl_mod_ext_demo.commands import ExtDemoAddNote, handle_add_note  # pyright: ignore

    controller = client(led, "ctl")
    for key, body, note_class in (
        (OPEN, OPEN_TEXT, "internal"),
        (HIDDEN, HIDDEN_TEXT, "restricted"),
    ):
        if controller.get(f"{ROUTE}/{key}", params={"scope": SCOPE}).status_code == 404:
            with led.backend(False) as uow:
                handle_add_note(
                    uow,
                    ExtDemoAddNote(
                        actor="user:seed",
                        source="demo",
                        scope=SCOPE,
                        key=key,
                        title=f"Note {key}",
                        body=body,
                        note_class=note_class,  # pyright: ignore[reportArgumentType]
                    ),
                )


@contextmanager
def ledger() -> Iterator[Ledger]:
    """Add `ext_demo` for this process, make the schema and the app, and seed; then close."""
    with use_modules([*load_modules(), ext_demo_spec()]):
        from tl_api.app import create_app

        importlib.import_module("tl_api.commands")  # the command table is built for ext_demo here
        target = as_target(os.environ["TL_DB"])
        create_schema(target)  # the module's projector makes ``ext_demo_note``
        backend = open_backend(target)
        workdir = Path(os.environ["P2_X4_WORKDIR"])
        workdir.mkdir(parents=True, exist_ok=True)
        try:
            bot_token = seed_accounts(backend)
            tokens = {
                name: sessions.sign_in(backend, username=name, password=PASSWORD)[1]
                for name in ("bob", "ctl", "boss", "vic")
            }
            tokens["bot"] = bot_token
            led = Ledger(target, backend, create_app(backend), tokens, workdir)
            seed_notes(led)
            yield led
        finally:
            backend.close()


def client(led: Ledger, who: str | None) -> TestClient:
    headers = {} if who is None else {"Authorization": f"Bearer {led.tokens[who]}"}
    return TestClient(led.app, headers=headers)


def clause3(led: Ledger) -> None:
    """The API refuses vic and the agent, accepts bob; the CLI adds a note as the dev owner."""
    suffix = secrets.token_hex(3)
    key = f"N-BOB-{suffix}"
    added = client(led, "bob").post(
        "/commands/ExtDemoAddNote",
        json={"scope": SCOPE, "key": key, "title": f"Bob {key}", "body": "from the demo"},
    )
    check(added.status_code == 200, f"bob's add answered {added.status_code}: {added.text}")
    read = client(led, "ctl").get(f"{ROUTE}/{key}", params={"scope": SCOPE})
    check(read.status_code == 200 and read.json()["body"] == "from the demo", "bob's note not read")
    ok(f"clause3 api: bob adds {key} (200), the controller reads it")

    refused = client(led, "vic").post(
        "/commands/ExtDemoAddNote",
        json={"scope": SCOPE, "key": "N-VIC", "title": "Vic", "body": "x"},
    )
    check(refused.status_code == 403 and "ext_demo" in refused.text, refused.text)
    ok("clause3 api: vic is refused (403) and the text names ext_demo")

    agent = client(led, "bot").post(
        "/commands/ExtDemoAddNote",
        json={"scope": SCOPE, "key": "N-BOT", "title": "Bot", "body": "x"},
    )
    check(
        agent.status_code == 403 and agent.json().get("error") == "agent_must_propose",
        agent.text,
    )
    ok("clause3 api: the agent bot is refused (403 agent_must_propose)")

    cli_key = f"N-CLI-{suffix}"
    root = typer.Typer()
    from tl_cli.main import _add_module_groups  # pyright: ignore[reportPrivateUsage]

    _add_module_groups(root, load_modules())
    environ = {"TL_ENV": "test", "TL_SESSION_FILE": str(led.workdir / "session.json")}
    args = ["ext_demo", "add", cli_key, "--project", "P123", "--title", "Cli", "--body", "x"]
    result = CliRunner().invoke(root, args, obj=led.target, env=environ)
    check(
        (result.exit_code, result.output.strip()) == (0, f"added {cli_key}"),
        f"cli add exited {result.exit_code}: {result.output}",
    )
    ok(f"clause3 cli: added {cli_key} (exit 0)")


def clause4(led: Ledger) -> None:
    """An agent over MCP: the read tool is listed, closed until allowed, and no core tool opens."""
    from tl_api.auth import Forbidden
    from tl_mcp.server import build_server

    allowed: set[str] = set()

    def hook(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    server = build_server(make_uow_factory(led.target), actor="agent:bot", authorize_hook=hook)

    def refused(name: str, args: dict[str, Any]) -> str:
        try:
            asyncio.run(server.call_tool(name, args))
        except ToolError as exc:
            return str(exc)
        return miss(f"{name} was not refused")

    def read(key: str) -> dict[str, Any]:
        result: Any = asyncio.run(server.call_tool(TOOL, {"scope": SCOPE, "key": key}))
        content = result.structured_content
        body = content["result"] if set(content) == {"result"} else content
        return dict(body)

    names = {tool.name for tool in asyncio.run(server.list_tools())}
    check(TOOL in names, f"{TOOL} is not listed")
    ok(f"clause4 mcp: {TOOL} is listed after build_server")

    text_closed = refused(TOOL, {"scope": SCOPE, "key": OPEN})
    check("not allowed" in text_closed, f"closed read said: {text_closed}")
    ok("clause4 mcp: the read is closed until mcp.ext_demo_get_note is allowed")

    allowed.add(f"mcp.{TOOL}")
    check(read(OPEN)["body"] == OPEN_TEXT, "the allowed read did not return the open note")
    ok("clause4 mcp: after the allow row, the agent reads the open note")

    core = refused("get_record", {"record": OPEN, "scope": SCOPE})
    check("not allowed" in core, f"core tool was not closed: {core}")
    ok("clause4 mcp: the core tool get_record is still refused")

    hidden_text = refused(TOOL, {"scope": SCOPE, "key": HIDDEN})
    missing_text = refused(TOOL, {"scope": SCOPE, "key": MISSING})
    check(hidden_text == missing_text and NOT_FOUND in hidden_text, hidden_text)
    check(HIDDEN not in hidden_text and HIDDEN_TEXT not in hidden_text, "hidden note leaked")
    ok("clause4 mcp: a hidden and a missing note raise one identical 'no such note' text")


def clause5(led: Ledger) -> None:
    """Five readers of one note route: the readable sets, and a hidden note as a missing one."""
    for name in READERS:
        token_who = None if name == "anonymous" else name
        reader = client(led, token_who)
        answers = {
            key: reader.get(f"{ROUTE}/{key}", params={"scope": SCOPE})
            for key in (OPEN, HIDDEN, MISSING)
        }
        readable = {key for key, r in answers.items() if r.status_code == 200}
        check(readable == MAY_READ[name], f"{name} reads {sorted(readable)}")
        hidden, missing = answers[HIDDEN], answers[MISSING]
        if HIDDEN not in readable:
            check(
                (hidden.status_code, hidden.text) == (missing.status_code, missing.text),
                f"{name}: hidden and missing answer differently",
            )
            check(HIDDEN_TEXT not in hidden.text and HIDDEN not in hidden.text, f"{name} leaked")
            check(hidden.status_code == (401 if name == "anonymous" else 404), name)
        for response in answers.values():
            if response.status_code != 200:
                check(OPEN_TEXT not in response.text, f"{name}: a refusal carries note text")
        if name == "anonymous":
            statuses = {r.status_code for r in answers.values()}
            texts = {r.text for r in answers.values()}
            check(statuses == {401} and len(texts) == 1, "anonymous is not refused alike")
        ok(f"reader {name}: reads {len(readable)} of 3")


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) == 2 else ""
    if mode not in MODES:
        print(f"usage: p2_x4_ext_demo.py {'|'.join(MODES)}", file=sys.stderr)
        raise SystemExit(2)
    run: Callable[[Ledger], None] = {"clause3": clause3, "clause4": clause4, "clause5": clause5}[
        mode
    ]
    with ledger() as led:
        run(led)


if __name__ == "__main__":
    main(sys.argv)
