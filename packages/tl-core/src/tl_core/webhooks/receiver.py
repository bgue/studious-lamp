"""A local webhook receiver for development, tests and the demo (brief 18.4, local tunnels).

``DevReceiver`` runs an HTTP server on 127.0.0.1 in a background thread. It verifies the Standard
Webhooks signature of every POST (any configured secret may match, so a rotation overlap works),
answers 200 for a good message and 401 for a bad one, records both, flags a repeated ``webhook-id``
as a duplicate (still 200, as a real receiver that dedupes would), and can be told to fail the next
requests with chosen statuses to exercise retries. It is allow-listed explicitly by whoever uses it
(``EgressPolicy(("127.0.0.1",))``); production egress never reaches loopback.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tl_core.webhooks.signing import SignatureError, SigningSecret, verify


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
        self._host = host
        self._requested_port = port
        self._tolerance = tolerance_s
        self._clock = clock
        self._secrets: list[SigningSecret] = [SigningSecret(value) for value in secrets]
        self._cond = threading.Condition(threading.Lock())
        self._accepted: list[Received] = []
        self._rejected: list[Received] = []
        self._script: list[int] = []
        self._seen: set[str] = set()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The bound port. ``RuntimeError`` while the receiver is not running."""
        if self._server is None:
            raise RuntimeError("the receiver is not running")
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        """``http://<host>:<port>/hook``."""
        return f"http://{self._host}:{self.port}/hook"

    def start(self) -> None:
        """Bind and serve in a daemon thread. ``RuntimeError`` if already running."""
        if self._server is not None:
            raise RuntimeError("the receiver is already running")
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length)
                body = raw.decode("utf-8", errors="replace")
                headers = {name.lower(): value for name, value in self.headers.items()}
                status, answer = receiver._handle(self.path, headers, body)
                payload = json.dumps(answer).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        server = ThreadingHTTPServer((self._host, self._requested_port), Handler)
        thread = threading.Thread(target=server.serve_forever, name="tl-dev-receiver", daemon=True)
        self._server = server
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        """Stop serving and release the port. Harmless when not running."""
        server = self._server
        thread = self._thread
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        self._server = None
        self._thread = None

    def __enter__(self) -> DevReceiver:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def fail_next(self, statuses: Sequence[int]) -> None:
        """Answer the next requests with these HTTP statuses, in order, then resume normally."""
        with self._cond:
            self._script.extend(statuses)

    def set_secrets(self, secrets: Sequence[str]) -> None:
        """Replace the secrets a signature may match (``whsec_...`` strings)."""
        with self._cond:
            self._secrets = [SigningSecret(value) for value in secrets]

    def messages(self) -> list[Received]:
        """Accepted messages in arrival order, duplicates included (a copy)."""
        with self._cond:
            return list(self._accepted)

    def rejected(self) -> list[Received]:
        """Requests answered with a scripted failure or 401 (a copy)."""
        with self._cond:
            return list(self._rejected)

    def unique(self) -> list[Received]:
        """Accepted messages that were not duplicates."""
        with self._cond:
            return [message for message in self._accepted if not message.duplicate]

    def wait_for(self, count: int, timeout_s: float = 10.0) -> bool:
        """Block until at least ``count`` messages were accepted; False on timeout."""
        with self._cond:
            return self._cond.wait_for(lambda: len(self._accepted) >= count, timeout_s)

    def clear(self) -> None:
        """Forget messages, rejected requests, scripted failures and seen ids."""
        with self._cond:
            self._accepted.clear()
            self._rejected.clear()
            self._script.clear()
            self._seen.clear()

    def _handle(self, path: str, headers: dict[str, str], body: str) -> tuple[int, dict[str, Any]]:
        """Verify, record and answer one POST. Everything happens under the lock."""
        message_id = headers.get("webhook-id", "")
        with self._cond:
            try:
                verify(
                    headers,
                    body,
                    self._secrets,
                    now=self._clock(),
                    tolerance_s=self._tolerance,
                )
                verified = True
            except SignatureError:
                verified = False

            if self._script:
                status = self._script.pop(0)
                self._rejected.append(
                    Received(
                        path=path,
                        webhook_id=message_id,
                        body=body,
                        headers=headers,
                        verified=verified,
                        duplicate=False,
                    )
                )
                self._cond.notify_all()
                return status, {"ok": False, "scripted": True}

            if not verified:
                self._rejected.append(
                    Received(
                        path=path,
                        webhook_id=message_id,
                        body=body,
                        headers=headers,
                        verified=False,
                        duplicate=False,
                    )
                )
                return 401, {"ok": False, "error": "bad signature"}

            duplicate = message_id in self._seen
            self._seen.add(message_id)
            self._accepted.append(
                Received(
                    path=path,
                    webhook_id=message_id,
                    body=body,
                    headers=headers,
                    verified=True,
                    duplicate=duplicate,
                )
            )
            self._cond.notify_all()
            return 200, {"ok": True, "duplicate": duplicate}
