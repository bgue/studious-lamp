"""Driver for dev/demos/P1-I1.sh: what a person, a client and an agent see of the engineering data.

Modes (first argument), each ending in a PASS line for its clause:

* ``refused``: clause 6. A person with the ``user`` role cannot change the registry: the API
  refuses the admin commands (403) and the generic ``UpdateRecord`` on a tag class (422), and a
  tag she makes cannot carry an ``origin`` or a pattern policy.
* ``reads``: clause 7. The same tags through the API, through the TUI tag register (F8, headless
  pilot, embedded client) and through the MCP tools an agent has (``get_tag``,
  ``list_tag_classes``).

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AMY_PASSWORD, TL_DEMO_AGENT_TOKEN and TL_DEMO_TAG. Every expectation is an assert: a
failing demo exits non-zero. Nothing printed holds a password or a token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


def post(url: str, token: str, name: str, body: dict[str, Any]) -> tuple[int, str]:
    """``POST /commands/<name>``; the status and the error code (or ``ok``)."""
    import httpx2

    response = httpx2.post(
        f"{url}/commands/{name}", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    data = response.json()
    return response.status_code, ("ok" if response.status_code == 200 else str(data["error"]))


def refused() -> None:
    import httpx2
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    amy = sign_in(url, "amy", os.environ["TL_DEMO_AMY_PASSWORD"]).token
    boss = sign_in(url, *DEMO).token
    classes = httpx2.get(f"{url}/tag-classes", headers={"Authorization": f"Bearer {boss}"}).json()
    stream_id = next(c["id"] for c in classes if c["code"] == "ControlValve")
    attempts: list[tuple[str, dict[str, Any], int, str]] = [
        (
            "RegisterMnemonic",
            {"scope": "company", "code": "ZZ", "label": "Z", "edition": "x@1.0.0"},
            403,
            "forbidden",
        ),
        (
            "UpdateRecord",
            {
                "scope": "company",
                "stream_id": stream_id,
                "expected_version": 2,
                "changes": {"title": "hijacked"},
            },
            422,
            "unsupported_record_type",
        ),
        ("RecordTag", {"scope": SCOPE, "number": "LEGACY-9"}, 403, "forbidden"),
        (
            "CreateTag",
            {"scope": SCOPE, "number": "LEGACY-8", "origin": "import"},
            422,
            "validation_error",
        ),
        (
            "CreateTag",
            {"scope": SCOPE, "number": "LEGACY-8", "pattern_policy": "record"},
            422,
            "validation_error",
        ),
    ]
    for name, body, status, code in attempts:
        got = post(url, amy, name, body)
        assert got == (status, code), (name, got)
        say(f"amy: {name} refused ({got[0]} {got[1]})")
    admin = post(url, boss, "UpdateRecord", attempts[1][1])
    assert admin == (422, "unsupported_record_type"), admin
    say("even demo (admin) cannot UpdateRecord a tag class: the registry has its own commands")
    passed(6, "a user cannot change the registry, edit a class generically or keep a bad number")


async def register(db: str, number: str) -> list[str]:
    """Open the tag register (F8) on the ledger as demo and read what it shows."""
    from textual.widgets import DataTable
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.tag_register import TagRegisterScreen

    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo")
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.press("f8")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TagRegisterScreen)
            assert screen.query_one("#tags-table", DataTable).row_count >= 1
            shown = [v.number for v in screen.shown]
            assert number in shown, shown
            return shown
    finally:
        client.close()


def reads() -> None:
    from mcp import Client, StdioServerParameters
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    token = os.environ["TL_DEMO_AGENT_TOKEN"]
    number = os.environ["TL_DEMO_TAG"]
    api = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        listed = api.list_tags(PROJECT)
        say(f"API: {len(listed)} tags in service, e.g. {', '.join(t.number for t in listed[:3])}")
        tag = api.get_tag(PROJECT, number)
        assert tag.segments["mnemonic"] == "FV" and tag.class_code == "ControlValve"
        say(f"API: {tag.number} class {tag.class_code}, conformance {tag.conformance}")
    finally:
        api.close()
    shown = asyncio.run(register(db, number))
    say(f"TUI tag register (F8): {len(shown)} rows, including {number}")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={"TL_AGENT_TOKEN": token, "TL_DB": db, "TL_ENV": os.environ.get("TL_ENV", "dev")},
    )

    async def session() -> dict[str, Any]:
        async with Client(params) as mcp:
            names = {t.name for t in (await mcp.list_tools()).tools}
            assert {"get_tag", "list_tag_classes", "list_code_values"} <= names
            classes = await mcp.call_tool("list_tag_classes", {})
            assert classes.structured_content is not None
            codes = [c["code"] for c in classes.structured_content["result"]]
            say(f"MCP list_tag_classes: {', '.join(codes[:4])} ...")
            result = await mcp.call_tool("get_tag", {"project": PROJECT, "number": number})
            assert not result.is_error and result.structured_content is not None
            return result.structured_content

    found = asyncio.run(session())
    assert found["number"] == number and found["class_code"] == "ControlValve"
    say(f"MCP get_tag: {found['number']}, {found['conformance']}, {len(found['issues'])} issue(s)")
    passed(7, "the API, the TUI tag register and an agent's MCP tools read the same tags")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "refused":
        refused()
    elif mode == "reads":
        reads()
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
