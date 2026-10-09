"""The webhook worker: dispatcher and delivery engine on a loop, deliveries in parallel threads.

One cycle dispatches new outbox rows into deliveries, claims the head of each subject's queue and
sends them concurrently (the engine guarantees that two events of one subject are never in flight
together). ``start`` runs cycles on a daemon thread until ``stop``; ``drain`` runs cycles in the
caller's thread until nothing is left to do now (used by ``tl webhook run --once`` and the demo).
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher

log = logging.getLogger(__name__)


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
        if threads < 1:
            raise ValueError("threads must be at least 1")
        if claim_limit < 1:
            raise ValueError("claim_limit must be at least 1")
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self._dispatcher = dispatcher
        self._engine = engine
        self._threads = threads
        self._claim_limit = claim_limit
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> Exception | None:
        """The exception that ended the latest failed cycle, cleared by the next good one."""
        return self._error

    def run_cycle(self) -> CycleResult:
        """Dispatch, claim up to ``claim_limit`` heads, deliver them on the thread pool."""
        created = self._dispatcher.run_until_idle().created
        claims = self._engine.claim(self._claim_limit)
        result = CycleResult(dispatched=created, claimed=len(claims))
        if claims:
            # The claims of one cycle are heads of different subjects, so sending them together
            # never reorders a subject.
            with ThreadPoolExecutor(
                max_workers=min(self._threads, len(claims)), thread_name_prefix="tl-webhook"
            ) as pool:
                for settled in pool.map(self._engine.deliver, claims):
                    if settled.state == "delivered":
                        result.delivered += 1
                    elif settled.state == "retry":
                        result.retried += 1
                    elif settled.state == "dead":
                        result.dead += 1
                    if settled.disabled_subscription:
                        result.disabled += 1
        return result

    def drain(self, *, max_cycles: int = 1000) -> CycleResult:
        """Run cycles until one is idle (or ``max_cycles``); return the summed result."""
        total = CycleResult()
        for _ in range(max_cycles):
            cycle = self.run_cycle()
            total.dispatched += cycle.dispatched
            total.claimed += cycle.claimed
            total.delivered += cycle.delivered
            total.retried += cycle.retried
            total.dead += cycle.dead
            total.disabled += cycle.disabled
            if cycle.idle:
                break
        return total

    def start(self) -> None:
        """Run cycles on a daemon thread. ``RuntimeError`` if already running."""
        if self.running:
            raise RuntimeError("the worker is already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tl-webhook-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the loop to end, wait for it and for deliveries in flight. Harmless twice."""
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        thread.join(timeout)
        if not thread.is_alive():
            self._thread = None

    def __enter__(self) -> WebhookWorker:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop.is_set():
            idle = True
            try:
                idle = self.run_cycle().idle
                self._error = None
            except Exception as exc:
                self._error = exc
                log.warning("webhook cycle failed: %s", exc)
            if idle:
                self._stop.wait(self._interval)
