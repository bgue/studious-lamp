"""`RemoteFeed` against a real server: head, live delivery, and a server restart (no duplicates).

Writers are other processes' stand-ins (`OtherWriter`: own engine and bus on the same SQLite file),
so the server sees their events only through its poller, as it does for `tl record create`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from harness import Harness
from remote_support import OtherWriter, RestartableServer, restartable, wait_for
from tl_api.client import ApiClient
from tl_core.ledger import Event
from tl_tui.messages import ConnectionState
from tl_tui.remote import RemoteClient, RemoteFeed, find_head


class Recorder:
    """A feed sink that keeps what it is given (thread-safe enough: list appends)."""

    def __init__(self) -> None:
        self.events_seen: list[Event] = []
        self.states: list[ConnectionState] = []

    def events(self, batch: list[Event]) -> None:
        self.events_seen.extend(batch)

    def connection(self, state: ConnectionState, detail: str = "") -> None:
        self.states.append(state)

    @property
    def seqs(self) -> list[int]:
        return [e.seq for e in self.events_seen]


@contextmanager
def following(
    server: RestartableServer, scope: str | None = None
) -> Iterator[tuple[RemoteFeed, Recorder]]:
    client = RemoteClient.connect(server.base_url, server.token, timeout=2.0)
    feed = client.change_feed(scope)
    assert isinstance(feed, RemoteFeed)
    sink, stop = Recorder(), threading.Event()
    thread = threading.Thread(target=feed.follow, args=(sink, stop), daemon=True)
    thread.start()
    try:
        wait_for(
            lambda: feed.cursor is not None and "live" in sink.states, what="the feed to start"
        )
        yield feed, sink
    finally:
        stop.set()
        feed.close()
        thread.join(timeout=10)
        client.close()
        assert not thread.is_alive()


@pytest.mark.parametrize("count", [0, 1, 2, 3, 7, 8, 9, 40])
def test_find_head_is_the_last_seq_for_any_log_length(harness: Harness, count: int) -> None:
    writer = OtherWriter(harness)
    try:
        for n in range(count):
            writer.create(f"H-{n}")
        assert find_head(harness.api()) == count
    finally:
        writer.close()


def test_events_written_before_the_feed_started_are_not_delivered_later_ones_are(
    harness: Harness,
) -> None:
    writer = OtherWriter(harness)
    try:
        writer.create("OLD-1")
        with restartable(harness) as server, following(server) as (feed, sink):
            assert feed.cursor == 1
            made = writer.create("NEW-1")
            wait_for(lambda: made.events[0].seq in sink.seqs, what="the new event")
            assert sink.seqs == [2]
    finally:
        writer.close()


def test_a_restarted_server_resumes_from_the_last_seq_with_no_duplicates(harness: Harness) -> None:
    writer = OtherWriter(harness)
    try:
        with restartable(harness) as server, following(server) as (feed, sink):
            first = writer.create("A-1")
            wait_for(lambda: first.events[0].seq in sink.seqs, what="the first event")
            server.stop()
            wait_for(lambda: "unreachable" in sink.states, what="the outage to be noticed")
            during = [writer.create(f"D-{n}") for n in range(3)]  # written while the server is down
            server.start()
            want = [e.seq for r in during for e in r.events]
            wait_for(lambda: all(s in sink.seqs for s in want), what="the missed events")
            last = writer.create("Z-1")
            wait_for(lambda: last.events[0].seq in sink.seqs, what="an event after the restart")
            assert sink.seqs == [first.events[0].seq, *want, last.events[0].seq]
            assert sink.seqs == sorted(set(sink.seqs))  # in order, each once
            assert sink.states[0] == "live" and sink.states[-1] == "live"
    finally:
        writer.close()


def test_a_scope_filter_keeps_other_scopes_out(harness: Harness) -> None:
    writer = OtherWriter(harness)
    try:
        with restartable(harness) as server, following(server, scope="company") as (_, sink):
            writer.create("P-1")  # project:P123, not company
            probe = ApiClient(server.base_url, server.token)
            try:
                assert probe.events_after(0, scope="company").events == []
            finally:
                probe.close()
            assert sink.events_seen == []
    finally:
        writer.close()


def test_an_unreachable_server_at_start_is_reported_and_retried(harness: Harness) -> None:
    writer = OtherWriter(harness)
    try:
        server = RestartableServer(harness)  # not started yet
        client = RemoteClient.connect(server.base_url, server.token, timeout=1.0)
        feed = RemoteFeed(
            lambda: ApiClient(server.base_url, server.token, timeout=1.0), first_delay_s=0.05
        )
        sink, stop = Recorder(), threading.Event()
        thread = threading.Thread(target=feed.follow, args=(sink, stop), daemon=True)
        thread.start()
        try:
            wait_for(lambda: "unreachable" in sink.states, what="the unreachable state")
            assert feed.cursor is None
            server.start()
            wait_for(lambda: "live" in sink.states, what="the connection")
            made = writer.create("LATE-1")
            wait_for(lambda: made.events[0].seq in sink.seqs, what="the event")
        finally:
            stop.set()
            feed.close()
            thread.join(timeout=10)
            server.stop()
            client.close()
    finally:
        writer.close()
