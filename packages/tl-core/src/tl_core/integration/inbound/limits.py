"""Process-local volume bounds for the inbound route (FANOUT D4 step 2).

A sliding window of hit times per key, with a bounded number of keys. ``hit`` records an attempt
and says how long the caller must wait (0 when it may go on). It is a second layer behind the
front door's own limiter, which stays a release gate (ADR-0009); it is not shared between
processes. Two bounds use it: one per endpoint (its ``rate_per_minute``) and one for the whole
process (``INBOUND_GLOBAL_RATE_PER_MINUTE``). A refused hit is not counted, so a flood does not keep
the window full for ever.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

WINDOW_S = 60.0
MAX_KEYS = 10_000


class WindowCounter:
    def __init__(
        self,
        *,
        window_s: float = WINDOW_S,
        max_keys: int = MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window_s
        self._max_keys = max_keys
        self._clock = clock
        self._seen: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> float:
        """Count one attempt under ``key``; 0.0 when allowed, else seconds until it would be."""
        with self._lock:
            now = self._clock()
            times = self._seen.get(key)
            if times is None:
                times = deque[float]()
                self._seen[key] = times
                while len(self._seen) > self._max_keys:
                    self._seen.popitem(last=False)
            else:
                self._seen.move_to_end(key)
            while times and times[0] <= now - self._window:
                times.popleft()
            if len(times) >= limit:
                return max(times[0] + self._window - now, 0.001)
            times.append(now)
            return 0.0

    def keys(self) -> int:
        with self._lock:
            return len(self._seen)


__all__ = ["MAX_KEYS", "WINDOW_S", "WindowCounter"]
