"""Driver for dev/demos/P0-I8-C.sh: talks MCP to the dev server (`python -m tl_mcp.dev`) over stdio.

Reads TL_DB (a temporary ledger with a few records). Prints what an agent sees and asserts every
expectation, so a failing demo exits non-zero. The server is started as a child process, exactly
as an MCP client config would start it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from mcp import Client, StdioServerParameters

DB = os.environ["TL_DB"]
EXPECTED_TOOLS = {
    "gen",
    "query_db",
    "rebuild_projections",
    "render_screen",
    "run_tests",
    "seed",
    "send_test_webhook",
}


def say(text: str) -> None:
    print(f"   {text}")


def data(result: Any) -> dict[str, Any]:
    assert not result.is_error, result
    assert result.structured_content is not None
    return dict(result.structured_content)


def refusal(result: Any, needle: str) -> str:
    assert result.is_error, f"expected a refusal containing {needle!r}"
    text = "".join(getattr(block, "text", "") for block in result.content)
    assert needle in text, text
    return text


class Receiver(BaseHTTPRequestHandler):
    seen: list[dict[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("content-length", "0")))
        Receiver.seen.append({k.lower(): v for k, v in self.headers.items()})
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


async def main() -> None:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "VIRTUAL_ENV", "TL_DB")}
    env["TL_ENV"] = "dev"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "tl_mcp.dev", "--db", DB], env=env
    )
    async with Client(params) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == EXPECTED_TOOLS, tools
        say(f"tools: {', '.join(sorted(tools))}")

        print("\n== query_db: read-only SQL on the dev ledger")
        out = data(
            await client.call_tool(
                "query_db", {"sql": "SELECT key, title FROM cur_core_record ORDER BY key"}
            )
        )
        say(f"{out['row_count']} rows: {out['rows']}")
        assert out["row_count"] == 3
        for sql in (
            "DELETE FROM events",
            "SELECT secret FROM wh_secret",
            "SELECT 1; DROP TABLE events",
        ):
            say(
                "refused: "
                + refusal(await client.call_tool("query_db", {"sql": sql}), "refused")[:90]
            )

        print("\n== gen: codegen drift report")
        out = data(await client.call_tool("gen", {}))
        say(f"in_sync={out['in_sync']} files={out['file_count']} drift={out['drift']}")
        assert out["in_sync"] is True

        print("\n== rebuild_projections: damage a projection, rebuild it from the ledger")
        import sqlite3

        with sqlite3.connect(DB) as con:
            con.execute("DELETE FROM cur_core_record")
        out = data(
            await client.call_tool("query_db", {"sql": "SELECT count(*) FROM cur_core_record"})
        )
        assert out["rows"] == [[0]]
        out = data(await client.call_tool("rebuild_projections", {"only": ["core_record"]}))
        say(f"replayed {out['replayed']} events into {out['projectors']}")
        out = data(
            await client.call_tool("query_db", {"sql": "SELECT count(*) FROM cur_core_record"})
        )
        assert out["rows"] == [[3]]

        print("\n== render_screen: the TUI as SVG")
        out = data(
            await client.call_tool("render_screen", {"keys": ["enter"], "name": "demo-record"})
        )
        say(f"{len(out['svg'])} bytes of SVG saved as {out['file']}")
        assert out["svg"].startswith("<svg") and "Valve one" in out["text"]
        os.remove(out["file"])

        print("\n== send_test_webhook: a signed event to a loopback receiver (and a refusal)")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/hook"
        out = data(
            await client.call_tool(
                "send_test_webhook", {"url": url, "event_type": "Record.Created"}
            )
        )
        say(
            f"status {out['status']}, event {out['event_id']}, "
            f"receiver saw webhook-test={Receiver.seen[0].get('webhook-test')}"
        )
        assert out["ok"] and Receiver.seen[0].get("webhook-signature", "").startswith("v1,")
        server.shutdown()
        say(
            "refused: "
            + refusal(
                await client.call_tool("send_test_webhook", {"url": "http://example.com/hook"}),
                "refused",
            )[:90]
        )

        print("\n== run_tests: a filtered pytest, no shell")
        out = data(
            await client.call_tool(
                "run_tests",
                {"paths": ["packages/tl-mcp/tests/test_dev_guard.py"], "keyword": "loopback"},
            )
        )
        say(f"exit {out['exit_code']}: {out['summary']} (report {out['report']})")
        assert out["exit_code"] == 0
        say(
            "refused: "
            + refusal(await client.call_tool("run_tests", {"paths": ["/etc/passwd"]}), "refused")[
                :90
            ]
        )

        print("\n== resources")
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        templates = {
            str(t.uri_template) for t in (await client.list_resource_templates()).resource_templates
        }
        say(f"{len(uris)} resources, {len(templates)} templates")
        graph = json.loads((await client.read_resource("tl://dev/schema-graph")).contents[0].text)  # type: ignore[union-attr]
        say(f"schema graph: {len(graph['classes'])} classes, {len(graph['edges'])} edges")
        adr = (await client.read_resource("tl://dev/adr/0004-relay-orchestration")).contents[0].text  # type: ignore[union-attr]
        assert "Relay orchestration" in adr
        say("ADR 0004: " + adr.splitlines()[0])
        reports = json.loads((await client.read_resource("tl://dev/test-reports")).contents[0].text)  # type: ignore[union-attr]
        assert reports and reports[0]["name"].endswith(".txt")
        say(f"test reports: newest {reports[0]['name']}")
        try:
            await client.read_resource("tl://dev/adr/..%2f..%2fAGENTS")
        except Exception as exc:  # the server answers a resource error, the client raises
            say(f"traversal refused: {type(exc).__name__}")
        else:
            raise AssertionError("a path in a document name was accepted")


try:
    asyncio.run(main())
except Exception as exc:  # a refusal that should have been an answer, or the reverse
    print(f"DEMO FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
