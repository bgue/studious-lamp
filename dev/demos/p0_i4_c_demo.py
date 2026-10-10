"""Driver for dev/demos/P0-I4-C.sh: the API client, the query language, files and MCP.

Reads TL_DEMO_URL, TL_DEMO_TOKEN and TL_DB from the environment (the shell script starts the
server).
Every expectation is an assert, so a failing demo exits non-zero.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx2
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.client import ApiClient
from tl_core.query import QuerySyntaxError
from tl_core.services.commands import CreateRecord
from tl_core.services.links import AddLink
from tl_mcp.server import build_server

SCOPE = "project:P123"


def say(text: str) -> None:
    print(f"   {text}")


def main() -> None:
    api = ApiClient(os.environ["TL_DEMO_URL"], os.environ["TL_DEMO_TOKEN"])

    print("\n== records over HTTP (the actor is the token's, never the body's)")
    ids = {}
    for key, title in [
        ("P123-V-0001", "Gate valve"),
        ("P123-V-0002", "Check valve"),
        ("P123-P-0001", "Pump skid"),
    ]:
        made = api.create_record(
            CreateRecord(
                actor="user:ignored",
                source="tui",
                scope=SCOPE,
                record_type="core.Record",
                title=title,
                key=key,
            )
        )
        ids[key] = made.stream_id
        say(f"created {key} v{made.version} by {made.events[0].actor} via {made.events[0].source}")
    api.add_link(
        AddLink(
            actor="x",
            source="tui",
            scope=SCOPE,
            from_id=ids["P123-V-0001"],
            to_id=ids["P123-P-0001"],
            relation="requires",
        )
    )

    print("\n== the query language, parsed by the server")
    found = api.query_records(SCOPE, "valve -title~check")
    say(f"valve -title~check -> {[r['key'] for r in found]}")
    assert [r["key"] for r in found] == ["P123-V-0001"]
    say(f"count(valve) -> {api.count_records(SCOPE, 'valve')}")
    try:
        api.query_records(SCOPE, "title~gate (")
    except QuerySyntaxError as exc:
        say(f"syntax error at position {exc.position}: {exc}")
        assert exc.position >= 0
    else:
        raise AssertionError("a syntax error was accepted")

    print("\n== links and trace")
    tree = api.trace(ids["P123-V-0001"])
    say(f"trace: {tree.key} -> {[c.key for c in tree.children]}")
    assert [c.key for c in tree.children] == ["P123-P-0001"]

    print("\n== files: upload and download as an attachment")
    work = Path(tempfile.mkdtemp())
    pdf = work / "mtr.pdf"
    pdf.write_bytes(b"%PDF-1.7 mill test report\n")
    result = api.upload_file(SCOPE, ids["P123-V-0001"], pdf, slot="report")
    say(f"{result.file_id} {result.status} sha256={result.sha256[:12]}...")
    assert (
        result.status == "available"
        and api.download_file(SCOPE, result.file_id) == pdf.read_bytes()
    )
    raw = httpx2.get(
        f"{api.base_url}/files/{result.file_id}/content",
        params={"scope": SCOPE},
        headers={"Authorization": f"Bearer {os.environ['TL_DEMO_TOKEN']}"},
    )
    say(f"Content-Disposition: {raw.headers['content-disposition']}")
    say(f"X-Content-Type-Options: {raw.headers['x-content-type-options']}")
    assert raw.headers["content-disposition"].startswith("attachment")
    assert raw.headers["x-content-type-options"] == "nosniff"

    print("\n== the change feed over HTTP (paged)")
    page = api.events_after(0, limit=3)
    say(f"first page: seq {[e.seq for e in page.events]}, has_more={page.has_more}")

    print("\n== MCP read tools, in process, on the same ledger (actor agent:triage)")
    factory = SqliteUowFactory(Path(os.environ["TL_DB"]))
    server = build_server(factory, actor="agent:triage")

    async def run() -> None:
        hits = await server.call_tool("search_records", {"scope": SCOPE, "q": "valve"})
        say(f"search_records valve -> {[r['key'] for r in hits.structured_content['records']]}")
        links = await server.call_tool("get_links", {"record": "P123-V-0001", "scope": SCOPE})
        rows = links.structured_content["result"]
        say(f"get_links P123-V-0001 -> {[(r['direction'], r['other_key']) for r in rows]}")
        trace = await server.call_tool("trace", {"record": "P123-V-0001", "scope": SCOPE})
        tree = trace.structured_content
        say(f"trace -> {tree['key']} with {len(tree['children'])} child")
        resource = list(await server.read_resource(f"tl://record/{SCOPE}/P123-V-0001"))  # type: ignore[arg-type]
        body = json.loads(resource[0].content)
        say(f"tl://record/... -> {body['record']['title']!r} with {len(body['links'])} link")
        assert len(hits.structured_content["records"]) == 2 and len(body["links"]) == 1

    asyncio.run(run())
    factory.close()
    api.close()


if __name__ == "__main__":
    main()
