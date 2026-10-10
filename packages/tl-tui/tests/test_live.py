"""Live-update plumbing without a terminal: event rules, the embedded feed, the thread runner.

The embedded feed is tested on a real SQLite file: a write through this client arrives at once (the
bus), a write through a second client on the same file arrives by polling, and nothing arrives
twice. `LiveUpdates` is tested with a hand-driven feed against a minimal message pump.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fakes_live import FakeFeed
from tl_adapters.sqlite.uow import create_schema
from tl_core.ledger import Event
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_tui.embedded import EmbeddedClient
from tl_tui.live import (
    LiveUpdates,
    OwnWrites,
    describe_changes,
    detect_conflict,
    latest_by_record,
    touched_record_ids,
)
from tl_tui.messages import ConnectionChanged, LiveEvents

SCOPE = "project:P123"


def event(seq: int, kind: str, stream: str, version: int, actor: str = "user:bob", **payload: Any):
    return Event(
        event_type=kind,
        payload=payload,
        seq=seq,
        event_id=f"EV{seq:024d}",
        stream_id=stream,
        stream_type="core.Record",
        stream_version=version,
        scope=SCOPE,
        actor=actor,
        recorded_at="2026-10-10T09:00:00Z",  # type: ignore[arg-type]
        effective_at="2026-10-10T09:00:00Z",  # type: ignore[arg-type]
        correlation_id="C" * 26,
        causation_id=None,
        source="test",
        prev_hash=None,
        hash="0" * 64,
    )


# --- the rules ------------------------------------------------------------------------------


def test_record_events_touch_their_stream_and_link_events_touch_both_ends() -> None:
    events = [
        event(1, "Record.Updated", "R1", 2),
        event(2, "Pset.ValuesSet", "R2", 3),
        event(3, "Workflow.Transitioned", "R3", 4),
        event(4, "Link.Added", "L1", 1, from_ref="R4", to_ref="R5"),
        event(5, "File.Uploaded", "F1", 1),
        event(6, "Schema.EffectiveChanged", "S1", 1),
    ]
    assert touched_record_ids(events) == {"R1", "R2", "R3", "R4", "R5"}


def test_an_event_past_the_opened_version_is_a_conflict() -> None:
    mine = event(7, "Record.Updated", "R1", 3)
    theirs = event(8, "Record.Updated", "R1", 4, actor="user:carol")
    other = event(9, "Record.Updated", "R2", 9)
    assert detect_conflict("R1", 3, [mine, other]) is None  # not past what the form opened at
    assert detect_conflict("R1", 2, [mine, other, theirs]) is theirs  # the newest wins
    assert detect_conflict("R1", 4, [theirs]) is None
    link = event(10, "Link.Added", "L1", 8, from_ref="R1", to_ref="R2")
    assert detect_conflict("R1", 1, [link]) is None  # a link does not move the record's version


def test_latest_by_record_and_the_status_line() -> None:
    events = [
        event(1, "Record.Updated", "R1", 2),
        event(2, "Pset.ValuesSet", "R1", 3, actor="user:carol"),
        event(3, "Link.Added", "L1", 1, from_ref="R2", to_ref="R3"),
    ]
    assert latest_by_record(events)["R1"].seq == 2
    assert "L1" not in latest_by_record(events)
    assert describe_changes(events[:1]) == "Record changed by user:bob"
    assert describe_changes(events) == "3 records changed by 2 users"


def test_own_writes_is_bounded_and_remembers_the_newest() -> None:
    own = OwnWrites(capacity=3)
    for n in range(1, 6):
        own.note(
            CommandResult(
                stream_id="R", key="K", version=n, events=[event(n, "Record.Updated", "R", n)]
            )
        )
    assert len(own) == 3
    assert "EV" + "5".zfill(24) in own and "EV" + "1".zfill(24) not in own


# --- the thread runner ----------------------------------------------------------------------


class Pump:
    """The one thing LiveUpdates needs from a widget: a thread-safe `post_message`."""

    def __init__(self) -> None:
        self.messages: list[Any] = []
        self.lock = threading.Lock()

    def post_message(self, message: Any) -> bool:
        with self.lock:
            self.messages.append(message)
        return True


def wait_for(predicate: Any, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_live_updates_posts_events_and_states_in_order_and_stops() -> None:
    feed, pump = FakeFeed(), Pump()
    live = LiveUpdates(feed, pump)  # type: ignore[arg-type]
    live.start()
    wait_for(lambda: feed.started.is_set())
    a, b = event(1, "Record.Updated", "R1", 2), event(2, "Record.Updated", "R1", 3)
    feed.push(a, b)
    feed.state("unreachable", "down")
    wait_for(lambda: len(pump.messages) >= 3)
    first, second, third = pump.messages[:3]
    assert isinstance(first, ConnectionChanged) and first.state == "live"
    assert isinstance(second, LiveEvents) and [e.seq for e in second.events] == [1, 2]
    assert isinstance(third, ConnectionChanged) and (third.state, third.detail) == (
        "unreachable",
        "down",
    )
    live.stop()
    assert feed.closed and not live.running


def test_a_feed_that_raises_tells_the_user_instead_of_vanishing() -> None:
    class Broken:
        def follow(self, sink: Any, stop: threading.Event) -> None:
            raise RuntimeError("boom")

        def close(self) -> None: ...

    pump = Pump()
    live = LiveUpdates(Broken(), pump)  # type: ignore[arg-type]
    live.start()
    wait_for(lambda: pump.messages)
    live.stop()
    message = pump.messages[0]
    assert isinstance(message, ConnectionChanged) and message.state == "unreachable"
    assert "boom" in message.detail


# --- the embedded feed on a real ledger -------------------------------------------------------


def create(client: EmbeddedClient, key: str) -> CommandResult:
    return client.create_record(
        CreateRecord(
            actor="user:t",
            source="test",
            scope=SCOPE,
            record_type="core.Record",
            key=key,
            title=key,
        )
    )


@pytest.fixture
def two_clients(tmp_path: Path) -> Any:
    db = tmp_path / "tl.db"
    create_schema(db)
    mine, other = EmbeddedClient.for_sqlite(db), EmbeddedClient.for_sqlite(db)
    yield mine, other
    mine.close()
    other.close()


def test_own_writes_arrive_at_once_other_writers_by_polling_each_once(two_clients: Any) -> None:
    mine, other = two_clients
    create(mine, "OLD-1")  # before the feed starts: never delivered
    feed = mine.change_feed(SCOPE)
    assert feed is not None
    pump = Pump()
    live = LiveUpdates(feed, pump)  # type: ignore[arg-type]
    live.start()
    wait_for(lambda: pump.messages)  # "live"
    own = create(mine, "MINE-1")
    theirs = create(other, "THEIRS-1")
    want = {e.event_id for e in own.events + theirs.events}

    def delivered() -> list[Event]:
        with pump.lock:
            return [e for m in pump.messages if isinstance(m, LiveEvents) for e in m.events]

    wait_for(lambda: {e.event_id for e in delivered()} >= want)
    time.sleep(0.6)  # two more polls: a duplicate would show up now
    got = delivered()
    assert [e.event_id for e in got].count(own.events[0].event_id) == 1
    assert [e.event_id for e in got].count(theirs.events[0].event_id) == 1
    assert [e.seq for e in got] == sorted(e.seq for e in got)
    live.stop()
    assert not live.running


def test_the_feed_only_follows_the_scope_it_was_given(two_clients: Any) -> None:
    mine, other = two_clients
    feed = mine.change_feed(SCOPE)
    pump = Pump()
    live = LiveUpdates(feed, pump)  # type: ignore[arg-type]
    live.start()
    wait_for(lambda: pump.messages)
    other.create_record(
        CreateRecord(
            actor="user:t",
            source="test",
            scope="company",
            record_type="core.Record",
            key="C-1",
            title="c",
        )
    )
    inside = create(other, "IN-1")
    wait_for(
        lambda: any(
            isinstance(m, LiveEvents) and m.events[0].event_id == inside.events[0].event_id
            for m in pump.messages
        )
    )
    live.stop()
    seen = [e for m in pump.messages if isinstance(m, LiveEvents) for e in m.events]
    assert {e.scope for e in seen} == {SCOPE}


def test_update_events_carry_the_version_the_conflict_check_needs(two_clients: Any) -> None:
    mine, other = two_clients
    made = create(other, "V-1")
    record = other.get_record_by_id(made.stream_id)
    assert record is not None
    feed = mine.change_feed(SCOPE)
    pump = Pump()
    live = LiveUpdates(feed, pump)  # type: ignore[arg-type]
    live.start()
    wait_for(lambda: pump.messages)
    update = other.update_record(
        UpdateRecord(
            actor="user:bob",
            source="test",
            scope=SCOPE,
            stream_id=made.stream_id,
            expected_version=record["version"],
            changes={"title": "changed"},
        )
    )
    wait_for(lambda: any(isinstance(m, LiveEvents) for m in pump.messages))
    live.stop()
    got = [e for m in pump.messages if isinstance(m, LiveEvents) for e in m.events]
    assert detect_conflict(made.stream_id, record["version"], got) is not None
    assert got[-1].stream_version == update.version
