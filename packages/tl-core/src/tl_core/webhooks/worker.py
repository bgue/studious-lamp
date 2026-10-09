"""The webhook worker: dispatcher and delivery engine on a loop, deliveries in parallel threads.

One cycle dispatches new outbox rows into deliveries, claims the head of each subject's queue and
sends them concurrently (the engine guarantees that two events of one subject are never in flight
together). ``start`` runs cycles on a daemon thread until ``stop``; ``drain`` runs cycles in the
caller's thread until nothing is left to do now (used by ``tl webhook run --once`` and the demo).

STUB (P0-I5-T24): the method bodies raise ``NotImplementedError``. The specification is the ticket
and the provided test.
"""

from __future__ import annotations

from dataclasses import dataclass

from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher


@dataclass
class CycleResult:
    """What one cycle did. Counts are for this cycle only; :meth:`WebhookWorker.drain` sums them."""

    dispatched: int = 0  # deliveries created from outbox rows
    claimed: int = 0
    delivered: int = 0
    retried: int = 0
    dead: int = 0
    disabled: int = 0  # subscriptions auto-disabled

    @property
    def idle(self) -> bool:
        """True when the cycle created no delivery and claimed none."""
        return self.dispatched == 0 and self.claimed == 0


class WebhookWorker:
    def __init__(
        self,
        dispatcher: Dispatcher,
        engine: DeliveryEngine,
        *,
        threads: int = 4,
        claim_limit: int = 16,
        interval_s: float = 0.5,
    ) -> None:
        raise NotImplementedError

    @property
    def running(self) -> bool:
        raise NotImplementedError

    @property
    def last_error(self) -> Exception | None:
        """The exception that ended the latest failed cycle, cleared by the next good one."""
        raise NotImplementedError

    def run_cycle(self) -> CycleResult:
        """Dispatch, claim up to ``claim_limit`` heads, deliver them on the thread pool."""
        raise NotImplementedError

    def drain(self, *, max_cycles: int = 1000) -> CycleResult:
        """Run cycles until one is idle (or ``max_cycles``); return the summed result."""
        raise NotImplementedError

    def start(self) -> None:
        """Run cycles on a daemon thread. ``RuntimeError`` if already running."""
        raise NotImplementedError

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the loop to end, wait for it and for deliveries in flight. Harmless twice."""
        raise NotImplementedError

    def __enter__(self) -> WebhookWorker:
        raise NotImplementedError

    def __exit__(self, *exc: object) -> None:
        raise NotImplementedError

