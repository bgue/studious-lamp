"""What a read of an XER file gives back, and the one exception it can raise (P1-I4-T03)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tl_xer.process import Status
from tl_xer.typed import Snapshot

LIMIT_MESSAGE = "reading the XER file broke the resource limits"


class XerLimitError(Exception):
    """The child broke the envelope or answered something malformed. ``reason`` is all there is.

    ``reason`` is ``limit`` (time, memory or CPU), ``crash`` (died, no answer, a malformed answer)
    or ``too_large`` (an answer past its bound). The message is fixed: no trace, no path.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(LIMIT_MESSAGE)
        self.reason = reason


@dataclass(frozen=True)
class XerResult:
    """A checked answer. ``snapshot``, the typed JSON and the raw bundle exist only when valid."""

    status: Status
    report: dict[str, Any]
    snapshot: Snapshot | None = None
    typed_json: bytes | None = None
    typed_sha256: str | None = None
    raw_gz: bytes | None = None
    raw_sha256: str | None = None
