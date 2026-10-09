"""Tests for the in-process bus (P0-I1-T07)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from tl_core.bus import InProcessBus, OrderedPublisher
from tl_core.ledger import AppendResult, Event, NewEvent

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_event(seq: int, scope: str = "project:P1", event_type: str = "Record.Created") -> Event:
    return Event(
        event_type=event_type,
        payload={},
        seq=seq,
        event_id=f"E{seq:025d}",
        stream_id="s1",
        stream_type="core.Record",
        stream_version=seq,
        scope=scope,
        actor="user:dev",
        recorded_at=NOW,
        effective_at=NOW,
        correlation_id="c",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash="0" * 64,
    )


class FakeLedger:
    def __init__(self, events: list[Event]) -> None:
        self.events = events

    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]:
        found = [e for e in self.events if e.seq > seq and (scope is None or e.scope == scope)]
        return found[:limit]

    def append(self, **kwargs: object) -> AppendResult:  # pragma: no cover - not used
        raise NotImplementedError

    def read_stream(
        self, stream_id: str, *, from_version: int = 1
    ) -> list[Event]:  # pragma: no cover
        raise NotImplementedError

    def head_seq(self) -> int:  # pragma: no cover
        raise NotImplementedError

    def stream_version(self, stream_id: str) -> int:  # pragma: no cover
        raise NotImplementedError


def test_publish_delivers_to_matching_subscribers_in_order() -> None:
    bus = InProcessBus()
    everything: list[int] = []
    only_a: list[int] = []
    only_updates: list[int] = []
    bus.subscribe(lambda e: everything.append(e.seq))
    bus.subscribe(lambda e: only_a.append(e.seq), scope="project:A")
    bus.subscribe(lambda e: only_updates.append(e.seq), event_types=["Record.Updated"])
    bus.publish(
        [
            make_event(1, "project:A"),
            make_event(2, "project:B", "Record.Updated"),
            make_event(3, "project:A", "Record.Updated"),
        ]
    )
    assert everything == [1, 2, 3]
    assert only_a == [1, 3]
    assert only_updates == [2, 3]


def test_close_stops_delivery() -> None:
    bus = InProcessBus()
    seen: list[int] = []
    sub = bus.subscribe(lambda e: seen.append(e.seq))
    bus.publish([make_event(1)])
    sub.close()
    bus.publish([make_event(2)])
    assert seen == [1]


def test_a_failing_callback_does_not_stop_others_or_the_publisher(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = InProcessBus()
    seen: list[int] = []

    def boom(_: Event) -> None:
        raise RuntimeError("subscriber bug")

    bus.subscribe(boom)
    bus.subscribe(lambda e: seen.append(e.seq))
    bus.publish([make_event(1), make_event(2)])
    assert seen == [1, 2]
    assert "bus subscriber failed" in caplog.text


def test_after_seq_replays_then_continues_without_repeats() -> None:
    history = [make_event(1), make_event(2), make_event(3, "project:B")]
    bus = InProcessBus(FakeLedger(history))
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq), after_seq=1)
    assert seen == [2, 3]
    bus.publish([make_event(3, "project:B"), make_event(4)])  # 3 was already replayed
    assert seen == [2, 3, 4]


def test_after_seq_replay_respects_scope_and_never_repeats_old_events() -> None:
    history = [make_event(1, "project:A"), make_event(2, "project:B"), make_event(3, "project:A")]
    bus = InProcessBus(FakeLedger(history))
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq), after_seq=0, scope="project:A")
    bus.publish([make_event(1, "project:A")])
    assert seen == [1, 3]


def test_without_after_seq_there_is_no_replay() -> None:
    bus = InProcessBus(FakeLedger([make_event(1)]))
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    assert seen == []


def test_new_event_is_importable_for_type_checkers() -> None:
    assert NewEvent(event_type="x", payload={}).schema_version == 1


def test_out_of_order_batch_is_delivered_in_seq_order() -> None:
    bus = InProcessBus()
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    bus.publish([make_event(3), make_event(2), make_event(4)])
    assert seen == [2, 3, 4]


def test_a_late_event_is_skipped_with_a_warning_not_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = InProcessBus()
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    bus.publish([make_event(5)])
    bus.publish([make_event(4)])
    assert seen == [5]
    assert "bus skipped seq 4" in caplog.text


def test_concurrent_publishers_are_serialised_and_keep_each_batch_ordered() -> None:
    bus = InProcessBus()
    seen: list[int] = []
    inside = 0
    overlaps = 0

    def on_event(event: Event) -> None:
        nonlocal inside, overlaps
        inside += 1
        if inside > 1:
            overlaps += 1
        seen.append(event.seq)
        inside -= 1

    bus.subscribe(on_event)
    barrier = threading.Barrier(2)

    def publisher(first: int) -> None:
        barrier.wait()
        bus.publish([make_event(seq) for seq in reversed(range(first, first + 50))])

    threads = [threading.Thread(target=publisher, args=(first,)) for first in (1, 51)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert overlaps == 0
    # whichever batch ran first is complete and ordered; the other is delivered after it or skipped
    # whole (its seqs are below the cursor) with warnings, never interleaved
    assert seen == sorted(seen)
    assert len(seen) in (50, 100)


def test_ordered_publisher_delivers_batches_in_enqueue_order() -> None:
    bus = InProcessBus()
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    publisher = OrderedPublisher(bus)
    publisher.enqueue([make_event(1), make_event(2)])
    publisher.enqueue([make_event(3)])
    publisher.drain()
    assert seen == [1, 2, 3]
    publisher.drain()  # idle drain is harmless
    assert seen == [1, 2, 3]


def test_enqueue_from_inside_a_callback_is_deferred_until_the_callback_returns() -> None:
    bus = InProcessBus()
    publisher = OrderedPublisher(bus)
    trace: list[str] = []

    def first(event: Event) -> None:
        trace.append(f"first-start-{event.seq}")
        if event.seq == 1:
            publisher.enqueue([make_event(2)])
            publisher.drain()  # nested: returns at once, the running drain delivers seq 2
            trace.append("first-nested-returned")
        trace.append(f"first-end-{event.seq}")

    other: list[int] = []
    bus.subscribe(first)
    bus.subscribe(lambda e: other.append(e.seq))
    publisher.enqueue([make_event(1)])
    publisher.drain()
    assert trace == [
        "first-start-1",
        "first-nested-returned",
        "first-end-1",
        "first-start-2",
        "first-end-2",
    ]
    assert other == [1, 2]


def test_a_second_thread_does_not_wait_for_a_slow_drain() -> None:
    bus = InProcessBus()
    publisher = OrderedPublisher(bus)
    started, release = threading.Event(), threading.Event()
    seen: list[int] = []

    def slow(event: Event) -> None:
        seen.append(event.seq)
        if event.seq == 1:
            started.set()
            assert release.wait(5)

    bus.subscribe(slow)
    publisher.enqueue([make_event(1)])
    drainer = threading.Thread(target=publisher.drain)
    drainer.start()
    assert started.wait(5)
    publisher.enqueue([make_event(2)])
    publisher.drain()  # returns immediately although the first callback is still running
    assert seen == [1]
    release.set()
    drainer.join(5)
    assert not drainer.is_alive()
    assert seen == [1, 2]


def test_a_failing_publish_is_logged_and_does_not_stop_later_batches(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class ExplodingBus(InProcessBus):
        def publish(self, events: Sequence[Event]) -> None:
            if events[0].seq == 1:
                raise RuntimeError("bus bug")
            super().publish(events)

    bus = ExplodingBus()
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    publisher = OrderedPublisher(bus)
    publisher.enqueue([make_event(1)])
    publisher.enqueue([make_event(2)])
    publisher.drain()
    assert seen == [2]
    assert "bus publish failed" in caplog.text
    publisher.enqueue([make_event(3)])
    publisher.drain()  # the drainer flag was reset
    assert seen == [2, 3]
