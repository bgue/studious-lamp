"""SubscriptionRegistry: filtering, dedupe across sources, resume, ordering and queues."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from tl_core.bus import InProcessBus
from tl_core.changefeed import SubscriptionFilter, SubscriptionOverflow, SubscriptionRegistry
from tl_core.ledger import Event

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_event(
    seq: int,
    event_type: str = "Record.Created",
    scope: str = "project:P1",
    stream_id: str = "R1",
    payload: dict[str, Any] | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        payload=payload or {},
        seq=seq,
        event_id=f"E{seq:025d}",
        stream_id=stream_id,
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
    def __init__(self, events: list[Event] | None = None) -> None:
        self.events: list[Event] = list(events or [])
        self.on_read: Callable[[int], None] | None = None
        self.reads = 0

    def head_seq(self) -> int:
        return max((e.seq for e in self.events), default=0)

    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]:
        self.reads += 1
        if self.on_read is not None:
            self.on_read(self.reads)
        found = [e for e in self.events if e.seq > seq and (scope is None or e.scope == scope)]
        return found[:limit]


def collect(
    registry: SubscriptionRegistry, flt: SubscriptionFilter | None = None, **kwargs: Any
) -> list[int]:
    got: list[int] = []
    registry.subscribe(lambda event: got.append(event.seq), flt, **kwargs)
    return got


# --- delivery and filters -----------------------------------------------------------------------


def test_events_reach_matching_subscribers_in_seq_order() -> None:
    registry = SubscriptionRegistry()
    everything = collect(registry)
    links = collect(registry, SubscriptionFilter.of(event_types=["Link.*"]))
    company = collect(registry, SubscriptionFilter(scope="company"))
    registry.dispatch(
        [
            make_event(3, "Link.Added", scope="company"),
            make_event(1, "Record.Created"),
            make_event(2, "Link.Retracted"),
        ]
    )
    assert everything == [1, 2, 3]
    assert links == [2, 3]
    assert company == [3]


def test_a_record_id_filter_hears_about_its_links() -> None:
    registry = SubscriptionRegistry()
    got = collect(registry, SubscriptionFilter.of(record_ids=["R9"]))
    registry.dispatch(
        [
            make_event(1, stream_id="R1"),
            make_event(2, stream_id="R9"),
            make_event(3, "Link.Added", stream_id="L1", payload={"from_ref": "R1", "to_ref": "R9"}),
        ]
    )
    assert got == [2, 3]


def test_the_same_event_offered_twice_is_delivered_once() -> None:
    registry = SubscriptionRegistry()
    got = collect(registry)
    registry.dispatch([make_event(1), make_event(2)])
    registry.dispatch([make_event(2), make_event(3)])
    registry.dispatch([make_event(1), make_event(3)])
    assert got == [1, 2, 3]


def test_high_water_tracks_the_highest_seq_dispatched() -> None:
    registry = SubscriptionRegistry()
    assert registry.high_water == -1
    registry.dispatch([make_event(4), make_event(2)])
    assert registry.high_water == 4
    registry.dispatch([])
    assert registry.high_water == 4


def test_a_callback_that_raises_is_isolated() -> None:
    registry = SubscriptionRegistry()

    def boom(event: Event) -> None:
        raise ValueError("bad")

    registry.subscribe(boom)
    got = collect(registry)
    registry.dispatch([make_event(1), make_event(2)])
    assert got == [1, 2]
    assert len(registry) == 2  # the failing subscriber is kept; it still has a cursor


def test_close_stops_delivery_and_registry_close_drops_everyone() -> None:
    registry = SubscriptionRegistry()
    got: list[int] = []
    sub = registry.subscribe(lambda event: got.append(event.seq))
    other = collect(registry)
    registry.dispatch([make_event(1)])
    sub.close()
    sub.close()  # idempotent
    registry.dispatch([make_event(2)])
    assert got == [1]
    assert other == [1, 2]
    assert len(registry) == 1
    registry.close()
    registry.dispatch([make_event(3)])
    assert other == [1, 2]
    assert len(registry) == 0


def test_a_callback_may_subscribe_and_close_itself() -> None:
    registry = SubscriptionRegistry()
    late: list[int] = []
    handles: list[Any] = []

    def first(event: Event) -> None:
        handles[0].close()
        registry.subscribe(lambda e: late.append(e.seq))

    handles.append(registry.subscribe(first))
    registry.dispatch([make_event(1)])
    registry.dispatch([make_event(2)])
    assert late == [2]  # subscribed during event 1, so it hears events after 1
    assert len(registry) == 1


# --- live versus resume -------------------------------------------------------------------------


def test_without_a_ledger_a_live_subscription_starts_at_the_high_water_mark() -> None:
    registry = SubscriptionRegistry()
    registry.dispatch([make_event(1), make_event(2)])
    got = collect(registry)
    registry.dispatch([make_event(2), make_event(3)])
    assert got == [3]


def test_with_a_ledger_a_live_subscription_starts_at_the_ledger_head() -> None:
    ledger = FakeLedger([make_event(1), make_event(2)])
    registry = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    got = collect(registry)
    registry.dispatch([make_event(1), make_event(2), make_event(3)])
    assert got == [3]
    assert ledger.reads == 0  # live subscriptions never replay


def test_after_seq_replays_the_ledger_then_continues_live() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 6)])
    registry = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    got = collect(registry, after_seq=2)
    assert got == [3, 4, 5]
    registry.dispatch([make_event(5), make_event(6)])
    assert got == [3, 4, 5, 6]


def test_replay_applies_the_filter_and_pushes_the_scope_down() -> None:
    ledger = FakeLedger(
        [
            make_event(1, "Link.Added", scope="company"),
            make_event(2, "Record.Created", scope="company"),
            make_event(3, "Link.Added", scope="project:P1"),
        ]
    )
    registry = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    got = collect(
        registry, SubscriptionFilter(scope="company", event_types=("Link.*",)), after_seq=0
    )
    assert got == [1]


def test_replay_pages_through_a_long_backlog() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 1201)])
    registry = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    got = collect(registry, after_seq=0)
    assert got == list(range(1, 1201))
    assert ledger.reads == 4  # 500 + 500 + 200, then an empty read


def test_after_seq_without_a_ledger_only_sets_the_cursor() -> None:
    registry = SubscriptionRegistry()
    got = collect(registry, after_seq=5)
    registry.dispatch([make_event(n) for n in range(3, 9)])
    assert got == [6, 7, 8]


def test_an_event_committed_during_replay_arrives_exactly_once_and_in_order() -> None:
    ledger = FakeLedger([make_event(1), make_event(2)])
    registry = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    threads: list[threading.Thread] = []

    def during_replay(read_number: int) -> None:
        if read_number != 2:  # the read that finds the ledger empty
            return
        ledger.events.append(make_event(3))
        thread = threading.Thread(target=registry.dispatch, args=([make_event(3)],), daemon=True)
        thread.start()
        thread.join(0.2)  # it must wait for the replay: the registry lock is held
        assert thread.is_alive()
        threads.append(thread)

    ledger.on_read = during_replay
    got = collect(registry, after_seq=0)
    for thread in threads:
        thread.join(5)
    assert got == [1, 2, 3]


# --- ordering under concurrent sources ----------------------------------------------------------


def test_a_second_source_cannot_overtake_a_delivery_in_progress() -> None:
    registry = SubscriptionRegistry()
    got: list[int] = []
    inside = threading.Event()
    gate = threading.Event()

    def slow(event: Event) -> None:
        if event.seq == 1:
            inside.set()
            assert gate.wait(5)
        got.append(event.seq)

    registry.subscribe(slow)
    first = threading.Thread(target=registry.dispatch, args=([make_event(1)],), daemon=True)
    second = threading.Thread(target=registry.dispatch, args=([make_event(2)],), daemon=True)
    first.start()
    assert inside.wait(5)
    second.start()
    second.join(0.2)
    assert got == []  # event 2 waits until event 1's callback returns
    gate.set()
    first.join(5)
    second.join(5)
    assert got == [1, 2]


def test_two_sources_feeding_the_same_events_deliver_each_once_in_order() -> None:
    registry = SubscriptionRegistry()
    got = collect(registry)
    total = 3000
    events = [make_event(n) for n in range(1, total + 1)]

    def feed(step: int) -> None:
        for start in range(0, total, step):
            registry.dispatch(events[start : start + step])

    threads = [threading.Thread(target=feed, args=(step,), daemon=True) for step in (1, 7, 64)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert got == list(range(1, total + 1))


# --- the in-process bus -------------------------------------------------------------------------


def test_attach_feeds_the_registry_from_a_bus_and_detach_stops_it() -> None:
    bus = InProcessBus()
    registry = SubscriptionRegistry()
    got = collect(registry, SubscriptionFilter.of(event_types=["Record.*"]))
    link = registry.attach(bus)
    bus.publish([make_event(1), make_event(2, "Link.Added")])
    bus.publish([make_event(3, "Record.Updated")])
    link.close()
    bus.publish([make_event(4)])
    assert got == [1, 3]


def test_the_bus_and_a_poller_style_feed_can_overlap() -> None:
    bus = InProcessBus()
    registry = SubscriptionRegistry()
    got = collect(registry)
    registry.attach(bus)
    bus.publish([make_event(1), make_event(2)])
    registry.dispatch([make_event(2), make_event(3)])  # what a poller would add
    bus.publish([make_event(3), make_event(4)])
    assert got == [1, 2, 3, 4]


# --- queue subscriptions ------------------------------------------------------------------------


def test_a_queue_subscription_hands_events_to_another_thread() -> None:
    registry = SubscriptionRegistry()
    sub = registry.subscribe_queue()
    assert sub.get() is None
    registry.dispatch([make_event(1), make_event(2), make_event(3)])
    first = sub.get()
    assert first is not None and first.seq == 1
    assert [e.seq for e in sub.get_many(10)] == [2, 3]
    assert sub.get_many(10) == []
    assert sub.last_seq == 3
    assert sub.overflowed is False


def test_get_waits_for_an_event_up_to_the_timeout() -> None:
    registry = SubscriptionRegistry()
    sub = registry.subscribe_queue()
    started = time.monotonic()
    assert sub.get(timeout=0.05) is None
    assert time.monotonic() - started >= 0.04
    threading.Timer(0.05, registry.dispatch, args=([make_event(1)],)).start()
    event = sub.get(timeout=5)
    assert event is not None and event.seq == 1


def test_a_full_queue_overflows_without_blocking_the_dispatcher() -> None:
    registry = SubscriptionRegistry()
    sub = registry.subscribe_queue(maxsize=3)
    other = collect(registry)
    started = time.monotonic()
    registry.dispatch([make_event(n) for n in range(1, 11)])
    assert time.monotonic() - started < 1
    assert other == list(range(1, 11))  # other subscribers are unaffected
    assert sub.overflowed is True
    assert len(registry) == 1  # the overflowed feed was dropped
    assert [e.seq for e in sub.get_many(10)] == [1, 2, 3]


def test_after_an_overflow_the_consumer_drains_then_learns_where_to_resume() -> None:
    registry = SubscriptionRegistry()
    sub = registry.subscribe_queue(maxsize=3)
    registry.dispatch([make_event(n) for n in range(1, 11)])
    drained = [sub.get(), sub.get(), sub.get()]
    assert [e.seq for e in drained if e is not None] == [1, 2, 3]
    with pytest.raises(SubscriptionOverflow) as info:
        sub.get()
    assert info.value.resume_seq == 3


def test_resubscribing_from_the_resume_point_catches_up_without_gaps() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 21)])
    registry = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    seen: list[int] = []
    sub = registry.subscribe_queue(maxsize=6, after_seq=0)
    for _ in range(50):
        try:
            batch = sub.get_many(100)
        except SubscriptionOverflow as overflow:
            sub = registry.subscribe_queue(maxsize=6, after_seq=overflow.resume_seq)
            continue
        if not batch and not sub.overflowed:
            break
        seen.extend(e.seq for e in batch)
    assert seen == list(range(1, 21))


def test_closing_a_queue_subscription_unregisters_it() -> None:
    registry = SubscriptionRegistry()
    sub = registry.subscribe_queue()
    assert len(registry) == 1
    sub.close()
    assert len(registry) == 0
    registry.dispatch([make_event(1)])
    assert sub.get() is None


def test_queue_arguments_are_checked() -> None:
    with pytest.raises(ValueError):
        SubscriptionRegistry().subscribe_queue(maxsize=0)


def test_a_queue_subscription_knows_its_resume_point_before_any_event_arrives() -> None:
    registry = SubscriptionRegistry()
    assert registry.subscribe_queue(after_seq=7).last_seq == 7
    registry.dispatch([make_event(9)])
    assert registry.subscribe_queue().last_seq == 9  # live: from the high-water mark
    ledger = FakeLedger([make_event(1), make_event(2), make_event(3)])
    with_ledger = SubscriptionRegistry(ledger)  # type: ignore[arg-type]
    assert with_ledger.subscribe_queue().last_seq == 3  # live: from the ledger head
    # a filter that rejects everything still leaves the resume point at the subscribe point
    idle = with_ledger.subscribe_queue(SubscriptionFilter.of(event_types=["Nope.*"]), after_seq=1)
    assert idle.last_seq == 1
    with_ledger.dispatch([make_event(4)])
    assert idle.last_seq == 1
    assert idle.get() is None
