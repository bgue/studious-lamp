"""The hand-off from the first read to the feed, own-write ordering, ledger resets (review of S20).

Three faults a happy-path run does not show:

* an event committed after the grid's first read and before the feed starts must still arrive;
* a command's events can reach the feed before the command's response reaches the caller, and
  must not be shown as someone else's change;
* a server whose ledger went backwards (replaced, restored) must make the TUI read everything
  again instead of waiting for seqs that will never come.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from fakes import SCOPE, FakeClient
from fakes_live import FakeFeed, make_event
from harness import Harness
from helpers import run_pilot, screen_text
from remote_support import LIVE_TIMEOUT_S, OtherWriter, wait_for
from textual.pilot import Pilot
from tl_adapters.sqlite.uow import create_schema
from tl_core.ledger import Event
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.live import OwnWrites
from tl_tui.messages import ConnectionState
from tl_tui.remote import RemoteClient, RemoteFeed
from tl_tui.widgets.connection_banner import ConnectionBanner
from tl_tui.widgets.grid import RecordGrid


async def until(pilot: Pilot[Any], predicate: Any, timeout: float = 5.0, what: str = "") -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        await pilot.pause(0.02)


def row(grid: RecordGrid, key: str) -> dict[str, Any] | None:
    return next((r for r in grid.rows if r["key"] == key), None)


def after_the_first_load(monkeypatch: pytest.MonkeyPatch, action: Any) -> None:
    """Run ``action`` once, right after the grid's first load and before the feed has started."""
    original = RecordGrid.load
    done = {"yes": False}

    def load(self: RecordGrid, **kwargs: Any) -> bool:
        ok = original(self, **kwargs)
        if not done["yes"]:
            done["yes"] = True
            action()
        return ok

    monkeypatch.setattr(RecordGrid, "load", load)


# --- the gap between the first read and the feed ----------------------------------------------


def test_embedded_an_event_between_the_first_read_and_the_feed_start_is_marked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    mine, other = EmbeddedClient.for_sqlite(db), EmbeddedClient.for_sqlite(db)
    first = other.create_record(
        CreateRecord(
            actor="user:bob",
            source="t",
            scope=SCOPE,
            record_type="core.Record",
            key="G-1",
            title="a",
        )
    )

    def commit_in_the_gap() -> None:
        other.update_record(
            UpdateRecord(
                actor="user:bob",
                source="t",
                scope=SCOPE,
                stream_id=first.stream_id,
                expected_version=1,
                changes={"title": "in the gap"},
            )
        )

    after_the_first_load(monkeypatch, commit_in_the_gap)
    app = TlApp(mine, scope=SCOPE, feed=mine.change_feed(SCOPE))

    async def scenario(pilot: Pilot[Any]) -> None:
        grid = app.query_one("#grid", RecordGrid)
        await until(pilot, lambda: (r := row(grid, "G-1")) is not None and grid.is_marked(r["id"]))
        assert row(grid, "G-1")["title"] == "in the gap"  # type: ignore[index]

    try:
        run_pilot(app, scenario)
    finally:
        mine.close()
        other.close()


def test_remote_an_event_between_the_first_read_and_the_feed_start_is_marked(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = OtherWriter(harness)
    first = writer.create("G-1", "a")
    with harness.live() as server:
        client = RemoteClient.connect(server.base_url, server.token, timeout=LIVE_TIMEOUT_S)
        feed = client.change_feed(SCOPE)
        after_the_first_load(
            monkeypatch, lambda: writer.update(first.stream_id, 1, title="in the gap")
        )
        app = TlApp(client.as_client(), scope=SCOPE, mode="remote", feed=feed)

        async def scenario(pilot: Pilot[Any]) -> None:
            grid = app.query_one("#grid", RecordGrid)
            await until(
                pilot, lambda: (r := row(grid, "G-1")) is not None and grid.is_marked(r["id"])
            )

        try:
            run_pilot(app, scenario)
        finally:
            client.close()
            writer.close()


# --- own writes whose events beat the response ------------------------------------------------


class GatedClient(FakeClient):
    """``update_record`` commits, then waits for ``release`` before it answers (a slow response)."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()
        self.committed = threading.Event()
        self.result: Any = None

    def update_record(self, cmd: UpdateRecord) -> Any:
        self.result = super().update_record(cmd)
        self.committed.set()
        assert self.release.wait(10), "the test never released the response"
        return self.result


def build_gated() -> tuple[TlApp, GatedClient, RemoteClient, FakeFeed]:
    api = GatedClient()
    remote = RemoteClient(api)  # type: ignore[arg-type]  # delegates by name; the fake has them
    feed = FakeFeed()
    return TlApp(remote.as_client(), feed=feed), api, remote, feed


def own_update(api: GatedClient, remote: RemoteClient, title: str) -> threading.Thread:
    record = api.get_record(SCOPE, "FV-1002")
    assert record is not None
    cmd = UpdateRecord(
        actor="user:me",
        source="tui",
        scope=SCOPE,
        stream_id=record["id"],
        expected_version=record["version"],
        changes={"title": title},
    )
    thread = threading.Thread(target=remote.update_record, args=(cmd,), daemon=True)
    thread.start()
    return thread


def test_events_that_beat_the_response_are_not_shown_as_someone_elses() -> None:
    app, api, remote, feed = build_gated()
    api.__dict__.update(FakeClient.with_valve_example().__dict__)  # seed the gated fake

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        api.calls.clear()
        thread = own_update(api, remote, "mine")
        await until(pilot, api.committed.is_set, what="the commit")
        feed.push(*api.result.events)  # the stream is faster than the response
        await pilot.pause(0.4)
        assert "list_records" not in api.calls  # held, not refreshed
        assert not any(grid.is_marked(r["id"]) for r in grid.rows)
        api.release.set()
        thread.join(5)
        await pilot.pause(0.5)
        assert not any(grid.is_marked(r["id"]) for r in grid.rows)
        assert "list_records" not in api.calls and app._held == []  # pyright: ignore

    run_pilot(app, scenario)


def test_a_foreign_event_on_the_same_stream_is_marked_once_the_response_is_in() -> None:
    app, api, remote, feed = build_gated()
    api.__dict__.update(FakeClient.with_valve_example().__dict__)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        thread = own_update(api, remote, "mine")
        await until(pilot, api.committed.is_set, what="the commit")
        record = FakeClient.get_record(api, SCOPE, "FV-1002")
        assert record is not None
        bobs = FakeClient.update_record(
            api,
            UpdateRecord(
                actor="user:bob",
                source="t",
                scope=SCOPE,
                stream_id=record["id"],
                expected_version=record["version"],
                changes={"title": "bob"},
            ),
        )
        feed.push(*api.result.events, *bobs.events)
        await pilot.pause(0.3)
        assert not grid.is_marked(record["id"])  # held while the command is in flight
        api.release.set()
        thread.join(5)
        await until(pilot, lambda: grid.is_marked(record["id"]), what="bob's mark")

    run_pilot(app, scenario)


def test_a_response_that_never_comes_does_not_hold_events_forever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(OwnWrites, "HOLD_CAP_S", 0.4)
    app, api, remote, feed = build_gated()
    api.__dict__.update(FakeClient.with_valve_example().__dict__)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        thread = own_update(api, remote, "stuck")
        await until(pilot, api.committed.is_set, what="the commit")
        feed.push(*api.result.events)
        await pilot.pause(0.1)
        assert not any(grid.is_marked(r["id"]) for r in grid.rows)
        await until(pilot, lambda: any(grid.is_marked(r["id"]) for r in grid.rows), what="the cap")
        api.release.set()
        thread.join(5)

    run_pilot(app, scenario)


def test_classification_rules() -> None:
    own = OwnWrites()
    mine = make_event(1, stream="S1")
    other_stream = make_event(2, stream="S2")
    assert own.classify(mine) == "foreign"
    with own.in_flight("S1"):
        assert own.classify(mine) == "pending"
        assert own.classify(other_stream) == "foreign"
    with own.in_flight(None):
        assert own.classify(other_stream) == "pending"  # a command whose stream is not known
    assert own.classify(mine) == "foreign"  # the window closed without noting it


# --- a ledger that went backwards ---------------------------------------------------------------


class Sink:
    def __init__(self) -> None:
        self.seen: list[Event] = []
        self.resets: list[str] = []
        self.states: list[ConnectionState] = []

    def events(self, batch: list[Event]) -> None:
        self.seen.extend(batch)

    def connection(self, state: ConnectionState, detail: str = "") -> None:
        self.states.append(state)

    def reset(self, detail: str) -> None:
        self.resets.append(detail)


class ScriptedApi:
    """A server that holds ``head`` events; its first stream drops, the next one delivers."""

    def __init__(self) -> None:
        self.head = 5
        self.streams = 0

    def events_after(self, after: int, *, limit: int = 500, **_: Any) -> Any:
        events = [make_event(n) for n in range(after + 1, self.head + 1)][:limit]
        return SimpleNamespace(events=events, next_seq=after, has_more=False)

    def stream_events(self, *, after: int | None = None, **_: Any) -> Any:
        self.streams += 1
        if self.streams == 1:
            raise httpx2.ReadError("dropped")
        yield make_event((after or 0) + 1, version=3)
        threading.Event().wait(5)  # idle until closed

    def close(self) -> None:
        pass


def test_a_ledger_behind_the_cursor_resets_the_feed_and_resumes_from_the_new_head() -> None:
    api = ScriptedApi()
    feed = RemoteFeed(lambda: api, first_delay_s=0.02)  # type: ignore[arg-type,return-value]
    assert feed.head() == 5 and feed.cursor == 5
    sink, stop = Sink(), threading.Event()
    api.head = 2  # the ledger was replaced while the stream was down
    thread = threading.Thread(target=feed.follow, args=(sink, stop), daemon=True)
    thread.start()
    try:
        wait_for(lambda: sink.seen, what="an event from the new ledger")
        assert sink.resets == ["server ledger changed; reloaded"]
        assert [e.seq for e in sink.seen] == [3] and feed.cursor == 3
    finally:
        stop.set()
        thread.join(0.2)


def test_the_app_reads_everything_again_and_says_so_when_the_ledger_resets() -> None:
    client = FakeClient.with_valve_example()
    feed = FakeFeed()
    app = TlApp(client, feed=feed)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        client.calls.clear()
        feed.reset("server ledger changed; reloaded")
        banner = app.query_one("#connection", ConnectionBanner)
        await until(pilot, lambda: banner.display, what="the notice")
        # The banner is shown before the compositor has painted it; wait for the text.
        await until(
            pilot,
            lambda: "server ledger changed; reloaded" in screen_text(app),
            what="the notice on screen",
        )
        await until(pilot, lambda: "list_records" in client.calls, what="the reload")

    run_pilot(app, scenario)
