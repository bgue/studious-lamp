"""Retry policy and the delivery state machine (brief 18.4: retries, DLQ, auto-disable).

A delivery is ``pending`` until it is ``delivered`` or ``dead``. After a failed attempt
:meth:`RetryPolicy.decide` returns either ``retry`` with a delay or ``dead`` with a reason:

* The delay is ``base_s * factor ** (attempt - 1)``, capped at ``max_delay_s``, then multiplied by a
  random factor in ``[1 - jitter, 1]`` ("equal jitter" keeps a floor so a retry storm cannot
  collapse
  to zero). A receiver's ``Retry-After`` raises the delay (never above the cap).
* The deadline is ``created_at + max_hours`` (``webhooks.retry.max_hours``, brief 30.5, default 24).
  A retry that would fall after the deadline is dead-lettered instead, so the last attempt happens
  at most one cap before the deadline.
* ``410 Gone`` and a blocked target (SSRF policy) are permanent: dead at once.

Until about:config exists (P0-I8) the numbers are constants; :meth:`RetryPolicy.from_settings` is
the
plug point that reads the setting keys.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

SETTING_MAX_HOURS = "webhooks.retry.max_hours"
DEFAULT_MAX_HOURS = 24.0

DeadReason = Literal["retries_exhausted", "gone", "egress_denied", "subscription_removed"]


@dataclass(frozen=True)
class Decision:
    """What to do after a failed attempt."""

    kind: Literal["retry", "dead"]
    delay_s: float = 0.0
    reason: DeadReason | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_hours: float = DEFAULT_MAX_HOURS
    base_s: float = 5.0
    factor: float = 2.0
    max_delay_s: float = 3600.0
    jitter: float = 0.5

    def __post_init__(self) -> None:
        if self.max_hours <= 0 or self.base_s <= 0 or self.max_delay_s <= 0:
            raise ValueError("max_hours, base_s and max_delay_s must be positive")
        if self.factor < 1:
            raise ValueError("factor must be at least 1")
        if not 0 <= self.jitter <= 1:
            raise ValueError("jitter must be between 0 and 1")

    @staticmethod
    def from_settings(settings: Mapping[str, Any]) -> RetryPolicy:
        """Read ``webhooks.retry.max_hours`` from a settings mapping; other numbers stay default."""
        return RetryPolicy(max_hours=float(settings.get(SETTING_MAX_HOURS, DEFAULT_MAX_HOURS)))

    def deadline(self, created_at: datetime) -> datetime:
        return created_at + timedelta(hours=self.max_hours)

    def backoff_s(
        self, attempt: int, rng: random.Random, retry_after_s: float | None = None
    ) -> float:
        """Seconds to wait after attempt number ``attempt`` (1 for the first) has failed."""
        if attempt < 1:
            raise ValueError("attempt starts at 1")
        ceiling = min(self.max_delay_s, self.base_s * self.factor ** (attempt - 1))
        delay = ceiling * (1 - self.jitter * rng.random())
        if retry_after_s is not None and retry_after_s > 0:
            delay = max(delay, min(retry_after_s, self.max_delay_s))
        return delay

    def decide(
        self,
        *,
        attempt: int,
        now: datetime,
        created_at: datetime,
        rng: random.Random,
        status: int | None = None,
        permanent: DeadReason | None = None,
        retry_after_s: float | None = None,
    ) -> Decision:
        """The outcome of a failed attempt (``status`` is the HTTP status, if one was received)."""
        if permanent is not None:
            return Decision("dead", reason=permanent)
        if status == 410:
            return Decision("dead", reason="gone")
        delay = self.backoff_s(attempt, rng, retry_after_s)
        if now + timedelta(seconds=delay) > self.deadline(created_at):
            return Decision("dead", reason="retries_exhausted")
        return Decision("retry", delay_s=delay)


@dataclass(frozen=True)
class HealthPolicy:
    """When a subscription is auto-disabled (brief 18.4: "sustained failure").

    Either ``max_consecutive_dead`` deliveries dead-lettered with no success in between, or no
    success
    for ``max_failing_hours`` while failing. The owner is notified through the ``Disabled`` event
    (feed and notification delivery arrive with their increments).
    """

    max_consecutive_dead: int = 5
    max_failing_hours: float = 72.0

    def should_disable(
        self, *, consecutive_dead: int, failing_since: datetime | None, now: datetime
    ) -> str | None:
        """A human-readable detail when the subscription should be disabled, else ``None``."""
        if consecutive_dead >= self.max_consecutive_dead:
            return f"{consecutive_dead} deliveries dead-lettered since the last success"
        if failing_since is not None and now - failing_since >= timedelta(
            hours=self.max_failing_hours
        ):
            return f"failing without a success for {self.max_failing_hours:g} hours"
        return None
