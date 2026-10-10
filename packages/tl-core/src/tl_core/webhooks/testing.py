"""Test doubles for the webhook engine. Not used by production code.

``ScriptedTransport`` stands in for the network: it records every request and answers from a script.
``FakeClock`` is a clock tests advance by hand. A real receiver on 127.0.0.1 is
``tl_core.webhooks.receiver`` (P0-I5-T23).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from tl_core.webhooks.egress import ResolvedTarget
from tl_core.webhooks.transport import TransportResult


class FakeClock:
    """A settable UTC clock. ``clock()`` returns the current fake time."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start if start is not None else datetime(2026, 10, 9, 3, 0, 0, tzinfo=UTC)
        self._lock = threading.Lock()

    def __call__(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, **delta: float) -> datetime:
        """Move forward (``seconds=``, ``minutes=``, ``hours=``) and return the new time."""
        with self._lock:
            self._now = self._now + timedelta(**delta)
            return self._now


@dataclass(frozen=True)
class SentRequest:
    target: ResolvedTarget
    headers: dict[str, str]
    body: bytes


Responder = Callable[[SentRequest], TransportResult]


@dataclass
class ScriptedTransport:
    """Answers each request from ``script`` (a list consumed in order), then from ``default``.

    A script entry is a ``TransportResult`` or an HTTP status ``int``. Thread safe.
    """

    script: list[TransportResult | int] = field(default_factory=list[TransportResult | int])
    default: TransportResult | int = 200
    responder: Responder | None = None
    sent: list[SentRequest] = field(default_factory=list[SentRequest])
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def send(
        self, target: ResolvedTarget, headers: dict[str, str], body: bytes, *, timeout_s: float
    ) -> TransportResult:
        request = SentRequest(target, dict(headers), body)
        with self._lock:
            self.sent.append(request)
            answer: TransportResult | int = self.script.pop(0) if self.script else self.default
        if self.responder is not None:
            return self.responder(request)
        if isinstance(answer, int):
            return TransportResult(status=answer, latency_ms=1, excerpt=f"HTTP {answer}")
        return answer
