"""A change feed the test drives by hand (P0-I4): `push` delivers events to the sink, in order.

``FakeFeed.follow`` blocks on a queue like the real feeds block on I/O, so the threading from the
feed thread into the app is exercised exactly as in production. ``connect`` and ``drop`` change the
reported connection state.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

from tl_core.ledger import Event
from tl_tui.live import FeedSink
from tl_tui.messages import ConnectionState


class FakeFeed:
    def __init__(self) -> None:
        self._items: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.started = threading.Event()
        self.closed = False

    def push(self, *events: Event) -> None:
        self._items.put(("events", list(events)))

    def state(self, state: ConnectionState, detail: str = "") -> None:
        self._items.put(("state", (state, detail)))

    def follow(self, sink: FeedSink, stop: threading.Event) -> None:
        sink.connection("live")
        self.started.set()
        while not stop.is_set():
            try:
                kind, payload = self._items.get(timeout=0.05)
            except queue.Empty:
                continue
            if kind == "events":
                sink.events(payload)
            else:
                sink.connection(*payload)

    def close(self) -> None:
        self.closed = True
