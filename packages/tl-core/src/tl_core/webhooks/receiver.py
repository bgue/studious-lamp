"""A local webhook receiver for development, tests and the demo (brief 18.4, local tunnels).

``DevReceiver`` runs an HTTP server on 127.0.0.1 in a background thread. It verifies the Standard
Webhooks signature of every POST (any configured secret may match, so a rotation overlap works),
answers 200 for a good message and 401 for a bad one, records both, flags a repeated ``webhook-id``
as a duplicate (still 200, as a real receiver that dedupes would), and can be told to fail the next
requests with chosen statuses to exercise retries. It is allow-listed explicitly by whoever uses it
(``EgressPolicy(("127.0.0.1",))``); production egress never reaches loopback.

STUB (P0-I5-T23): the method bodies raise ``NotImplementedError``. The specification is the
ticket and the provided test.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Received:
    """One POST the receiver handled."""

    path: str
    webhook_id: str
    body: str
    headers: dict[str, str]  # lower-case names
    verified: bool
    duplicate: bool

    def event(self) -> dict[str, Any]:
        """The body parsed as JSON."""
        return json.loads(self.body)


class DevReceiver:
    def __init__(
        self,
        secrets: Sequence[str] = (),
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        tolerance_s: int = 300,
        clock: Callable[[], float] = time.time,
    ) -> None:
        raise NotImplementedError

    @property
    def port(self) -> int:
        """The bound port. ``RuntimeError`` while the receiver is not running."""
        raise NotImplementedError

    @property
    def url(self) -> str:
        """``http://<host>:<port>/hook``."""
        raise NotImplementedError

    def start(self) -> None:
        """Bind and serve in a daemon thread. ``RuntimeError`` if already running."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop serving and release the port. Harmless when not running."""
        raise NotImplementedError

    def __enter__(self) -> DevReceiver:
        raise NotImplementedError

    def __exit__(self, *exc: object) -> None:
        raise NotImplementedError

    def fail_next(self, statuses: Sequence[int]) -> None:
        """Answer the next requests with these HTTP statuses, in order, then resume normally."""
        raise NotImplementedError

    def set_secrets(self, secrets: Sequence[str]) -> None:
        """Replace the secrets a signature may match (``whsec_...`` strings)."""
        raise NotImplementedError

    def messages(self) -> list[Received]:
        """Accepted messages in arrival order, duplicates included (a copy)."""
        raise NotImplementedError

    def rejected(self) -> list[Received]:
        """Requests answered with a scripted failure or 401 (a copy)."""
        raise NotImplementedError

    def unique(self) -> list[Received]:
        """Accepted messages that were not duplicates."""
        raise NotImplementedError

    def wait_for(self, count: int, timeout_s: float = 10.0) -> bool:
        """Block until at least ``count`` messages were accepted; False on timeout."""
        raise NotImplementedError

    def clear(self) -> None:
        """Forget messages, rejected requests, scripted failures and seen ids."""
        raise NotImplementedError
