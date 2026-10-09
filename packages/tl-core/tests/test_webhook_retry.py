"""Retry policy: backoff, deadline, permanent failures, auto-disable thresholds."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from tl_core.webhooks.retry import DEFAULT_MAX_HOURS, HealthPolicy, RetryPolicy

T0 = datetime(2026, 10, 9, 3, 0, 0, tzinfo=UTC)


def policy(**kw: float) -> RetryPolicy:
    return RetryPolicy(**kw)


def test_backoff_doubles_and_is_capped() -> None:
    p = policy(base_s=5, factor=2, max_delay_s=100, jitter=0)
    rng = random.Random(1)
    assert [p.backoff_s(n, rng) for n in range(1, 8)] == [5, 10, 20, 40, 80, 100, 100]


def test_jitter_stays_between_half_and_full_of_the_ceiling() -> None:
    p = policy(base_s=10, jitter=0.5)
    rng = random.Random(7)
    delays = [p.backoff_s(3, rng) for _ in range(500)]
    assert all(20 <= d <= 40 for d in delays)
    assert max(delays) - min(delays) > 10


def test_retry_after_raises_the_delay_but_never_above_the_cap() -> None:
    p = policy(base_s=1, jitter=0, max_delay_s=60)
    rng = random.Random(1)
    assert p.backoff_s(1, rng, retry_after_s=30) == 30
    assert p.backoff_s(1, rng, retry_after_s=9999) == 60


def test_default_horizon_is_the_documented_24_hours() -> None:
    assert DEFAULT_MAX_HOURS == 24
    assert RetryPolicy().max_hours == 24
    assert RetryPolicy.from_settings({"webhooks.retry.max_hours": 2}).max_hours == 2


def test_attempts_continue_until_the_deadline_then_dead_letter() -> None:
    p = policy(max_hours=1, base_s=600, factor=2, max_delay_s=1800, jitter=0)
    rng = random.Random(1)
    now = T0
    kinds: list[str] = []
    for attempt in range(1, 10):
        decision = p.decide(attempt=attempt, now=now, created_at=T0, rng=rng, status=500)
        kinds.append(decision.kind)
        if decision.kind == "dead":
            assert decision.reason == "retries_exhausted"
            break
        now += timedelta(seconds=decision.delay_s)
    assert kinds[-1] == "dead"
    assert kinds[:-1] and set(kinds[:-1]) == {"retry"}
    assert now <= T0 + timedelta(hours=1)


def test_gone_and_blocked_targets_are_permanent() -> None:
    p = policy()
    rng = random.Random(1)
    assert p.decide(attempt=1, now=T0, created_at=T0, rng=rng, status=410).reason == "gone"
    blocked = p.decide(attempt=1, now=T0, created_at=T0, rng=rng, permanent="egress_denied")
    assert (blocked.kind, blocked.reason) == ("dead", "egress_denied")


def test_other_client_errors_are_retried() -> None:
    p = policy()
    for status in (400, 404, 429, 500, 503, None):
        decision = p.decide(attempt=1, now=T0, created_at=T0, rng=random.Random(1), status=status)
        assert decision.kind == "retry", status


@pytest.mark.parametrize(
    "kw", [{"max_hours": 0}, {"base_s": 0}, {"factor": 0.5}, {"jitter": 2}, {"max_delay_s": -1}]
)
def test_bad_policies_are_refused(kw: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kw)


def test_health_policy_disables_on_dead_letters_or_a_long_failing_period() -> None:
    h = HealthPolicy(max_consecutive_dead=3, max_failing_hours=10)
    assert h.should_disable(consecutive_dead=2, failing_since=None, now=T0) is None
    assert "3 deliveries" in (
        h.should_disable(consecutive_dead=3, failing_since=None, now=T0) or ""
    )
    since = T0 - timedelta(hours=9)
    assert h.should_disable(consecutive_dead=0, failing_since=since, now=T0) is None
    since = T0 - timedelta(hours=10)
    assert "10 hours" in (h.should_disable(consecutive_dead=0, failing_since=since, now=T0) or "")
