"""ChangePoller: a seq-cursor poller feeding a subscription registry (P0-I4-T02)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

import pytest
from tl_core.changefeed import ChangePoller, SubscriptionFilter, SubscriptionRegistry
from tl_core.ledger import Event

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WAIT = 5.0  # seconds a test waits for the background thread before failing


def make_event(seq: int, event_type: str = "Record.Created", scope: str = "project:P1") -> Event:
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
    """``read_after`` and ``head_seq`` are real; ``fail_next`` makes the next reads raise."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self.events: list[Event] = list(events or [])
        self.calls: list[tuple[int, str | None, int]] = []
        self.fail_next = 0

    def add(self, *events: Event) -> None:
        self.events.extend(events)

    def head_seq(self) -> int:
        return max((e.seq for e in self.events), default=0)

    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]:
        self.calls.append((seq, scope, limit))
        if self.fail_next:
            self.fail_next -= 1
            raise RuntimeError("database is locked")
        found = [e for e in self.events if e.seq > seq and (scope is None or e.scope == scope)]
        return found[:limit]

    def __getattr__(self, name: str) -> Any:  # pragma: no cover
        # the poller may only call read_after and head_seq
        raise AssertionError(f"ChangePoller must not call ledger.{name}")


class Collector:
    def __init__(self, registry: SubscriptionRegistry, flt: SubscriptionFilter | None = None):
        self.seqs: list[int] = []
        self.arrived = threading.Event()
        self.want = 0
        registry.subscribe(self.on_event, flt, after_seq=0)

    def on_event(self, event: Event) -> None:
        self.seqs.append(event.seq)
        if len(self.seqs) >= self.want:
            self.arrived.set()

    def wait_for(self, count: int) -> bool:
        self.want = count
        if len(self.seqs) >= count:
            return True
        self.arrived.clear()
        return self.arrived.wait(WAIT)


def test_poll_once_dispatches_new_events_and_moves_the_cursor() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 4)])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, after_seq=0)  # type: ignore[arg-type]
    assert poller.cursor == 0
    assert poller.poll_once() == 3
    assert got.seqs == [1, 2, 3]
    assert poller.cursor == 3
    assert poller.poll_once() == 0
    ledger.add(make_event(4))
    assert poller.poll_once() == 1
    assert got.seqs == [1, 2, 3, 4]
    assert poller.cursor == 4


def test_by_default_only_events_after_the_ledger_head_are_seen() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 4)])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry)  # type: ignore[arg-type]
    assert poller.cursor == 3
    assert poller.poll_once() == 0
    ledger.add(make_event(4))
    assert poller.poll_once() == 1
    assert got.seqs == [4]


def test_an_explicit_start_replays_from_there() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 6)])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    ChangePoller(ledger, registry, after_seq=2).poll_once()  # type: ignore[arg-type]
    assert got.seqs == [3, 4, 5]


def test_events_are_read_in_pages_until_a_short_page() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 26)])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, after_seq=0, page_size=10)  # type: ignore[arg-type]
    assert poller.poll_once() == 25
    assert got.seqs == list(range(1, 26))
    assert ledger.calls == [(0, None, 10), (10, None, 10), (20, None, 10)]


def test_a_final_full_page_costs_one_more_empty_read() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 21)])
    registry = SubscriptionRegistry()
    poller = ChangePoller(ledger, registry, after_seq=0, page_size=10)  # type: ignore[arg-type]
    assert poller.poll_once() == 20
    assert [call[0] for call in ledger.calls] == [0, 10, 20]


def test_the_scope_is_passed_to_the_ledger() -> None:
    ledger = FakeLedger([make_event(1, scope="company"), make_event(2, scope="project:P1")])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, after_seq=0, scope="company")  # type: ignore[arg-type]
    assert poller.poll_once() == 1
    assert got.seqs == [1]
    assert {call[1] for call in ledger.calls} == {"company"}


def test_subscriber_filters_apply_to_polled_events() -> None:
    ledger = FakeLedger([make_event(1, "Record.Created"), make_event(2, "Link.Added")])
    registry = SubscriptionRegistry()
    got = Collector(registry, SubscriptionFilter.of(event_types=["Link.*"]))
    ChangePoller(ledger, registry, after_seq=0).poll_once()  # type: ignore[arg-type]
    assert got.seqs == [2]


def test_a_failed_read_leaves_the_cursor_and_the_next_poll_repeats_nothing() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 4)])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, after_seq=0)  # type: ignore[arg-type]
    ledger.fail_next = 1
    with pytest.raises(RuntimeError):
        poller.poll_once()
    assert poller.cursor == 0
    assert got.seqs == []
    assert poller.poll_once() == 3
    assert got.seqs == [1, 2, 3]


def test_a_subscriber_that_raises_does_not_stop_the_poller() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 4)])
    registry = SubscriptionRegistry()

    def boom(event: Event) -> None:
        raise ValueError("bad subscriber")

    registry.subscribe(boom, after_seq=0)
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, after_seq=0)  # type: ignore[arg-type]
    assert poller.poll_once() == 3
    assert got.seqs == [1, 2, 3]
    assert poller.cursor == 3


def test_the_background_thread_delivers_new_events() -> None:
    ledger = FakeLedger()
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, interval_s=0.01)  # type: ignore[arg-type]
    assert poller.running is False
    poller.start()
    try:
        assert poller.running is True
        ledger.add(make_event(1))
        assert got.wait_for(1)
        ledger.add(make_event(2), make_event(3))
        assert got.wait_for(3)
        assert got.seqs == [1, 2, 3]
    finally:
        poller.stop()
    assert poller.running is False
    assert poller.cursor == 3


def test_setting_the_wake_event_ends_the_wait_early() -> None:
    ledger = FakeLedger()
    registry = SubscriptionRegistry()
    got = Collector(registry)
    wake = threading.Event()
    poller = ChangePoller(ledger, registry, interval_s=60, wake=wake)  # type: ignore[arg-type]
    with poller:
        assert got.wait_for(0)
        ledger.add(make_event(1))
        wake.set()  # without the wake-up the poller would sleep for a minute
        assert got.wait_for(1)
        ledger.add(make_event(2))
        wake.set()
        assert got.wait_for(2)
    assert got.seqs == [1, 2]
    assert poller.running is False


def test_a_wake_up_that_finds_nothing_is_harmless() -> None:
    ledger = FakeLedger()
    registry = SubscriptionRegistry()
    got = Collector(registry)
    wake = threading.Event()
    with ChangePoller(ledger, registry, interval_s=0.01, wake=wake):  # type: ignore[arg-type]
        for _ in range(5):
            wake.set()
        ledger.add(make_event(1))
        assert got.wait_for(1)
    assert got.seqs == [1]


def test_stop_returns_promptly_even_with_a_long_interval_and_a_wake_event() -> None:
    poller = ChangePoller(
        FakeLedger(),  # type: ignore[arg-type]
        SubscriptionRegistry(),
        interval_s=60,
        wake=threading.Event(),
    )
    poller.start()
    poller.stop(timeout=WAIT)
    assert poller.running is False


def test_a_failing_poll_is_recorded_and_retried() -> None:
    ledger = FakeLedger([make_event(1)])
    registry = SubscriptionRegistry()
    got = Collector(registry)
    ledger.fail_next = 3
    poller = ChangePoller(ledger, registry, after_seq=0, interval_s=0.01)  # type: ignore[arg-type]
    with poller:
        assert got.wait_for(1)
    assert got.seqs == [1]
    assert ledger.fail_next == 0
    assert poller.last_error is None  # cleared by the successful poll after the failures


def test_last_error_holds_the_most_recent_failure() -> None:
    ledger = FakeLedger()
    registry = SubscriptionRegistry()
    ledger.fail_next = 10_000
    poller = ChangePoller(ledger, registry, after_seq=0, interval_s=0.01)  # type: ignore[arg-type]
    poller.start()
    try:
        deadline = threading.Event()
        for _ in range(500):
            if poller.last_error is not None:
                break
            deadline.wait(0.01)
        assert isinstance(poller.last_error, RuntimeError)
        assert poller.running is True  # a failing read does not kill the thread
    finally:
        poller.stop()


def test_start_twice_is_refused_and_stop_twice_is_fine() -> None:
    poller = ChangePoller(FakeLedger(), SubscriptionRegistry(), interval_s=0.01)  # type: ignore[arg-type]
    poller.stop()  # never started: nothing happens
    poller.start()
    try:
        with pytest.raises(RuntimeError):
            poller.start()
    finally:
        poller.stop()
    poller.stop()
    assert poller.running is False


def test_a_stopped_poller_can_be_started_again() -> None:
    ledger = FakeLedger()
    registry = SubscriptionRegistry()
    got = Collector(registry)
    poller = ChangePoller(ledger, registry, interval_s=0.01)  # type: ignore[arg-type]
    poller.start()
    poller.stop()
    ledger.add(make_event(1))
    poller.start()
    try:
        assert got.wait_for(1)
    finally:
        poller.stop()


def test_the_context_manager_starts_and_stops_the_thread() -> None:
    poller = ChangePoller(FakeLedger(), SubscriptionRegistry(), interval_s=0.01)  # type: ignore[arg-type]
    with poller as same:
        assert same is poller
        assert poller.running is True
    assert poller.running is False


@pytest.mark.parametrize(
    "kwargs",
    [{"after_seq": -1}, {"interval_s": 0}, {"interval_s": -1.0}, {"page_size": 0}],
)
def test_bad_arguments_are_refused(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ChangePoller(FakeLedger(), SubscriptionRegistry(), **kwargs)  # type: ignore[arg-type]
