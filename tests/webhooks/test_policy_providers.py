"""The engine asks for its egress and retry policy at every use, so a setting applies live."""

from __future__ import annotations

import pytest
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


# --- a provider that fails must not strand claims or duplicate a send (P0-I8 review) -------------


def broken() -> EgressPolicy:
    raise RuntimeError("settings are unreadable")


def test_a_failing_egress_provider_means_the_strict_default_not_a_crash(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.subscribe(filter=RECORDS, url="https://internal.test/")
    engine = DeliveryEngine(
        world.factory, world.transport, egress=broken, clock=world.clock, worker_id="w"
    )
    for key in ("P1-1", "P1-2", "P1-3"):
        world.record(key)
    world.dispatcher().run_until_idle()
    with caplog.at_level("ERROR"):
        stats = engine.run_cycle()
    assert stats.claimed >= 1 and stats.claimed == stats.dead + stats.retried + stats.delivered
    assert world.transport.sent == []  # nothing went out on a policy nobody could read
    assert "egress policy provider failed" in caplog.text


def test_a_failing_egress_provider_never_widens_what_was_allowed(world: World) -> None:
    world.subscribe(filter=RECORDS, url="https://internal.test/")
    allowed: list[str] = ["internal.test"]
    fail = [False]

    def provider() -> EgressPolicy:
        if fail[0]:
            raise RuntimeError("down")
        return EgressPolicy(tuple(allowed), private)

    engine = DeliveryEngine(
        world.factory, world.transport, egress=provider, clock=world.clock, worker_id="w"
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    assert engine.deliver(engine.claim()[0]).state == "delivered"
    fail[0] = True
    world.record("P1-2")
    world.dispatcher().run_until_idle()
    again = engine.deliver(engine.claim()[0])
    # the strict default has no allow-list (and no test resolver): nothing is sent
    assert again.state != "delivered" and len(world.transport.sent) == 1


def test_a_retry_provider_that_fails_after_the_send_does_not_roll_back_the_attempt(
    world: World,
) -> None:
    world.subscribe(filter=RECORDS)
    calls = [0]

    def provider() -> RetryPolicy:
        calls[0] += 1
        if calls[0] > 1:  # the first call is the attempt's; later calls would be inside settle
            raise RuntimeError("down")
        return RetryPolicy(base_s=10, jitter=0)

    engine = DeliveryEngine(
        world.factory,
        world.transport,
        retry=provider,
        egress=EgressPolicy((), world.resolver),
        clock=world.clock,
        worker_id="w",
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [TransportResult(status=500, latency_ms=1)]
    settled = engine.deliver(engine.claim()[0])
    assert settled.state == "retry" and len(world.transport.sent) == 1
    rows = world.query("SELECT attempts FROM wh_delivery")
    assert (
        rows[0]["attempts"] == 1
    )  # the attempt was recorded, so it will not be sent again at once


def test_settling_with_a_failing_retry_provider_uses_the_last_good_policy(world: World) -> None:
    from tl_core.webhooks.delivery import AttemptOutcome

    world.subscribe(filter=RECORDS)
    good = RetryPolicy(base_s=10, jitter=0)
    state = {"fail": False}

    def provider() -> RetryPolicy:
        if state["fail"]:
            raise RuntimeError("down")
        return good

    engine = DeliveryEngine(
        world.factory, world.transport, retry=provider, clock=world.clock, worker_id="w"
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    claim = engine.claim()[0]
    engine._retry()  # noqa: SLF001 - a first good read, as an earlier cycle would have made
    state["fail"] = True
    outcome = AttemptOutcome(world.clock(), TransportResult(status=500, latency_ms=1))
    settled = engine.settle(claim, outcome)  # outcome.retry is None: settle asks the provider
    assert settled.state == "retry" and settled.next_attempt_at is not None
