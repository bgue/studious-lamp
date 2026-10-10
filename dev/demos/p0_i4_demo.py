"""Driver for dev/demos/P0-I4.sh: three observers, two writers, measured latencies.

Reads TL_DEMO_URL, TL_DEMO_TOKEN and TL_DB from the environment (the script starts `tl serve`).
Observers (all started before the write):
  * a remote TUI under Textual's Pilot (headless): the time until the changed row is marked;
  * the SSE client the TUI uses (`RemoteFeed`): the time until the event arrives;
  * an in-process MCP server polled like an agent would (`search_records`): the time until it
    returns the new title.
Writers: `tl record create` in another process, then an embedded client (the embedded TUI's client)
updating that record. Latency is measured from the moment the writer has returned. Every
expectation is an assert, so a failing demo exits non-zero.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_core.ledger import Event
from tl_core.services.commands import UpdateRecord
from tl_mcp.server import build_server
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.messages import ConnectionState
from tl_tui.remote import RemoteClient
from tl_tui.widgets.grid import RecordGrid

SCOPE = "project:P123"
BUDGET_S = 2.0
NEW_TITLE = "Retitled by the embedded TUI"


class Watcher:
    """The SSE client: records when each event arrives."""

    def __init__(self) -> None:
        self.arrivals: dict[int, float] = {}
        self.seen: list[Event] = []

    def events_in(self, batch: list[Event]) -> None:
        now = time.monotonic()
        for event in batch:
            self.arrivals.setdefault(event.seq, now)
            self.seen.append(event)

    # FeedSink
    def connection(self, state: ConnectionState, detail: str = "") -> None: ...

    def reset(self, detail: str) -> None: ...


class Sink(Watcher):
    def events(self, batch: list[Event]) -> None:  # type: ignore[override]
        self.events_in(batch)


async def until(predicate: Any, timeout: float, what: str) -> float:
    start = time.monotonic()
    while not predicate():
        assert time.monotonic() - start < timeout, f"timed out waiting for {what}"
        await asyncio.sleep(0.01)
    return time.monotonic() - start


async def mcp_sees(server: Any, key: str, title: str, found: dict[str, float]) -> None:
    """Poll `search_records` every 50 ms, like an agent would, until the title shows up."""
    while True:
        hits = await server.call_tool("search_records", {"scope": SCOPE, "q": f"key:{key}"})
        rows = hits.structured_content["records"]
        if rows and rows[0]["title"] == title:
            found[key + title] = time.monotonic()
            return
        await asyncio.sleep(0.05)


def say(text: str) -> None:
    print(f"   {text}")


async def main() -> None:
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # Textual routes INFO lines to stdout
    url, token, db = os.environ["TL_DEMO_URL"], os.environ["TL_DEMO_TOKEN"], os.environ["TL_DB"]

    # Observer 1: a remote TUI, headless.
    tui_client = RemoteClient.connect(url, token)
    tui_feed = tui_client.change_feed(SCOPE)
    app = TlApp(tui_client.as_client(), scope=SCOPE, mode="remote", feed=tui_feed)

    # Observer 2: the SSE client on its own.
    sse_client = RemoteClient.connect(url, token)
    sse_feed = sse_client.change_feed(SCOPE)
    sink, stop = Sink(), threading.Event()
    sse_feed.head()
    thread = threading.Thread(target=sse_feed.follow, args=(sink, stop), daemon=True)
    thread.start()

    # Observer 3: an MCP server over the same ledger file.
    factory = SqliteUowFactory(Path(db))
    mcp = build_server(factory, actor="agent:triage")

    embedded = EmbeddedClient.for_sqlite(db)
    found: dict[str, float] = {}
    latencies: dict[str, float] = {}

    async with app.run_test(size=(120, 40)) as pilot:
        grid = app.query_one("#grid", RecordGrid)
        await pilot.pause(0.5)
        await until(lambda: getattr(sse_feed, "cursor", None) is not None, 5, "the SSE client")

        print("\n== write 1: `tl record create` in another process")
        mcp_task = asyncio.create_task(mcp_sees(mcp, "P123-D-0001", "Written by the CLI", found))
        subprocess.run(
            ["uv", "run", "tl", "record", "create", "--project", "P123", "--key", "P123-D-0001",
             "--title", "Written by the CLI", "--actor", "user:cli"],
            check=True, capture_output=True, text=True,
        )  # fmt: skip
        t0 = time.monotonic()  # the writer process has exited: its commit is behind us

        def title_marked(prefix: str) -> bool:
            """The demo record is in the grid, marked as changed elsewhere, with this title."""
            found_row = next((r for r in grid.rows if r["key"] == "P123-D-0001"), None)
            return (
                found_row is not None
                and found_row["title"].startswith(prefix)
                and grid.is_marked(found_row["id"])
            )

        await until(lambda: title_marked("Written"), 5, "the TUI mark")
        latencies["remote TUI (row marked)"] = time.monotonic() - t0
        await until(lambda: any(e.event_type == "Record.Created" for e in sink.seen), 5, "SSE")
        created = next(e for e in sink.seen if e.event_type == "Record.Created")
        latencies["SSE client (event)"] = max(0.0, sink.arrivals[created.seq] - t0)
        await asyncio.wait_for(mcp_task, 5)
        latencies["MCP agent (search_records)"] = max(
            0.0, found["P123-D-0001Written by the CLI"] - t0
        )
        record_id = created.stream_id
        say("measured from the moment the CLI exited:")
        for name, seconds in latencies.items():
            say(f"{name:<28} {seconds * 1000:7.0f} ms")
            assert seconds < BUDGET_S, f"{name} took {seconds:.2f} s"

        print("\n== write 2: an embedded client updates the same record (an embedded TUI's path)")
        latencies2: dict[str, float] = {}
        before = len(sink.seen)
        mcp_task = asyncio.create_task(mcp_sees(mcp, "P123-D-0001", NEW_TITLE, found))
        record = embedded.get_record(SCOPE, "P123-D-0001")
        assert record is not None
        result = embedded.update_record(
            UpdateRecord(actor="user:embedded", source="tui", scope=SCOPE, stream_id=record_id,
                         expected_version=record["version"], changes={"title": NEW_TITLE})
        )  # fmt: skip
        t1 = time.monotonic()
        seq = result.events[0].seq
        await until(lambda: title_marked("Retitled"), 5, "the TUI mark")
        latencies2["remote TUI (row marked)"] = time.monotonic() - t1
        await until(lambda: seq in sink.arrivals, 5, "SSE")
        latencies2["SSE client (event)"] = max(0.0, sink.arrivals[seq] - t1)
        await asyncio.wait_for(mcp_task, 5)
        latencies2["MCP agent (search_records)"] = max(0.0, found["P123-D-0001" + NEW_TITLE] - t1)
        assert len(sink.seen) == before + 1, "the SSE client saw an event twice or not at all"
        for name, seconds in latencies2.items():
            say(f"{name:<28} {seconds * 1000:7.0f} ms")
            assert seconds < BUDGET_S, f"{name} took {seconds:.2f} s"

    stop.set()
    sse_feed.close()
    thread.join(5)
    embedded.close()
    factory.close()
    tui_client.close()
    sse_client.close()


if __name__ == "__main__":
    asyncio.run(main())
