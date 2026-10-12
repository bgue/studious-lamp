"""Driver for dev/demos/P1-I0.sh: sign-in, the admin module, agent tokens and lockout (P1-I0).

Modes (first argument), each ending in a PASS line for its FANOUT exit clause:

* ``pg-create`` / ``pg-drop URL``: a throw-away Postgres database on ``TL_PG_URL`` (prints its URL).
* ``actors KEY``: the actors of the events of record KEY, read through the API as demo.
* ``signin``: clause 1. The demo account signs in to the TUI sign-in screen (headless pilot) on the
  ledger itself and on the running server, and to the API; it creates a record through the
  embedded client (what the TUI uses) and another over HTTP. Both events name ``user:demo``.
* ``refused``: clause 2. A person with the ``user`` role is refused every admin route (403).
* ``agent``: clause 3. The agent token an admin issued starts the MCP server; the agent proposes a
  record, cannot decide it or write directly, a person accepts it, and revoking the token ends the
  agent's next call in the same session.
* ``lock``: clause 4. Five wrong passwords lock the name; the right one is then refused with the
  time the lock ends.

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AMY_PASSWORD and TL_DEMO_AGENT_TOKEN. Every expectation is an assert: a failing demo exits
non-zero. Nothing printed holds a password or a token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

SCOPE = "project:P123"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


def pg_create() -> None:
    from tl_adapters.postgres import admin

    server = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    name = admin.test_database_name("demo")
    admin.create_database(server, name)
    print(admin.database_url(server, name))


def pg_drop(url: str) -> None:
    from sqlalchemy.engine import make_url
    from tl_adapters.postgres import admin

    server = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    admin.drop_database(server, make_url(url).database or "")


async def tui_sign_in(authenticator: Any, target: str, name: str, password: str) -> Any:
    """Type a username and password into the real sign-in screen and press Enter."""
    from textual.widgets import Input
    from tl_tui.sign_in import SignInApp

    app = SignInApp(authenticator, target=target)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.screen.query_one("#sign-in-username", Input).value = name
        app.screen.query_one("#sign-in-password", Input).value = password
        await pilot.press("tab", "enter")
        await pilot.pause()
    return app.return_value


def signin() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in
    from tl_core.services.commands import CreateRecord
    from tl_tui.embedded import EmbeddedAuthenticator, EmbeddedClient
    from tl_tui.remote import RemoteAuthenticator

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    embedded = asyncio.run(
        tui_sign_in(EmbeddedAuthenticator.for_target(db), "ledger (demo)", *DEMO)
    )
    assert embedded is not None and embedded.actor == "user:demo" and embedded.is_admin
    say(f"TUI sign-in screen on the ledger: {embedded.actor} ({', '.join(embedded.roles)})")
    remote = asyncio.run(tui_sign_in(RemoteAuthenticator(url), f"server {url}", *DEMO))
    assert remote is not None and remote.token is not None and remote.actor == "user:demo"
    say(f"TUI sign-in screen on the server: {remote.actor}, a session token (not shown)")
    out = sign_in(url, *DEMO)
    assert out.principal.actor == "user:demo" and out.token.startswith("tls_")
    say(f"API sign-in: {out.principal.actor}, expires in {out.expires_in // 3600} h")

    client = EmbeddedClient.for_target(db, actor=embedded.actor)  # what the TUI writes through
    try:
        made = client.create_record(
            CreateRecord(
                actor=embedded.actor,
                source="tui",
                scope=SCOPE,
                record_type="core.Record",
                key="DEMO-1",
                title="Created from the TUI by demo",
            )
        )
        say(f"TUI client created {made.key}")
    finally:
        client.close()
    api = ApiClient(url, out.token)
    try:
        over_http = api.create_record(
            CreateRecord(
                actor="user:ignored",
                source="api",
                scope=SCOPE,
                record_type="core.Record",
                key="DEMO-2",
                title="Created over HTTP by demo",
            )
        )
        say(f"API created {over_http.key}")
        for key in ("DEMO-1", "DEMO-2"):
            record = api.get_record(SCOPE, key)
            assert record is not None
            actors = {e.actor for e in api.history(record["id"])}
            assert actors == {"user:demo"}, actors
    finally:
        api.close()
    passed(1, "demo signs in (TUI headless and API) and creates records as user:demo")


def refused() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in
    from tl_core.auth.errors import ForbiddenError

    url = os.environ["TL_DEMO_URL"]
    out = sign_in(url, "amy", os.environ["TL_DEMO_AMY_PASSWORD"])
    amy = ApiClient(url, out.token)
    try:
        say(f"amy ({', '.join(out.principal.roles)}) is signed in; she may use the API")
        assert amy.whoami().actor == "user:amy"
        for what, call in (
            ("list accounts", amy.list_accounts),
            ("list agent tokens", amy.list_agent_tokens),
            (
                "create an account",
                lambda: amy.create_account("mallory", "Mallory", roles=["admin"]),
            ),
        ):
            try:
                call()
            except ForbiddenError as exc:
                say(f"{what}: refused ({exc})")
            else:
                raise AssertionError(f"a user was allowed to {what}")
    finally:
        amy.close()
    passed(2, "a user is refused an admin action (403 forbidden)")


def agent() -> None:
    from mcp import Client, StdioServerParameters
    from mcp.server.mcpserver.exceptions import ToolError
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in
    from tl_api.errors import ApiError
    from tl_core.services.commands import CreateRecord
    from tl_core.services.errors import ProposalDeciderError

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    token = os.environ["TL_DEMO_AGENT_TOKEN"]
    boss = ApiClient(url, sign_in(url, *DEMO).token)
    robot = ApiClient(url, token)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={"TL_AGENT_TOKEN": token, "TL_DB": db, "TL_ENV": os.environ.get("TL_ENV", "dev")},
    )

    async def session() -> str:
        async with Client(params) as mcp:
            tools = sorted(t.name for t in (await mcp.list_tools()).tools)
            say("MCP tools: " + ", ".join(tools))
            assert "accept_proposal" not in tools  # an agent cannot decide
            made = await mcp.call_tool(
                "create_record", {"scope": SCOPE, "title": "Re-inspect weld W-12"}
            )
            assert not made.is_error and made.structured_content is not None
            proposal = made.structured_content["proposal"]
            assert proposal["status"] == "pending" and proposal["agent"] == "agent:triage"
            say(f"the agent proposed {proposal['proposal_id']} ({proposal['status']})")
            seen = await mcp.call_tool("search_records", {"scope": SCOPE, "q": "title~W-12"})
            assert seen.structured_content is not None and seen.structured_content["total"] == 0
            say("nothing is written yet: a proposal is not a record")
            # a person decides; the agent cannot, and cannot write directly either
            try:
                robot.accept_proposal(proposal["proposal_id"])
            except ProposalDeciderError as exc:
                say(f"the agent's token cannot accept: {exc}")
            else:
                raise AssertionError("an agent accepted a proposal")
            try:
                robot.create_record(
                    CreateRecord(
                        actor="agent:triage", source="api", scope=SCOPE, record_type="core.Record",
                        title="Direct write",
                    )
                )  # fmt: skip
            except ApiError as exc:
                say(f"the agent's token cannot write directly: {exc.status} {exc.error}")
            else:
                raise AssertionError("an agent changed a record directly")
            done = boss.accept_proposal(proposal["proposal_id"])
            assert done.status == "accepted" and done.decided_by == "user:demo", done
            say(f"demo accepted it: the record exists, caused by the agent ({done.status})")
            # revoke the token while the server runs: the next call in this session is refused
            views = [t for t in boss.list_agent_tokens() if not t.revoked]
            assert len(views) == 1
            boss.revoke_agent_token(views[0].token_id, reason="demo")
            say("demo revoked the agent's token")
            try:
                await mcp.call_tool("search_records", {"scope": SCOPE})
            except ToolError as exc:
                return str(exc)
            result = await mcp.call_tool("search_records", {"scope": SCOPE})
            assert result.is_error, "the revoked token still worked"
            return " ".join(getattr(p, "text", "") for p in result.content)

    try:
        refusal = asyncio.run(session())
    finally:
        boss.close()
        robot.close()
    assert "invalid or expired token" in refusal, refusal
    say(f"the next call is refused: {refusal}")
    passed(3, "an admin created a user and an agent token; the agent proposed over MCP")


def lock() -> None:
    from tl_api.client.auth import sign_in
    from tl_core.auth.errors import AccountLockedError, InvalidCredentialsError

    url, good = os.environ["TL_DEMO_URL"], os.environ["TL_DEMO_AMY_PASSWORD"]
    for attempt in range(1, 6):
        try:
            sign_in(url, "amy", "this is not the password")
        except InvalidCredentialsError as exc:
            say(f"wrong password {attempt}: {exc}")
        else:
            raise AssertionError("a wrong password was accepted")
    try:
        sign_in(url, "amy", good)
    except AccountLockedError as exc:
        assert exc.locked_until, "the lock did not say when it ends"
        say(f"the right password is now refused too: {exc}; until {exc.locked_until}")
    else:
        raise AssertionError("a locked name signed in")
    try:
        sign_in(url, "nobody-at-all", "this is not the password")
    except InvalidCredentialsError as exc:
        say(f"an unknown name fails like a wrong password: {exc}")
    passed(4, "five wrong passwords lock the name (unlock is local only: tl admin unlock)")


def actors(key: str) -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    api = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        record = api.get_record(SCOPE, key)
        assert record is not None, f"no record {key}"
        print(",".join(sorted({e.actor for e in api.history(record["id"])})))
    finally:
        api.close()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pg-create":
        pg_create()
    elif mode == "actors":
        actors(sys.argv[2])
    elif mode == "pg-drop":
        pg_drop(sys.argv[2])
    elif mode in {"signin", "refused", "agent", "lock"}:
        {"signin": signin, "refused": refused, "agent": agent, "lock": lock}[mode]()
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
