"""The network side of delivery: a ``Transport`` Protocol and the httpx implementation.

The engine never imports httpx; tests and the demo use a real local receiver through
``HttpxTransport`` or a fake transport. ``HttpxTransport`` connects to the **pinned IP** that
:meth:`tl_core.webhooks.egress.EgressPolicy.check` returned and sends the original host in ``Host``
and in TLS SNI (so the certificate is still checked against the host name). It does not follow
redirects, sends no cookies and reads at most ``MAX_RESPONSE_BYTES`` of the answer.
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


@dataclass(frozen=True)
class TransportResult:
    """What happened to one request. ``status`` is None when no response arrived."""

    status: int | None
    latency_ms: int
    excerpt: str = ""
    error: str | None = None
    retry_after_s: float | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class Transport(Protocol):
    def send(
        self, target: ResolvedTarget, headers: dict[str, str], body: bytes, *, timeout_s: float
    ) -> TransportResult: ...


def excerpt_of(raw: bytes) -> str:
    """A log-safe excerpt of a response body: decoded leniently, control characters removed."""
    text = raw[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
    return "".join(ch for ch in text if ch.isprintable() or ch == " ")[:EXCERPT_CHARS]


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
    """Send over HTTP(S) with httpx to the pinned address."""

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
                    if len(received) >= MAX_RESPONSE_BYTES:
                        break
                return TransportResult(
                    status=response.status_code,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    excerpt=excerpt_of(bytes(received)),
                    retry_after_s=parse_retry_after(response.headers.get("retry-after")),
                )
        except httpx.HTTPError as exc:
            return TransportResult(
                status=None,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}"[:200],
            )
