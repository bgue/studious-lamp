"""The delivery engine follows webhooks.egress.allowlist and webhooks.retry.max_hours (P0-I8-T06).

Provided; do not edit.
"""

from __future__ import annotations

import pytest
from tl_core import settings
from tl_core.settings.reader import SettingsReader, conn_factory_from
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.retry import RetryPolicy
from tl_core.webhooks.transport import TransportResult
from tl_core.webhooks.wiring import (
    ALLOWLIST_ENV,
    egress_from_settings,
    make_engine,
    retry_from_settings,
    settings_reader,
)
from world import World

RECORDS = {"event_types": ["Record.*"]}


def private(host: str, port: int) -> list[str]:
    return ["10.0.0.7"]


def put(world: World, key: str, value: object, **kw: object) -> None:
    with world.factory() as uow:
        settings.set_setting(
            uow,
            key=key,
            layer="company",
            value=value,
            actor="user:alice",
            source="test",
            **kw,  # type: ignore[arg-type]
        )


def live_reader(world: World) -> SettingsReader:
    """A reader that reads the tables on every question (so a test needs no waiting)."""
    return SettingsReader(conn_factory_from(world.factory), max_age_s=0)


def test_the_default_policies_are_the_platform_defaults(world: World) -> None:
    reader = live_reader(world)
    assert egress_from_settings(reader)() == EgressPolicy(())
    assert retry_from_settings(reader)() == RetryPolicy()
    assert retry_from_settings(reader)().max_hours == 24.0


def test_the_allow_list_is_the_setting_after_the_operators_entries_without_repeats(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, "env.test, shared.test")
    put(
        world,
        "webhooks.egress.allowlist",
        ["shared.test", "hub.test"],
        reason="r",
        accept_risk=True,
    )
    policy = egress_from_settings(live_reader(world), ["flag.test"])()
    assert policy.allowlist == ("flag.test", "env.test", "shared.test", "hub.test")


def test_a_resolver_given_to_the_provider_reaches_the_policy(world: World) -> None:
    policy = egress_from_settings(live_reader(world), resolver=private)()
    assert policy.resolver is private


def test_the_retry_window_is_the_setting(world: World) -> None:
    reader = live_reader(world)
    put(world, "webhooks.retry.max_hours", 48, reason="partner outage")
    assert retry_from_settings(reader)() == RetryPolicy(max_hours=48.0)
    put(world, "webhooks.retry.max_hours", 0.5, reason="shorter")
    assert retry_from_settings(reader)().max_hours == 0.5


def test_a_changed_allow_list_reaches_a_running_engine(world: World) -> None:
    world.subscribe(filter=RECORDS, url="https://internal.test/")
    engine = make_engine(
        world.factory, transport=world.transport, reader=live_reader(world), resolver=private
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    first = engine.deliver(engine.claim()[0])
    assert (first.state, first.dead_reason) == ("dead", "egress_denied")
    put(world, "webhooks.egress.allowlist", ["internal.test"], reason="r", accept_risk=True)
    world.record("P1-2")
    world.dispatcher().run_until_idle()
    assert engine.deliver(engine.claim()[0]).state == "delivered"
    assert len(world.transport.sent) == 1


def test_an_allow_host_flag_still_works_beside_the_setting(world: World) -> None:
    world.subscribe(filter=RECORDS, url="https://internal.test/")
    engine = make_engine(
        world.factory,
        allow_hosts=["internal.test"],
        transport=world.transport,
        reader=live_reader(world),
        resolver=private,
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    assert engine.deliver(engine.claim()[0]).state == "delivered"


def test_a_changed_retry_window_reaches_a_running_engine(world: World) -> None:
    world.subscribe(filter=RECORDS)
    engine = make_engine(
        world.factory,
        transport=world.transport,
        reader=live_reader(world),
        resolver=world.resolver,
        clock=world.clock,
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [TransportResult(status=500, latency_ms=1)] * 3
    claim = engine.claim()[0]
    settled = engine.deliver(claim)
    assert (settled.state, settled.dead_reason) == ("retry", None)
    put(world, "webhooks.retry.max_hours", 0.1, reason="short window")  # six minutes
    world.clock.advance(minutes=7)
    later = engine.claim()
    assert later and engine.deliver(later[0]).state == "dead"


def test_an_explicit_retry_policy_wins_over_the_setting(world: World) -> None:
    world.subscribe(filter=RECORDS)
    put(world, "webhooks.retry.max_hours", 0.1, reason="short window")
    engine = make_engine(
        world.factory,
        transport=world.transport,
        retry=RetryPolicy(max_hours=100, base_s=10, jitter=0),
        reader=live_reader(world),
        resolver=world.resolver,
        clock=world.clock,
    )
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [TransportResult(status=500, latency_ms=1)]
    world.clock.advance(minutes=30)
    assert engine.deliver(engine.claim()[0]).state == "retry"


def test_the_default_reader_looks_again_within_seconds(world: World) -> None:
    reader = settings_reader(world.factory)
    assert reader.get("webhooks.retry.max_hours") == 24
    put(world, "webhooks.retry.max_hours", 48, reason="r")
    assert reader.get("webhooks.retry.max_hours") == 24  # still the young copy
