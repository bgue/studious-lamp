"""The change-feed bus: Protocol and the in-process implementation (brief 5.3, dev column)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from typing import Protocol

from tl_core.ledger import Event, Ledger

log = logging.getLogger(__name__)

Callback = Callable[[Event], None]


class Subscription(Protocol):
    def close(self) -> None: ...


class Bus(Protocol):
    def publish(self, events: Sequence[Event]) -> None: ...

    def subscribe(
        self,
        callback: Callback,
        *,
        after_seq: int | None = None,
        scope: str | None = None,
        event_types: Sequence[str] | None = None,
    ) -> Subscription: ...


class _Subscription:
    def __init__(
        self,
        bus: InProcessBus,
        callback: Callback,
        scope: str | None,
        event_types: frozenset[str] | None,
        last_seq: int,
    ) -> None:
        self._bus = bus
        self.callback = callback
        self.scope = scope
        self.event_types = event_types
        self.last_seq = last_seq

    def matches(self, event: Event) -> bool:
        return (self.scope is None or event.scope == self.scope) and (
            self.event_types is None or event.event_type in self.event_types
        )

    def close(self) -> None:
        self._bus.remove(self)


class InProcessBus:
    """Synchronous, in-process delivery with a per-subscriber ``seq`` cursor.

    A subscription never sees a ``seq`` that is not greater than the last one delivered to it, so
    delivery is ordered and never repeats. ``publish`` sorts each batch by ``seq`` and delivers it
    while holding the bus lock, so concurrent publishers are serialised. An event that is skipped
    because its ``seq`` is at or below the cursor (a duplicate of a replayed event, or one that
    arrived after a later event) is logged as a warning, never dropped silently. Publishers must
    publish in commit order; the SQLite unit of work guarantees that by committing and publishing
    under one lock. A callback that raises is logged and skipped; it cannot affect the publisher or
    other subscribers. When the bus is given a ledger, ``subscribe(after_seq=n)`` first replays
    committed events after ``n``.
    """

    def __init__(self, ledger: Ledger | None = None) -> None:
        self._ledger = ledger
        self._lock = threading.RLock()
        self._subs: list[_Subscription] = []

    def subscribe(
        self,
        callback: Callback,
        *,
        after_seq: int | None = None,
        scope: str | None = None,
        event_types: Sequence[str] | None = None,
    ) -> Subscription:
        types = frozenset(event_types) if event_types is not None else None
        sub = _Subscription(
            self, callback, scope, types, after_seq if after_seq is not None else -1
        )
        with self._lock:
            if after_seq is not None and self._ledger is not None:
                cursor = after_seq
                while True:
                    page = self._ledger.read_after(cursor, scope=scope, limit=500)
                    if not page:
                        break
                    for event in page:
                        self._deliver(sub, event)
                    cursor = page[-1].seq
            self._subs.append(sub)
        return sub

    def publish(self, events: Sequence[Event]) -> None:
        batch = sorted(events, key=lambda event: event.seq)
        with self._lock:
            for event in batch:
                for sub in list(self._subs):
                    self._deliver(sub, event)

    def remove(self, sub: _Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    @staticmethod
    def _deliver(sub: _Subscription, event: Event) -> None:
        if not sub.matches(event):
            return
        if event.seq <= sub.last_seq:
            log.warning(
                "bus skipped seq %s: subscriber is already at seq %s (duplicate or late event)",
                event.seq,
                sub.last_seq,
            )
            return
        sub.last_seq = event.seq
        try:
            sub.callback(event)
        except Exception:
            log.exception("bus subscriber failed for seq %s", event.seq)
