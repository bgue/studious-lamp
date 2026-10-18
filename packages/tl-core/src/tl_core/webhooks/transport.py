"""The network side of delivery: a ``Transport`` Protocol and the httpx implementation.

The engine never imports httpx; tests and the demo use a real local receiver through
``HttpxTransport`` or a fake transport. ``HttpxTransport`` connects to the **pinned IP** that
:meth:`tl_core.webhooks.egress.EgressPolicy.check` returned and sends the original host in ``Host``
and in TLS SNI (so the certificate is still checked against the host name). It does not follow
redirects, sends no cookies, reads at most ``MAX_RESPONSE_BYTES`` of the answer and gives the
whole exchange ``timeout_s`` in total (not per read).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from tl_core.webhooks.egress import ResolvedTarget

MAX_RESPONSE_BYTES = 4096
EXCERPT_CHARS = 512
USER_AGENT = "Throughline-Webhooks/1"


class _DeadlineError(Exception):
    """The exchange outlived its total budget."""


@dataclass(frozen=True)
class TransportResult:
    """What happened to one request. ``status`` is None when no response arrived."""

    status: int | None
    latency_ms: int
    excerpt: str = ""
    error: str | None = None
    retry_after_s: float | None = None
    #: The answer was longer than the transport reads; ``excerpt`` is its start.
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class Transport(Protocol):
    def send(
        self, target: ResolvedTarget, headers: dict[str, str], body: bytes, *, timeout_s: float
    ) -> TransportResult: ...


def excerpt_of(
    raw: bytes, *, max_bytes: int = MAX_RESPONSE_BYTES, max_chars: int = EXCERPT_CHARS
) -> str:
    """A log-safe excerpt of a response body: decoded leniently, control characters removed."""
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    return "".join(ch for ch in text if ch.isprintable() or ch == " ")[:max_chars]


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a ``Retry-After`` header given as delta-seconds; HTTP dates are ignored."""
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


class HttpxTransport:
    """Send over HTTP(S) with httpx to the pinned address.

    ``max_response_bytes`` is how much of the answer is read (an action's synchronous result needs
    more than a delivery's log excerpt; P1-I7 passes ``ACTION_MAX_RESULT_BYTES``). One byte more
    than that is read, so a longer answer is known to be longer (``truncated``), never silently cut.
    """

    def __init__(
        self, *, max_response_bytes: int = MAX_RESPONSE_BYTES, excerpt_chars: int | None = None
    ) -> None:
        self._max_bytes = max_response_bytes
        # A delivery logs a short excerpt. A larger cap is a caller that needs the answer (an
        # action's result): the characters follow the bytes, so the cap is never silently cut.
        if excerpt_chars is None:
            excerpt_chars = (
                EXCERPT_CHARS if max_response_bytes <= MAX_RESPONSE_BYTES else max_response_bytes
            )
        self._excerpt_chars = excerpt_chars

    def send(
        self, target: ResolvedTarget, headers: dict[str, str], body: bytes, *, timeout_s: float
    ) -> TransportResult:
        host = f"[{target.ip}]" if ":" in target.ip else target.ip
        url = f"{target.scheme}://{host}:{target.port}{target.path_and_query}"
        request_headers = {**headers, "Host": target.host_header, "User-Agent": USER_AGENT}
        extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
        started = time.monotonic()
        try:
            with (
                httpx.Client(
                    timeout=timeout_s, follow_redirects=False, trust_env=False, cookies=None
                ) as client,
                client.stream(
                    "POST", url, content=body, headers=request_headers, extensions=extensions
                ) as response,
            ):
                received = bytearray()
                for chunk in response.iter_bytes():
                    received.extend(chunk)
                    if len(received) > self._max_bytes:
                        break
                    if time.monotonic() - started > timeout_s:
                        # httpx's timeout is per read: a server that trickles one byte at a time
                        # never trips it. ``timeout_s`` is also the budget of the whole exchange.
                        raise _DeadlineError("the response took longer than the time allowed")
                return TransportResult(
                    status=response.status_code,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    excerpt=excerpt_of(
                        bytes(received), max_bytes=self._max_bytes, max_chars=self._excerpt_chars
                    ),
                    retry_after_s=parse_retry_after(response.headers.get("retry-after")),
                    truncated=len(received) > self._max_bytes,
                )
        except _DeadlineError as exc:
            return TransportResult(
                status=None,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"DeadlineExceeded: {exc}"[:200],
            )
        except httpx.HTTPError as exc:
            return TransportResult(
                status=None,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}"[:200],
            )
