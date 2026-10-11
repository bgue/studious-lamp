"""A per-source limit on failed sign-ins, in front of the per-name lockout (ADR-0009 section 6).

The lockout counts failures per username, so one source trying a password against many names
(password spraying) never trips it. This counts failures per **client address**: 20 failed
`POST /auth/sign-in` in 10 minutes from one address, and the 21st is answered 429 `rate_limited`
with `Retry-After` before any password is hashed. It is process-local and in memory, so it is a
second layer and not a replacement for a rate limiter in the front door (a reverse proxy or
gateway), which is a release gate: see ADR-0009 and `docs/runbooks/accounts-and-access.md`.

The address is the socket peer. Behind a reverse proxy that is the proxy, so a deployment sets
`TL_TRUSTED_PROXY_HEADER` (for example `X-Forwarded-For`) and the **last** entry of that header,
which only the trusted proxy writes, is used. Without that setting the header is ignored, so a
client cannot choose its own address.
"""

from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_FAILURES = 20
DEFAULT_WINDOW_S = 600.0
MAX_SOURCES = 10_000
#: Responses that count as a failed attempt: bad credentials, a disabled account, a locked name.
FAILURE_STATUSES = frozenset({401, 403, 423})


class SourceLimiter:
    """A sliding window of failure times per source key, with a bounded number of sources."""

    def __init__(
        self,
        failures: int = DEFAULT_FAILURES,
        window_s: float = DEFAULT_WINDOW_S,
        *,
        max_sources: int = MAX_SOURCES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failures < 1 or window_s <= 0:
            raise ValueError("failures must be at least 1 and the window positive")
        self.failures, self.window_s, self.max_sources = failures, window_s, max_sources
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

    def retry_after(self, key: str) -> float:
        """Seconds until ``key`` may try again; 0 when it may now."""
        with self._lock:
            now = self._clock()
            times = self._trim(key, now)
            if times is None or len(times) < self.failures:
                return 0.0
            return max(times[0] + self.window_s - now, 0.001)

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            times = self._trim(key, now)
            if times is None:
                times = deque()
                self._seen[key] = times
                while len(self._seen) > self.max_sources:
                    self._seen.popitem(last=False)  # the source that has been quiet longest
            else:
                self._seen.move_to_end(key)
            times.append(now)

    def sources(self) -> int:
        with self._lock:
            return len(self._seen)


def client_key(scope: Scope, trusted_header: str | None) -> str:
    """The address failures are counted under: the trusted proxy's last entry, else the peer."""
    peer = scope.get("client")
    key = str(peer[0]) if peer else "unknown"
    if trusted_header:
        wanted = trusted_header.lower().encode("latin-1")
        for name, value in scope["headers"]:
            if name.lower() == wanted:
                last = value.decode("latin-1").split(",")[-1].strip()
                try:
                    return str(ipaddress.ip_address(last))
                except ValueError:
                    return key  # not an address: fall back to the peer, never trust garbage
    return key


class RateLimitMiddleware:
    """429 for a source that has failed too often on one route; counts failures from its answers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: SourceLimiter,
        trusted_header: str | None = None,
        method: str = "POST",
        path: str = "/auth/sign-in",
    ) -> None:
        self.app = app
        self._limiter = limiter
        self._trusted = trusted_header
        self._method = method
        self._path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != self._method
            or scope["path"] != self._path
        ):
            await self.app(scope, receive, send)
            return
        key = client_key(scope, self._trusted)
        wait = self._limiter.retry_after(key)
        if wait > 0:
            response = JSONResponse(
                {"error": "rate_limited", "message": "too many failed sign-ins from this address"},
                status_code=429,
                headers={"Retry-After": str(math.ceil(wait))},
            )
            await response(scope, receive, send)
            return

        async def counting_send(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] in FAILURE_STATUSES:
                self._limiter.record_failure(key)
            await send(message)

        await self.app(scope, receive, counting_send)
