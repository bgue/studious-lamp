"""The live change feed behind ``GET /events`` and ``GET /stream`` (brief 5.3, 18.1).

One :class:`FeedHub` per application owns the subscription registry, fed two ways: the backend's
bus (writes made in this process arrive at once) and a poller over the ledger (writes made by other
processes, such as an embedded TUI sharing the SQLite file, arrive within ``poll_interval_s``). The
registry drops an event it has already delivered, so both sources can offer the same one.

SSE contract (documented in the README): each event is sent as

    id: <seq>
    event: <event type, e.g. Record.Created>
    data: <the Event as JSON>

A client reconnects with ``Last-Event-ID: <last seq>`` (or ``?after=<seq>``); delivery is
at-least-once and in ``seq`` order, with no gap between the catch-up and the live part. Without a
cursor the stream is live only. ``: keep-alive`` comment lines are sent when the stream is idle.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from tl_core.bus import Subscription
from tl_core.changefeed import (
    ChangePoller,
    QueueSubscription,
    SubscriptionFilter,
    SubscriptionOverflow,
    SubscriptionRegistry,
    fetch_changes,
)
from tl_core.ledger import Event

from tl_api.backend import Backend

CATCH_UP_PAGE = 200
MAX_STREAMS = 32


def format_event(event: Event) -> str:
    """One SSE message for ``event``: ``id`` is the ledger ``seq``."""
    return f"id: {event.seq}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"


class FeedHub:
    """The registry, the poller and a bounded set of stream workers for one application."""

    def __init__(
        self,
        backend: Backend,
        *,
        poll_interval_s: float = 0.25,
        keepalive_s: float = 15.0,
        wait_s: float = 1.0,
        max_streams: int = MAX_STREAMS,
    ) -> None:
        self.backend = backend
        self._registry: SubscriptionRegistry | None = None
        self._attached: Subscription | None = None
        self._poll_interval_s = poll_interval_s
        self.poller: ChangePoller | None = None  # built in start(): it reads the ledger head
        self.keepalive_s = keepalive_s
        self.wait_s = wait_s  # how long a worker blocks on the queue before looking again
        self._executor = ThreadPoolExecutor(max_workers=max_streams, thread_name_prefix="tl-sse")
        self._max_streams = max_streams
        self._open = 0
        self._lock = threading.Lock()

    @property
    def registry(self) -> SubscriptionRegistry:
        """The registry, built on first use so that creating an app touches no storage."""
        with self._lock:
            if self._registry is None:
                self._registry = SubscriptionRegistry(self.backend.ledger)
                self._attached = self._registry.attach(self.backend.bus)
            return self._registry

    def start(self) -> None:
        """Start looking for events written by other processes (idempotent)."""
        if self.poller is None:
            self.poller = ChangePoller(
                self.backend.ledger, self.registry, interval_s=self._poll_interval_s
            )
        if not self.poller.running:
            self.poller.start()

    def stop(self) -> None:
        if self.poller is not None:
            self.poller.stop()
        if self._attached is not None:
            self._attached.close()
        if self._registry is not None:
            self._registry.close()
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def open_streams(self) -> int:
        return self._open

    def try_open_stream(self) -> bool:
        """Reserve a stream slot; ``False`` when ``max_streams`` streams are already open."""
        with self._lock:
            if self._open >= self._max_streams:
                return False
            self._open += 1
            return True

    def release_stream(self) -> None:
        with self._lock:
            self._open = max(0, self._open - 1)

    async def stream(
        self, flt: SubscriptionFilter, after_seq: int | None = None
    ) -> AsyncIterator[str]:
        """SSE text chunks for the matching events, until the consumer stops iterating.

        The caller reserved a slot with :meth:`try_open_stream` and releases it when the response
        ends (``SlotResponse`` in ``routes/events.py``), whether or not this generator ever ran.
        """
        loop = asyncio.get_running_loop()
        sub: QueueSubscription | None = None
        try:
            yield ": connected\n\n"
            cursor = after_seq
            if cursor is not None:
                while True:
                    page = await loop.run_in_executor(
                        self._executor,
                        partial(
                            fetch_changes,
                            self.backend.ledger,
                            after_seq=cursor,
                            flt=flt,
                            limit=CATCH_UP_PAGE,
                        ),
                    )
                    for event in page.events:
                        yield format_event(event)
                    cursor = page.next_seq
                    if not page.has_more:
                        break
            sub = self.registry.subscribe_queue(flt, after_seq=cursor)
            idle = 0.0
            while True:
                try:
                    events = await loop.run_in_executor(
                        self._executor, sub.get_many, 100, self.wait_s
                    )
                except SubscriptionOverflow as overflow:
                    sub.close()
                    sub = self.registry.subscribe_queue(flt, after_seq=overflow.resume_seq)
                    continue
                if events:
                    idle = 0.0
                    for event in events:
                        yield format_event(event)
                else:
                    idle += self.wait_s
                    if idle >= self.keepalive_s:
                        idle = 0.0
                        yield ": keep-alive\n\n"
        finally:
            if sub is not None:
                sub.close()
