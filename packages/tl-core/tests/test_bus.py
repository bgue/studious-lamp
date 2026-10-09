"""Tests for the in-process bus (P0-I1-T07)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tl_core.bus import InProcessBus
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
