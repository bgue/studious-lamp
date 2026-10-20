"""The httpx transport against a real local server: pinned IP, Host header, no redirects."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from tl_core.webhooks.egress import EgressPolicy, ResolvedTarget
from tl_core.webhooks.transport import HttpxTransport


class Handler(BaseHTTPRequestHandler):
    seen: list[dict[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).seen.append(
            {**{k.lower(): v for k, v in self.headers.items()}, "body": body.decode()}
        )
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(1.0)
            self.send_response(200)
            self.end_headers()
        elif self.path == "/limited":
            self.send_response(429)
            self.send_header("Retry-After", "120")
            self.end_headers()
            self.wfile.write(b"slow down\x00\x01")
        elif self.path == "/trickle":
            # an answer that never stops arriving: a byte every 0.2 s, inside any per-read timeout
            self.send_response(200)
            self.send_header("Content-Length", "40")
            self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.2)
            except OSError:
                return
        elif self.path == "/big":
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            self.wfile.write(b"x" * 100000)
        else:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@pytest.fixture
def server() -> Iterator[int]:
    Handler.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def target(port: int, path: str = "/in") -> ResolvedTarget:
    policy = EgressPolicy(("hook.test",), lambda host, p: ["127.0.0.1"])
    return policy.check(f"http://hook.test:{port}{path}")


def test_it_connects_to_the_pinned_ip_and_presents_the_original_host(server: int) -> None:
    result = HttpxTransport().send(
        target(server),
        {"webhook-id": "abc", "Content-Type": "application/json"},
        b'{"a":1}',
        timeout_s=5,
    )
    assert result.ok and result.status == 200 and result.excerpt == "ok"
    seen = Handler.seen[0]
    assert seen["host"] == f"hook.test:{server}"
    assert seen["webhook-id"] == "abc" and seen["body"] == '{"a":1}'
    assert seen["user-agent"].startswith("Throughline-Webhooks")


def test_redirects_are_not_followed(server: int) -> None:
    result = HttpxTransport().send(target(server, "/redirect"), {}, b"{}", timeout_s=5)
    assert result.status == 302 and not result.ok
    assert len(Handler.seen) == 1


def test_retry_after_and_a_log_safe_excerpt(server: int) -> None:
    result = HttpxTransport().send(target(server, "/limited"), {}, b"{}", timeout_s=5)
    assert result.status == 429 and result.retry_after_s == 120
    assert result.excerpt == "slow down"


def test_a_huge_response_is_cut_short(server: int) -> None:
    result = HttpxTransport().send(target(server, "/big"), {}, b"{}", timeout_s=5)
    assert result.ok and len(result.excerpt) <= 512


def test_timeouts_and_refused_connections_become_errors_not_exceptions(server: int) -> None:
    slow = HttpxTransport().send(target(server, "/slow"), {}, b"{}", timeout_s=0.2)
    assert slow.status is None and slow.error is not None and not slow.ok
    refused = HttpxTransport().send(target(1), {}, b"{}", timeout_s=1)
    assert refused.status is None and refused.error is not None


def test_a_server_that_trickles_cannot_hold_the_exchange_past_its_budget(server: int) -> None:
    """httpx's timeout is per read, so each byte restarts it; the total budget is ours."""
    started = time.monotonic()
    result = HttpxTransport(max_response_bytes=100_000).send(
        target(server, "/trickle"), {}, b"{}", timeout_s=1.0
    )
    assert time.monotonic() - started < 4.0
    assert result.status is None and result.error is not None
    assert result.error.startswith("DeadlineExceeded")


def test_the_action_executor_gets_the_same_deadline(server: int) -> None:
    """The second caller of the transport: a webhook action with a short ``timeout_s``."""
    from tl_core.integration.contract import ActionRequest, RecordRef, WebhookExecutorConfig
    from tl_core.integration.executors.webhook import WebhookExecutor
    from tl_core.webhooks.signing import SigningSecret, generate_secret

    secret = SigningSecret(generate_secret())
    executor = WebhookExecutor(
        policy=EgressPolicy(("hook.test",), lambda host, p: ["127.0.0.1"]),
        transport=HttpxTransport(max_response_bytes=100_000),
        secrets=lambda secret_id: [secret],
    )
    config = WebhookExecutorConfig(
        url=f"http://hook.test:{server}/trickle", secret_id="S" * 26, timeout_s=1
    )
    request = ActionRequest(
        invocation_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", action="a", action_version=1,
        scope="project:P1", targets=[RecordRef(id="r1", record_type="core.Record")],
        parameters={}, invoked_by="user:x", attempt=1, config=config,
    )  # fmt: skip
    started = time.monotonic()
    outcome = executor.execute(request)
    assert time.monotonic() - started < 4.0
    assert outcome.status == "failed" and outcome.retryable


def test_a_larger_cap_does_not_cut_the_excerpt(server: int) -> None:
    result = HttpxTransport(max_response_bytes=100_000).send(
        target(server, "/big"), {}, b"{}", timeout_s=5
    )
    assert len(result.excerpt) == 100_000 and not result.truncated
    default = HttpxTransport().send(target(server, "/big"), {}, b"{}", timeout_s=5)
    assert len(default.excerpt) == 512 and default.truncated


def test_a_server_that_drips_its_headers_cannot_hold_the_exchange_past_its_budget() -> None:
    """The header phase is outside the body loop: a header line every 0.4 s never trips httpx's
    per-read timeout, so only a watchdog over the whole exchange stops it (second review)."""
    import socket

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(2.0)
            try:
                conn.recv(65536)
                conn.sendall(b"HTTP/1.1 200 OK\r\n")
                for n in range(60):
                    if stop.is_set():
                        return
                    conn.sendall(f"X-Drip-{n}: y\r\n".encode())
                    time.sleep(0.4)
            except OSError:
                return

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    started = time.monotonic()
    result = HttpxTransport().send(target(port), {}, b"{}", timeout_s=1.0)
    elapsed = time.monotonic() - started
    stop.set()
    listener.close()
    assert elapsed < 3.0, elapsed
    assert result.status is None and result.error is not None
    assert result.error.startswith("DeadlineExceeded")
