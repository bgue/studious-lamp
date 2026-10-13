"""Driver for dev/demos/P1-I2.sh: what a person, a client and an agent see of the documents.

Modes (first argument), each ending in a PASS line for its clause:

* ``refused``: clause 8. A person with the ``user`` role cannot void a document, issue a revision,
  claim a system link source or take a key the module builds; and no one, an admin included, can
  change a document through a generic command.
* ``reads``: clause 9. The same documents through the API, through the TUI document register
  (F7, headless pilot, embedded client) and through the MCP tools an agent has.

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AMY_PASSWORD, TL_DEMO_AGENT_TOKEN. Every expectation is an assert: a failing demo exits
non-zero. Nothing printed holds a password or a token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)
NUMBER = "ISO-1234"


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


def post(url: str, token: str, name: str, body: dict[str, Any]) -> tuple[int, str, str]:
    """``POST /commands/<name>``: the status, the error code (or ``ok``) and the stream id."""
    import httpx2

    response = httpx2.post(
        f"{url}/commands/{name}", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    data = response.json()
    code = "ok" if response.status_code == 200 else str(data["error"])
    return response.status_code, code, str(data.get("stream_id", ""))


def refused() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    url = os.environ["TL_DEMO_URL"]
    amy = sign_in(url, "amy", os.environ["TL_DEMO_AMY_PASSWORD"]).token
    boss = sign_in(url, *DEMO).token
    api = ApiClient(url, boss)
    try:
        document = api.get_document(PROJECT, NUMBER)
    finally:
        api.close()
    revision = document.revisions[0]
    mine = post(
        url, amy, "CreateRecord", {"scope": SCOPE, "record_type": "core.Record", "title": "Note"}
    )
    assert mine[:2] == (200, "ok"), mine
    attempts: list[tuple[str, str, dict[str, Any], int, str]] = [
        (
            "amy",
            "VoidDocument",
            {"scope": SCOPE, "stream_id": document.id, "reason": "x"},
            403,
            "forbidden",
        ),
        (
            "amy",
            "IssueRevision",
            {"scope": SCOPE, "stream_id": revision.id, "issue_status": "IFR"},
            403,
            "forbidden",
        ),
        (
            "amy",
            "AddLink",
            {
                "scope": SCOPE,
                "from_id": mine[2],
                "to_id": document.id,
                "relation": "references",
                "link_source": "rule",
            },
            422,
            "reserved_link_source",
        ),
        (
            "amy",
            "CreateRecord",
            {"scope": SCOPE, "record_type": "core.Record", "title": "t", "key": "ISO-9999@A"},
            422,
            "reserved_key",
        ),
        (
            "demo",
            "TransitionWorkflow",
            {
                "scope": SCOPE,
                "stream_id": document.id,
                "expected_version": document.version,
                "transition": "void",
            },
            422,
            "",
        ),
    ]
    for who, name, body, status, code in attempts:
        got = post(url, amy if who == "amy" else boss, name, body)
        assert got[0] == status and (not code or got[1] == code), (who, name, got)
        say(f"{who}: {name} refused ({got[0]} {got[1]})")
    still = ApiClient(url, boss)
    try:
        assert still.get_document(PROJECT, NUMBER).state != "Void"
    finally:
        still.close()
    passed(
        8, "a user cannot void, issue or claim a system link; no one changes a document generically"
    )


async def register(db: str, number: str) -> tuple[list[str], list[str]]:
    """Open the document register (F7) on the ledger as demo: the rows and the detail panel."""
    from textual.widgets import DataTable
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.document_register import DocumentRegisterScreen

    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo")
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("f7")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DocumentRegisterScreen)
            assert screen.query_one("#docs-table", DataTable).row_count >= 1
            shown = [v.number for v in screen.shown]
            assert number in shown, shown
            screen.query_one("#docs-table", DataTable).move_cursor(row=shown.index(number))
            await pilot.pause()
            from tl_tui.document_text import detail_lines

            assert screen.detail is not None
            return shown, detail_lines(screen.detail)
    finally:
        client.close()


def reads() -> None:
    from mcp import Client, StdioServerParameters
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    token = os.environ["TL_DEMO_AGENT_TOKEN"]
    api = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        listed = api.list_documents(PROJECT)
        say(f"API: {len(listed)} documents, e.g. {', '.join(d.number for d in listed[:3])}")
        document = api.get_document(PROJECT, NUMBER)
        classes = {r.code: r.status_class for r in document.revisions}
        assert classes and None not in classes.values(), classes
        say(f"API: {NUMBER} current {document.current_revision_code}; revisions {classes}")
        stale = api.get_document(PROJECT, NUMBER)
        assert stale.current_revision_code is not None
    finally:
        api.close()
    shown, lines = asyncio.run(register(db, NUMBER))
    say(f"TUI document register (F7): {len(shown)} rows, including {NUMBER}")
    for line in lines[:4]:
        say(f"  {line}")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={"TL_AGENT_TOKEN": token, "TL_DB": db, "TL_ENV": os.environ.get("TL_ENV", "dev")},
    )

    async def session() -> dict[str, Any]:
        async with Client(params) as mcp:
            names = {t.name for t in (await mcp.list_tools()).tools}
            assert {"list_documents", "get_document", "list_stale_links"} <= names
            result = await mcp.call_tool("get_document", {"project": PROJECT, "number": NUMBER})
            assert not result.is_error and result.structured_content is not None
            return result.structured_content

    found = asyncio.run(session())
    assert found["number"] == NUMBER
    assert found["current_revision_code"] == document.current_revision_code
    say(f"MCP get_document: {found['number']}, current {found['current_revision_code']}")
    passed(9, "the API, the TUI document register and an agent's MCP tools read the same documents")


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
