"""The subscription registry: one fan-out point for the in-process bus and the poller.

Both sources hand committed events to :meth:`SubscriptionRegistry.dispatch`; the registry applies
each subscriber's filter and delivers in ``seq`` order, once per subscription:

* **At-least-once with resume.** A subscription remembers the last ``seq`` it was given and
  ignores anything at or below it, so the bus and the poller may both offer the same event. A
  client that stored its last ``seq`` resumes with ``after_seq``; the registry replays what the
  ledger holds after it, then goes live without a gap (replay and registration happen under one
  lock, and ``dispatch`` takes the same lock).
* **Order.** Delivery is in ``seq`` order per subscription; ``dispatch`` sorts each batch and the
  bus (through ``OrderedPublisher``) and the poller both hand over ascending batches.
* **A slow or failing subscriber never blocks writers for long.** Callbacks run on the
  dispatching thread, inside the registry lock (an ``RLock``, so a callback may subscribe or
  close). Never block in a callback. A callback that raises is logged and skipped. For a
  consumer on another thread (SSE, a worker) use :meth:`subscribe_queue`: it enqueues without
  blocking and, if the consumer falls behind by ``maxsize`` events, ends with
  :class:`SubscriptionOverflow` carrying the ``seq`` to resume from.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from tl_core.changefeed.filters import ANY, SubscriptionFilter
from tl_core.ledger import Event, Ledger

if TYPE_CHECKING:
    from tl_core.bus import Bus, Subscription

log = logging.getLogger(__name__)

Callback = Callable[[Event], None]
REPLAY_PAGE = 500


class SubscriptionOverflow(Exception):
    """A queue subscription fell behind. Resubscribe with ``after_seq=resume_seq``."""

    def __init__(self, resume_seq: int) -> None:
        super().__init__(f"subscription overflowed; resume after seq {resume_seq}")
        self.resume_seq = resume_seq


class RegistrySubscription:
    """One subscriber's filter and cursor. ``close()`` stops delivery."""

    def __init__(
        self,
        registry: SubscriptionRegistry,
        callback: Callback,
        flt: SubscriptionFilter,
        last_seq: int,
    ) -> None:
        self._registry = registry
        self.callback = callback
        self.filter = flt
        self.last_seq = last_seq
        self.closed = False

    def close(self) -> None:
        self._registry.remove(self)


class QueueSubscription:
    """A subscription whose events wait in a bounded queue for a consumer on another thread."""

    def __init__(self, maxsize: int) -> None:
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._overflowed = False
        self._resume_seq = -1
        self._inner: RegistrySubscription | None = None

    # --- producer side (called by the registry, never blocks) ---------------------------------

    def bind(self, inner: RegistrySubscription) -> None:
        """Tie this handle to its registry subscription (done by ``subscribe_queue``)."""
        self._inner = inner

    def offer(self, event: Event) -> None:
        """Enqueue without blocking; on a full queue, mark the overflow and close the feed."""
        with self._lock:
            if self._overflowed:
                return
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self._overflowed = True
                if self._inner is not None:
                    self._inner.closed = True
                return
            self._resume_seq = event.seq

    # --- consumer side ------------------------------------------------------------------------

    def get(self, timeout: float = 0.0) -> Event | None:
        """The next event; ``None`` if none arrives within ``timeout`` seconds (0: do not wait).

        Raises :class:`SubscriptionOverflow` when the queue overflowed and has been drained: the
        consumer then calls ``registry.subscribe_queue(..., after_seq=error.resume_seq)``.
        """
        try:
            return self._queue.get(timeout=timeout) if timeout > 0 else self._queue.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._overflowed:
                    raise SubscriptionOverflow(self._resume_seq) from None
            return None

    def get_many(self, limit: int = 100, timeout: float = 0.0) -> list[Event]:
        """Up to ``limit`` events: waits ``timeout`` for the first, then takes what is queued."""
        first = self.get(timeout)
        if first is None:
            return []
        events = [first]
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    @property
    def overflowed(self) -> bool:
        return self._overflowed

    @property
    def last_seq(self) -> int:
        """Highest ``seq`` placed in the queue (the resume point if the consumer stops now)."""
        return self._resume_seq

    def close(self) -> None:
        if self._inner is not None:
            self._inner.close()


class SubscriptionRegistry:
    """Fan-out of committed events to filtered subscribers. See the module docstring."""

    def __init__(self, ledger: Ledger | None = None) -> None:
        self._ledger = ledger
        self._lock = threading.RLock()
        self._subs: list[RegistrySubscription] = []
        self._high = -1  # highest seq ever dispatched

    def __len__(self) -> int:
        with self._lock:
            return len(self._subs)

    @property
    def high_water(self) -> int:
        """Highest ``seq`` dispatched so far (-1 when none)."""
        return self._high

    # --- subscribing --------------------------------------------------------------------------

    def subscribe(
        self,
        callback: Callback,
        flt: SubscriptionFilter | None = None,
        *,
        after_seq: int | None = None,
    ) -> RegistrySubscription:
        """Deliver matching events to ``callback``.

        ``after_seq=None`` is live only: events committed from now on. ``after_seq=n`` replays
        the ledger after ``n`` (when the registry has a ledger) and then continues live, with no
        gap and no duplicate.
        """
        chosen = flt if flt is not None else ANY
        return self._open(
            lambda start: RegistrySubscription(self, callback, chosen, start), after_seq
        )

    def subscribe_queue(
        self,
        flt: SubscriptionFilter | None = None,
        *,
        after_seq: int | None = None,
        maxsize: int = 1000,
    ) -> QueueSubscription:
        """Like :meth:`subscribe`, for a consumer that reads from another thread."""
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        chosen = flt if flt is not None else ANY
        handle = QueueSubscription(maxsize)

        def make(start: int) -> RegistrySubscription:
            inner = RegistrySubscription(self, handle.offer, chosen, start)
            handle.bind(inner)
            return inner

        self._open(make, after_seq)
        return handle

    def _open(
        self, make: Callable[[int], RegistrySubscription], after_seq: int | None
    ) -> RegistrySubscription:
        with self._lock:
            sub = make(after_seq if after_seq is not None else self._live_start())
            if after_seq is not None and self._ledger is not None:
                self._replay(sub)
            if not sub.closed:
                self._subs.append(sub)
            return sub

    def attach(self, bus: Bus) -> Subscription:
        """Feed this registry from an in-process bus. Close the result to detach."""
        return bus.subscribe(lambda event: self.dispatch([event]))

    def _live_start(self) -> int:
        head = self._ledger.head_seq() if self._ledger is not None else -1
        return max(head, self._high)

    def _replay(self, sub: RegistrySubscription) -> None:
        assert self._ledger is not None
        cursor = sub.last_seq
        while not sub.closed:
            page = self._ledger.read_after(cursor, scope=sub.filter.scope, limit=REPLAY_PAGE)
            if not page:
                break
            for event in page:
                self._deliver(sub, event)
            cursor = page[-1].seq
            sub.last_seq = max(sub.last_seq, cursor)

    # --- dispatching --------------------------------------------------------------------------

    def dispatch(self, events: Sequence[Event]) -> None:
        """Offer committed events to every subscriber. Safe to call from several threads."""
        if not events:
            return
        batch = sorted(events, key=lambda event: event.seq)
        with self._lock:
            for event in batch:
                self._high = max(self._high, event.seq)
                for sub in list(self._subs):
                    if not sub.closed:
                        self._deliver(sub, event)
            self._subs = [sub for sub in self._subs if not sub.closed]

    @staticmethod
    def _deliver(sub: RegistrySubscription, event: Event) -> None:
        if event.seq <= sub.last_seq:
            log.debug("registry skipped seq %s: subscriber is at seq %s", event.seq, sub.last_seq)
            return
        sub.last_seq = event.seq
        if not sub.filter.matches(event):
            return
        try:
            sub.callback(event)
        except Exception:
            log.exception("change-feed subscriber failed for seq %s", event.seq)

    def remove(self, sub: RegistrySubscription) -> None:
        with self._lock:
            sub.closed = True
            if sub in self._subs:
                self._subs.remove(sub)

    def close(self) -> None:
        """Drop every subscription."""
        with self._lock:
            for sub in self._subs:
                sub.closed = True
            self._subs = []
