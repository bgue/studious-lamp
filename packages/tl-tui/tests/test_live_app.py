"""Live updates in the app, driven by a hand-fed feed over the FakeClient (P0-I4).

The feed thread, the worker thread and the UI thread are all real; only the source of events and
the data are fake. What is proved: another client's change marks the row without blocking the UI,
own changes do not, a burst is coalesced, an open record follows its changes, and a lost
connection shows the banner and recovers.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_live import FakeFeed
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from tl_core.ledger import Event
from tl_core.services.commands import UpdateRecord
from tl_tui.app import TlApp
from tl_tui.live import OwnWrites
from tl_tui.widgets.connection_banner import ConnectionBanner
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.record_view import RecordView


class SlowClient(FakeClient):
    """Reads take ``delay`` seconds and remember which thread ran them."""

    def __init__(self) -> None:
        super().__init__()
        self.delay = 0.0
        self.read_threads: list[str] = []

    def list_records(self, scope: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.read_threads.append(threading.current_thread().name)
        time.sleep(self.delay)
        return super().list_records(scope, **kwargs)


def bob_updates(client: FakeClient, key: str, **changes: Any) -> list[Event]:
    record = client.get_record(SCOPE, key)
    assert record is not None
    result = client.update_record(
        UpdateRecord(
            actor="user:bob",
            source="test",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            changes=changes,
        )
    )
    return result.events


async def until(pilot: Pilot[Any], predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        await pilot.pause(0.02)


def build(client: FakeClient | None = None) -> tuple[TlApp, FakeClient, FakeFeed]:
    client = client or FakeClient.with_valve_example()
    feed = FakeFeed()
    return TlApp(client, feed=feed), client, feed


def grid_of(app: TlApp) -> RecordGrid:
    return app.query_one("#grid", RecordGrid)


def row_of(grid: RecordGrid, key: str) -> dict[str, Any]:
    return next(r for r in grid.rows if r["key"] == key)


def test_another_clients_change_marks_the_row_and_says_who() -> None:
    app, client, feed = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        record_id = row_of(grid, "FV-1002")["id"]
        assert not grid.is_marked(record_id)
        feed.push(*bob_updates(client, "FV-1002", title="Renamed by Bob"))
        await until(pilot, lambda: grid.is_marked(record_id))
        assert row_of(grid, "FV-1002")["title"] == "Renamed by Bob"
        assert not grid.is_marked(row_of(grid, "FV-1001")["id"])
        text = screen_text(app)
        assert "Renamed by Bob" in text and "•" in text
        assert "Record changed by user:bob" in text

    run_pilot(app, scenario)


def test_a_new_record_from_elsewhere_appears_marked() -> None:
    app, client, feed = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        before = len(grid.rows)
        client._seed("FV-9000", "Brand new", "Design")  # pyright: ignore[reportPrivateUsage]
        created = client.history(
            next(r for r in client._records.values() if r["key"] == "FV-9000")["id"]
        )  # pyright: ignore[reportPrivateUsage]
        feed.push(*created)
        await until(pilot, lambda: len(grid.rows) == before + 1)
        assert grid.is_marked(row_of(grid, "FV-9000")["id"])

    run_pilot(app, scenario)


def test_the_ui_stays_responsive_while_the_refresh_reads_in_a_worker() -> None:
    client = SlowClient()
    for n in range(3):
        client._seed(f"S-{n}", f"Row {n}", "Design")  # pyright: ignore[reportPrivateUsage]
    app, _, feed = build(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        client.read_threads.clear()
        client.delay = 0.6
        started = time.monotonic()
        feed.push(*bob_updates(client, "S-1", title="slow"))
        await until(pilot, lambda: bool(client.read_threads))
        await pilot.press("down")  # the loop must answer while the worker sleeps
        assert grid.cursor_row == 1
        assert time.monotonic() - started < 0.55
        assert client.read_threads[0] != threading.main_thread().name
        await until(pilot, lambda: row_of(grid, "S-1")["title"] == "slow")
        assert grid.cursor_row == 1  # the cursor stayed on its row through the refresh

    run_pilot(app, scenario)


def test_own_changes_are_not_marked_and_cause_no_refresh() -> None:
    client = FakeClient.with_valve_example()
    own = OwnWrites()
    setattr(client, "own_writes", own)  # noqa: B010
    app, _, feed = build(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        events = bob_updates(client, "FV-1002", title="mine")
        client.calls.clear()
        own.note(type("R", (), {"events": events})())  # pyright: ignore
        feed.push(*events)
        await pilot.pause(0.3)
        assert "list_records" not in client.calls
        assert not grid.is_marked(row_of(grid, "FV-1002")["id"])

    run_pilot(app, scenario)


def test_a_burst_of_events_is_coalesced_into_a_few_reads() -> None:
    app, client, feed = build(FakeClient.with_valve_example(extra_rows=5))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        client.calls.clear()
        last: list[Event] = []
        for n in range(40):
            last = bob_updates(client, "FV-1003", title=f"burst {n}")
            feed.push(*last)
        await until(pilot, lambda: row_of(grid, "FV-1003")["title"] == "burst 39")
        await pilot.pause(0.2)
        assert client.calls.count("list_records") <= 8

    run_pilot(app, scenario)


def test_the_mark_fades_after_highlight_seconds() -> None:
    app, client, feed = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        grid.highlight_seconds = 0.4
        feed.push(*bob_updates(client, "FV-1002", title="brief"))
        record_id = row_of(grid, "FV-1002")["id"]
        await until(pilot, lambda: grid.is_marked(record_id))
        await until(pilot, lambda: not grid.is_marked(record_id))
        await until(pilot, lambda: "•" not in screen_text(app))

    run_pilot(app, scenario)


def test_a_result_that_arrives_after_a_sort_is_dropped() -> None:
    client = SlowClient()
    for n in range(3):
        client._seed(f"S-{n}", f"Row {n}", "Design")  # pyright: ignore[reportPrivateUsage]
    app, _, feed = build(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        client.read_threads.clear()
        client.delay = 0.5
        feed.push(*bob_updates(client, "S-2", title="late"))
        await until(pilot, lambda: bool(client.read_threads))
        client.delay = 0.0
        grid.sort_by("key")
        grid.sort_by("key")  # descending now
        keys_after_sort = [r["key"] for r in grid.rows]
        assert keys_after_sort == sorted(keys_after_sort, reverse=True)
        await pilot.pause(0.8)  # the slow worker finishes; its older answer must not replace rows
        assert [r["key"] for r in grid.rows] == keys_after_sort

    run_pilot(app, scenario)


def test_an_open_record_follows_a_change_made_elsewhere() -> None:
    app, client, feed = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")  # opens FV-1001
        await pilot.pause()
        view = app.query_one(RecordView)
        assert view.record is not None and view.record["key"] == "FV-1001"
        version = view.record["version"]
        feed.push(*bob_updates(client, "FV-1001", title="Changed under you"))
        await until(pilot, lambda: view.record is not None and view.record["version"] > version)
        assert view.record["title"] == "Changed under you"
        assert "Changed under you" in screen_text(app)

    run_pilot(app, scenario)


def test_a_change_to_another_record_does_not_reload_the_open_one() -> None:
    app, client, feed = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        events = bob_updates(client, "FV-1002", title="elsewhere")
        client.calls.clear()
        feed.push(*events)
        await until(pilot, lambda: "list_records" in client.calls)
        await pilot.pause(0.2)
        assert "get_record" not in client.calls

    run_pilot(app, scenario)


def test_the_banner_shows_while_unreachable_and_clears_when_back() -> None:
    app, client, feed = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        banner = app.query_one("#connection", ConnectionBanner)
        assert not banner.display
        feed.state("unreachable", "connection refused")
        await until(pilot, lambda: banner.display)
        text = screen_text(app)
        assert "Server unreachable" in text and "connection refused" in text
        feed.state("reconnecting", "event stream closed")
        await until(pilot, lambda: banner.state == "reconnecting")
        assert "reconnecting" in screen_text(app)
        client.calls.clear()
        feed.state("live")
        await until(pilot, lambda: not banner.display)
        assert "Connection restored" in screen_text(app)
        await until(pilot, lambda: "list_records" in client.calls)  # rows re-read after the outage

    run_pilot(app, scenario)


def test_a_failed_refresh_keeps_the_rows_and_says_why() -> None:
    import httpx2
    from tl_api.client.base import ApiUnavailableError

    client = FakeClient.with_valve_example()
    app, _, feed = build(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = grid_of(app)
        keys_before = [r["key"] for r in grid.rows]
        events = bob_updates(client, "FV-1002", title="x")

        def down(*args: Any, **kwargs: Any) -> Any:
            raise ApiUnavailableError(httpx2.ConnectError("refused"))

        client.list_records = down  # type: ignore[method-assign]
        feed.push(*events)
        await until(pilot, lambda: "server unreachable" in screen_text(app))
        assert [r["key"] for r in grid.rows] == keys_before

    run_pilot(app, scenario)
