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
