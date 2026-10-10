"""The engine asks for its egress and retry policy at every use, so a setting applies live."""

from __future__ import annotations

from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.retry import RetryPolicy
from tl_core.webhooks.transport import TransportResult
from world import World

RECORDS = {"event_types": ["Record.*"]}


def private(host: str, port: int) -> list[str]:
    return ["10.0.0.7"]


def test_a_changed_allow_list_applies_to_the_next_delivery(world: World) -> None:
    world.subscribe(filter=RECORDS, url="https://internal.test/")
    allowed: list[str] = []
    engine = DeliveryEngine(
        world.factory,
        world.transport,
        egress=lambda: EgressPolicy(tuple(allowed), private),
        clock=world.clock,
        worker_id="w",
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    first = engine.deliver(engine.claim()[0])
    assert (first.state, first.dead_reason) == ("dead", "egress_denied")
    allowed.append("internal.test")  # the setting changes while the engine runs
    world.record("P1-2")
    world.dispatcher().run_until_idle()
    second = engine.deliver(engine.claim()[0])
    assert second.state == "delivered" and len(world.transport.sent) == 1


def test_a_changed_retry_window_applies_to_the_next_failure(world: World) -> None:
    world.subscribe(filter=RECORDS)
    window = [24.0]
    engine = DeliveryEngine(
        world.factory,
        world.transport,
        retry=lambda: RetryPolicy(max_hours=window[0], base_s=10, jitter=0),
        egress=EgressPolicy((), world.resolver),
        clock=world.clock,
        worker_id="w",
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [TransportResult(status=500, latency_ms=1)] * 2
    first = engine.deliver(engine.claim()[0])
    assert first.state == "retry"
    window[0] = 0.001  # the setting shrinks the window: the next retry would fall after it
    world.clock.advance(seconds=11)
    second = engine.deliver(engine.claim()[0])
    assert (second.state, second.dead_reason) == ("dead", "retries_exhausted")
