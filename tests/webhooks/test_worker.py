"""WebhookWorker: parallel across subjects, serial within one, survives errors (P0-I5-T24)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher, DispatchStats
from tl_core.webhooks.testing import SentRequest
from tl_core.webhooks.transport import TransportResult
from tl_core.webhooks.worker import CycleResult, WebhookWorker
from world import World

RECORDS = {"event_types": ["Record.*"]}


def worker(
    world: World, *, threads: int = 4, claim_limit: int = 16, interval_s: float = 0.02
) -> WebhookWorker:
    return WebhookWorker(
        world.dispatcher(),
        world.engine(),
        threads=threads,
        claim_limit=claim_limit,
        interval_s=interval_s,
    )


def statuses(world: World) -> list[str]:
    return [r["status"] for r in world.query("SELECT status FROM wh_delivery ORDER BY seq")]


def wait_until(check: Any, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


def test_an_empty_cycle_is_idle_and_cycle_results_say_so() -> None:
    assert CycleResult().idle
    assert not CycleResult(dispatched=1).idle
    assert not CycleResult(claimed=1).idle


def test_bad_arguments_are_refused(world: World) -> None:
    for bad in ({"threads": 0}, {"claim_limit": 0}, {"interval_s": 0}):
        with pytest.raises(ValueError):
            WebhookWorker(world.dispatcher(), world.engine(), **bad)


def test_drain_dispatches_delivers_and_sums_the_cycles(world: World) -> None:
    world.subscribe(filter=RECORDS)
    for n in range(3):
        world.record(f"P1-{n}")
    result = worker(world).drain()
    assert (result.dispatched, result.claimed, result.delivered) == (3, 3, 3)
    assert (result.retried, result.dead, result.disabled) == (0, 0, 0)
    assert statuses(world) == ["delivered"] * 3
    assert worker(world).drain().idle  # nothing left: a second drain does nothing


def test_drain_counts_retries_and_stops_when_everything_is_backing_off(world: World) -> None:
    world.subscribe(filter=RECORDS)
    world.record("P1-1")
    world.transport.default = 500
    result = worker(world).drain()
    assert (result.claimed, result.delivered, result.retried) == (1, 0, 1)
    assert statuses(world) == ["pending"]


def test_drain_respects_max_cycles(world: World) -> None:
    world.subscribe(filter=RECORDS)
    rid = world.record("P1-1")
    for version in range(1, 4):
        world.retitle(rid, f"t{version}", version=version)
    result = worker(world).drain(max_cycles=2)
    assert result.delivered == 2  # one event of the subject per cycle: ordering
    assert statuses(world).count("pending") == 2


def test_claim_limit_caps_one_cycle(world: World) -> None:
    world.subscribe(filter=RECORDS)
    for n in range(5):
        world.record(f"P1-{n}")
    cycle = worker(world, claim_limit=2).run_cycle()
    assert (cycle.claimed, cycle.delivered) == (2, 2)


def test_different_subjects_are_sent_at_the_same_time(world: World) -> None:
    world.subscribe(filter=RECORDS)
    for n in range(3):
        world.record(f"P1-{n}")
    barrier = threading.Barrier(3, timeout=10)

    def responder(request: SentRequest) -> TransportResult:
        barrier.wait()  # only passes when three requests are in flight together
        return TransportResult(status=200, latency_ms=1)

    world.transport.responder = responder
    cycle = worker(world, threads=3).run_cycle()
    assert (cycle.claimed, cycle.delivered) == (3, 3)


def test_events_of_one_subject_are_never_in_flight_together_and_arrive_in_order(
    world: World,
) -> None:
    world.subscribe(filter=RECORDS)
    rid = world.record("P1-1")
    for version in range(1, 4):
        world.retitle(rid, f"t{version}", version=version)
    other = world.record("P1-2")
    world.retitle(other, "x", version=1)
    lock = threading.Lock()
    inflight: dict[str, int] = {}
    worst = 0
    order: list[tuple[str, int]] = []

    def responder(request: SentRequest) -> TransportResult:
        nonlocal worst
        import json

        body = json.loads(request.body)
        subject = body["subject"]
        with lock:
            inflight[subject] = inflight.get(subject, 0) + 1
            worst = max(worst, inflight[subject])
            order.append((subject, body["tlseq"]))
        time.sleep(0.03)
        with lock:
            inflight[subject] -= 1
        return TransportResult(status=200, latency_ms=1)

    world.transport.responder = responder
    result = worker(world, threads=4).drain()
    assert result.delivered == 6 and worst == 1
    for subject in {s for s, _ in order}:
        seqs = [q for s, q in order if s == subject]
        assert seqs == sorted(seqs)


def test_the_loop_delivers_in_the_background_and_stops_cleanly(world: World) -> None:
    world.subscribe(filter=RECORDS)
    loop = worker(world)
    assert not loop.running
    with loop:
        assert loop.running
        with pytest.raises(RuntimeError):
            loop.start()
        world.record("P1-1")
        assert wait_until(lambda: statuses(world) == ["delivered"])
    assert not loop.running
    loop.stop()  # harmless twice
    loop.start()  # and it can be started again
    world.record("P1-2")
    assert wait_until(lambda: statuses(world) == ["delivered", "delivered"])
    loop.stop()
    assert not loop.running


class FlakyDispatcher(Dispatcher):
    def __init__(self, inner: Dispatcher) -> None:
        self._inner = inner
        self.failures = 2

    def run_until_idle(self, *, limit: int = 500) -> DispatchStats:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("database is locked")
        return self._inner.run_until_idle(limit=limit)


def test_an_error_in_a_cycle_is_recorded_and_the_loop_carries_on(world: World) -> None:
    world.subscribe(filter=RECORDS)
    world.record("P1-1")
    flaky = FlakyDispatcher(world.dispatcher())
    engine: DeliveryEngine = world.engine()
    loop = WebhookWorker(flaky, engine, interval_s=0.02)
    loop.start()
    try:
        assert wait_until(lambda: statuses(world) == ["delivered"])
        assert wait_until(lambda: loop.last_error is None)  # cleared by the first good cycle
        assert flaky.failures == 0
    finally:
        loop.stop()
