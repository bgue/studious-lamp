"""The whole path in both modes: another writer, the change feed, the app on screen (P0-I4).

Remote: a real API server on loopback, `RemoteClient`, `RemoteFeed` (SSE), the app under Textual's
Pilot. Embedded: a real SQLite ledger, `EmbeddedClient`, `EmbeddedFeed`. In both, a write by another
engine on the same ledger must mark the row on screen within two seconds, with no terminal.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from harness import Harness
from helpers import run_pilot, screen_text
from remote_support import OtherWriter, restartable
from textual.pilot import Pilot
from tl_adapters.sqlite.uow import create_schema
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.remote import RemoteClient, RemoteFeed
from tl_tui.widgets.connection_banner import ConnectionBanner
from tl_tui.widgets.grid import RecordGrid

SCOPE = "project:P123"
LATENCY_BUDGET_S = 2.0


async def until(pilot: Pilot[Any], predicate: Any, timeout: float, what: str) -> float:
    start = time.monotonic()
    while not predicate():
        assert time.monotonic() - start < timeout, f"timed out waiting for {what}"
        await pilot.pause(0.02)
    return time.monotonic() - start


def row(grid: RecordGrid, key: str) -> dict[str, Any] | None:
    return next((r for r in grid.rows if r["key"] == key), None)


def test_remote_a_write_by_another_client_marks_the_row_within_two_seconds(
    harness: Harness,
) -> None:
    writer = OtherWriter(harness)
    seeded = writer.create("R-1", "Before")
    with harness.live() as server:
        client = RemoteClient.connect(server.base_url, server.token)
        feed = client.change_feed(SCOPE)
        assert isinstance(feed, RemoteFeed)
        app = TlApp(client.as_client(), scope=SCOPE, mode="remote", feed=feed)
        latencies: list[float] = []

        async def scenario(pilot: Pilot[Any]) -> None:
            grid = app.query_one("#grid", RecordGrid)
            await until(pilot, lambda: feed.cursor is not None and len(grid.rows) == 1, 5, "start")
            started = time.monotonic()
            writer.update(seeded.stream_id, 1, title="After")  # another process's write
            latencies.append(
                await until(
                    pilot,
                    lambda: (
                        (r := row(grid, "R-1")) is not None
                        and r["title"] == "After"
                        and grid.is_marked(r["id"])
                    ),
                    5,
                    "the mark",
                )
            )
            latencies.append(time.monotonic() - started)
            created = writer.create("R-2", "Brand new")
            await until(pilot, lambda: row(grid, "R-2") is not None, 5, "the new row")
            assert grid.is_marked(created.stream_id)
            assert "•" in screen_text(app) and "changed by user:bob" in screen_text(app)

        try:
            run_pilot(app, scenario)
        finally:
            client.close()
            writer.close()
        assert latencies[0] < LATENCY_BUDGET_S, latencies


def test_remote_the_banner_shows_during_an_outage_and_the_feed_resumes(harness: Harness) -> None:
    writer = OtherWriter(harness)
    with restartable(harness) as server:
        client = RemoteClient.connect(server.base_url, server.token, timeout=2.0)
        feed = client.change_feed(SCOPE)
        assert isinstance(feed, RemoteFeed)
        app = TlApp(client.as_client(), scope=SCOPE, mode="remote", feed=feed)

        async def scenario(pilot: Pilot[Any]) -> None:
            grid = app.query_one("#grid", RecordGrid)
            banner = app.query_one("#connection", ConnectionBanner)
            await until(pilot, lambda: feed.cursor is not None, 5, "start")
            server.stop()
            await until(pilot, lambda: banner.display, 6, "the banner")
            assert "unreachable" in screen_text(app) or "Connection lost" in screen_text(app)
            made = writer.create("DURING-1", "Written during the outage")
            server.start()
            await until(pilot, lambda: not banner.display, 8, "the banner to clear")
            await until(pilot, lambda: row(grid, "DURING-1") is not None, 5, "the missed record")
            assert grid.is_marked(made.stream_id)
            assert len([r for r in grid.rows if r["key"] == "DURING-1"]) == 1

        try:
            run_pilot(app, scenario)
        finally:
            client.close()
            writer.close()


def test_remote_an_unreachable_server_at_a_user_action_is_a_banner_not_a_crash() -> None:
    client = RemoteClient.connect("http://127.0.0.1:9", "token", timeout=0.5)  # nothing listens
    app = TlApp(client.as_client(), scope=SCOPE, mode="remote")

    async def scenario(pilot: Pilot[Any]) -> None:
        banner = app.query_one("#connection", ConnectionBanner)
        await until(pilot, lambda: banner.display, 5, "the banner")
        text = screen_text(app)
        assert "Server unreachable" in text
        assert "server unreachable" in text  # the status line from the failed grid load
        await pilot.press("r")  # reload again: still no crash
        await pilot.pause(0.2)
        assert app.is_running

    run_pilot(app, scenario)
    client.close()


def test_embedded_a_write_by_another_process_marks_the_row_within_two_seconds(
    tmp_path: Path,
) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    mine = EmbeddedClient.for_sqlite(db)
    other = EmbeddedClient.for_sqlite(db)
    first = other.create_record(
        CreateRecord(
            actor="user:bob",
            source="test",
            scope=SCOPE,
            record_type="core.Record",
            key="E-1",
            title="Before",
        )
    )
    feed = mine.change_feed(SCOPE)
    app = TlApp(mine, scope=SCOPE, feed=feed)

    async def scenario(pilot: Pilot[Any]) -> None:
        grid = app.query_one("#grid", RecordGrid)
        await until(pilot, lambda: len(grid.rows) == 1, 5, "the first load")
        await pilot.pause(0.5)  # the feed thread has started and taken the ledger head
        started = time.monotonic()
        other.update_record(
            UpdateRecord(
                actor="user:bob",
                source="test",
                scope=SCOPE,
                stream_id=first.stream_id,
                expected_version=1,
                changes={"title": "After"},
            )
        )
        await until(
            pilot,
            lambda: (
                (r := row(grid, "E-1")) is not None
                and r["title"] == "After"
                and grid.is_marked(r["id"])
            ),
            5,
            "the mark",
        )
        assert time.monotonic() - started < LATENCY_BUDGET_S

    try:
        run_pilot(app, scenario)
    finally:
        mine.close()
        other.close()
