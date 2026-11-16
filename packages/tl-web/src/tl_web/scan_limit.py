"""A miss counter for the scan page (P2-QR-S3): guessing a code costs the guesser a budget.

Misses are counted per session (a hash of the cookie token, never the token) and per client
address, in a sliding window. Once either count has reached its limit, every lookup of that session
or address is refused (hit or miss alike, so the refusal tells nothing about a code) until the
oldest miss leaves the window. Only a miss counts: a lookup is counted before it runs and a hit
gives the count back, so a hit neither adds to the count nor clears it, and concurrent lookups
cannot pass the limit.

It is in process and in memory, bounded by ``MAX_KEYS`` (the key that has been quiet longest is
dropped first). It is a second layer behind a proxy's own limit, like ``tl_api.ratelimit``.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

MISS_LIMIT_SESSION = 10
MISS_LIMIT_ADDRESS = 30
WINDOW_S = 600
MAX_KEYS = 10_000


def session_key(token: str) -> str:
    """The counting key of a session token: a digest, so memory never holds the token."""
    return "s:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def address_key(address: str) -> str:
    return "a:" + address


class MissCounter:
    """Sliding windows of miss times per key, two limits, a bounded number of keys."""

    def __init__(
        self,
        *,
        session_limit: int = MISS_LIMIT_SESSION,
        address_limit: int = MISS_LIMIT_ADDRESS,
        window_s: float = WINDOW_S,
        max_keys: int = MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min(session_limit, address_limit, max_keys) < 1 or window_s <= 0:
            raise ValueError("limits and key cap must be at least 1 and the window positive")
        self.session_limit, self.address_limit = session_limit, address_limit
        self.window_s, self.max_keys = window_s, max_keys
        self._clock = clock
        self._seen: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float] | None:
        times = self._seen.get(key)
        if times is None:
            return None
        while times and times[0] <= now - self.window_s:
            times.popleft()
        if not times:
            del self._seen[key]
            return None
        return times

    def _wait(self, key: str, limit: int, now: float) -> float:
        times = self._trim(key, now)
        if times is None or len(times) < limit:
            return 0.0
        self._seen.move_to_end(key)  # a limited key stays recent: eviction takes quiet ones
        return max(times[-limit] + self.window_s - now, 0.001)

    def reserve(self, token: str, address: str) -> tuple[int, float]:
        """Count one lookup for this session and address, atomically with the limit check.

        Returns ``(0, stamp)`` when the lookup may run (it is already counted, so a burst of
        concurrent lookups cannot pass the limit), else ``(seconds to wait, 0.0)`` and nothing is
        counted. A hit gives its count back with ``refund(..., stamp)``; a miss keeps it.
        """
        with self._lock:
            now = self._clock()
            wait = max(
                self._wait(session_key(token), self.session_limit, now),
                self._wait(address_key(address), self.address_limit, now),
            )
            if wait > 0:
                return math.ceil(wait), 0.0
            for key in (session_key(token), address_key(address)):
                times = self._seen.get(key)
                if times is None:
                    times = deque()
                    self._seen[key] = times
                    while len(self._seen) > self.max_keys:
                        self._seen.popitem(last=False)
                else:
                    self._seen.move_to_end(key)
                times.append(now)
            return 0, now

    def refund(self, token: str, address: str, stamp: float) -> None:
        """Take back the count of a lookup that turned out to be a hit."""
        with self._lock:
            for key in (session_key(token), address_key(address)):
                times = self._seen.get(key)
                if times is not None and stamp in times:
                    times.remove(stamp)
                    if not times:
                        del self._seen[key]

    def keys(self) -> int:
        with self._lock:
            return len(self._seen)
