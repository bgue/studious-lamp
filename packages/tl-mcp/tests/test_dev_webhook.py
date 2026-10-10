"""``send_test_webhook``: a signed catalog sample to a loopback receiver, and what it must refuse.

Receivers are real ``DevReceiver`` servers on 127.0.0.1 and the throw-away servers below are real
``http.server`` threads on 127.0.0.1. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from tl_core.webhooks.receiver import DevReceiver
from tl_core.webhooks.signing import SigningSecret, generate_secret, verify
from tl_mcp.dev.guard import redact_url

WRONG_SECRET = generate_secret()


class _ThrowAway:
    """A loopback HTTP server that answers every POST with ``status`` and ``headers``."""

    def __init__(self, status: int, headers: dict[str, str], delay_s: float = 0.0) -> None:
        self.hits: list[str] = []
        self._gate = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                self.rfile.read(length)
                owner.hits.append(self.path)
                if delay_s:
                    owner._gate.wait(delay_s)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/hook"

    def __enter__(self) -> _ThrowAway:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._gate.set()
        self._server.shutdown()
        self._server.server_close()


def _audit_text(env: DevHarness) -> str:
    path = env.ctx.audit_path
    assert path is not None
    return path.read_text(encoding="ascii") if path.exists() else ""


def test_delivery_is_signed_and_marked_as_a_test(dev_env: DevHarness) -> None:
    secret = generate_secret()
    with DevReceiver([secret]) as receiver:
        out = dev_env.structured("send_test_webhook", url=receiver.url, secret=secret)
        assert out["ok"] is True
        assert out["status"] == 200
        assert out["secret"] is None
        assert out["header"] == "webhook-test: 1"
        assert out["target"] == f"127.0.0.1:{receiver.port}"
        assert receiver.wait_for(1)
        messages = receiver.messages()
    assert len(messages) == 1
    received = messages[0]
    assert received.verified is True
    assert received.headers["webhook-test"] == "1"
    event = json.loads(received.body)
    assert event["type"].endswith(".Record.Created.v1")
    assert event["id"] == out["event_id"]


def test_generated_secret_is_returned_and_verifies(dev_env: DevHarness) -> None:
    with DevReceiver([generate_secret()]) as receiver:
        out = dev_env.structured("send_test_webhook", url=receiver.url)
        assert out["ok"] is False
        assert out["status"] == 401
        assert isinstance(out["secret"], str)
        assert out["secret"].startswith("whsec_")
        rejected = receiver.rejected()
    assert len(rejected) == 1
    assert rejected[0].verified is False
    verify(rejected[0].headers, rejected[0].body, [SigningSecret(out["secret"])])


def test_a_wrong_secret_is_rejected_by_the_receiver(dev_env: DevHarness) -> None:
    with DevReceiver([generate_secret()]) as receiver:
        out = dev_env.structured("send_test_webhook", url=receiver.url, secret=WRONG_SECRET)
        assert out["status"] == 401
        assert out["ok"] is False
        assert out["secret"] is None
        assert receiver.messages() == []


def test_another_catalog_event_type_is_sent(dev_env: DevHarness) -> None:
    secret = generate_secret()
    with DevReceiver([secret]) as receiver:
        out = dev_env.structured(
            "send_test_webhook", url=receiver.url, secret=secret, event_type="Link.Added"
        )
        assert out["ok"] is True
        assert out["event_type"] == "Link.Added"
        assert receiver.wait_for(1)
        event = json.loads(receiver.messages()[0].body)
    assert event["type"].endswith(".Link.Added.v1")


def test_an_unknown_event_type_is_refused(dev_env: DevHarness) -> None:
    with DevReceiver([generate_secret()]) as receiver:
        with pytest.raises(ToolError, match="Nope.Created"):
            dev_env.call("send_test_webhook", url=receiver.url, event_type="Nope.Created")
        assert receiver.messages() == []
        assert receiver.rejected() == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/h",
        "http://10.0.0.1/h",
        "http://169.254.169.254/",
        "http://2130706433/",
        "http://127.0.0.1.nip.io/",
        "http://user:pw@127.0.0.1/",
        "ftp://127.0.0.1/",
        "file:///etc/passwd",
    ],
)
def test_refused_targets_are_audited_and_receive_nothing(dev_env: DevHarness, url: str) -> None:
    with DevReceiver([generate_secret()]) as receiver:
        with pytest.raises(ToolError, match="refused"):
            dev_env.call("send_test_webhook", url=url)
        assert receiver.messages() == []
        assert receiver.rejected() == []
    refusals = [
        line
        for line in dev_env.audit_lines()
        if line["tool"] == "send_test_webhook" and line["outcome"] == "refused"
    ]
    expected = redact_url(url)  # a password in the URL never reaches the audit file
    assert any(line["detail"]["url"] == expected for line in refusals)


def test_a_malformed_secret_is_refused(dev_env: DevHarness) -> None:
    with DevReceiver([generate_secret()]) as receiver:
        with pytest.raises(ToolError):
            dev_env.call("send_test_webhook", url=receiver.url, secret="abc")
        assert receiver.messages() == []
        assert receiver.rejected() == []


def test_a_redirect_is_not_followed(dev_env: DevHarness) -> None:
    with _ThrowAway(302, {"Location": "http://example.com/"}) as away:
        out = dev_env.structured("send_test_webhook", url=away.url)
        assert out["status"] == 302
        assert out["ok"] is False
        assert len(away.hits) == 1


def test_proxy_variables_are_ignored(dev_env: DevHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    dead_proxy = "http://127.0.0.1:9"
    monkeypatch.setenv("HTTP_PROXY", dead_proxy)
    monkeypatch.setenv("HTTPS_PROXY", dead_proxy)
    monkeypatch.setenv("http_proxy", dead_proxy)
    secret = generate_secret()
    with DevReceiver([secret]) as receiver:
        out = dev_env.structured("send_test_webhook", url=receiver.url, secret=secret)
        assert out["ok"] is True
        assert out["status"] == 200


def test_a_receiver_that_is_not_listening_is_a_result(dev_env: DevHarness) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # the port was just closed: nothing listens on it
    started = time.monotonic()
    out = dev_env.structured("send_test_webhook", url=f"http://127.0.0.1:{port}/hook")
    elapsed = time.monotonic() - started
    assert out["ok"] is False
    assert out["status"] is None
    assert out["error"]
    assert elapsed < 3


@pytest.fixture
def slow_receiver() -> Iterator[_ThrowAway]:
    with _ThrowAway(200, {}, delay_s=5.0) as away:
        yield away


def test_a_slow_receiver_times_out(dev_env: DevHarness, slow_receiver: _ThrowAway) -> None:
    started = time.monotonic()
    out = dev_env.structured("send_test_webhook", url=slow_receiver.url, timeout_s=1)
    elapsed = time.monotonic() - started
    assert out["ok"] is False
    assert out["status"] is None
    assert out["error"]
    assert "Timeout" in out["error"]
    assert elapsed < 4


def test_the_audit_record_holds_url_and_event_type_but_no_secret(dev_env: DevHarness) -> None:
    secret = generate_secret()
    with DevReceiver([secret]) as receiver:
        dev_env.structured("send_test_webhook", url=receiver.url, secret=secret)
        url = receiver.url
    lines = [line for line in dev_env.audit_lines() if line["tool"] == "send_test_webhook"]
    assert len(lines) == 1
    assert lines[0]["outcome"] == "ok"
    assert lines[0]["detail"]["url"] == url
    assert lines[0]["detail"]["event_type"] == "Record.Created"
    assert secret not in _audit_text(dev_env)
    assert secret[len("whsec_") :] not in _audit_text(dev_env)


def test_the_generated_secret_is_not_in_the_audit(dev_env: DevHarness) -> None:
    with DevReceiver([generate_secret()]) as receiver:
        out: dict[str, Any] = dev_env.structured("send_test_webhook", url=receiver.url)
    assert out["secret"] not in _audit_text(dev_env)


def test_userinfo_is_redacted_in_the_audit_and_the_error(dev_env: DevHarness) -> None:
    with pytest.raises(ToolError) as caught:
        dev_env.call("send_test_webhook", url="http://user:s3cret@127.0.0.1:9/h")
    assert "s3cret" not in str(caught.value)
    assert dev_env.ctx.audit_path is not None
    audit_text = dev_env.ctx.audit_path.read_text()
    assert "s3cret" not in audit_text and "***@127.0.0.1" in audit_text


def test_an_ipv6_target_is_shown_in_brackets(dev_env: DevHarness) -> None:
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class V6(HTTPServer):
        address_family = socket.AF_INET6

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.rfile.read(int(self.headers.get("content-length", "0")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    try:
        server = V6(("::1", 0), Handler)
    except OSError:
        pytest.skip("IPv6 loopback is not available")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        out = dev_env.structured("send_test_webhook", url=f"http://[::1]:{port}/h")
        assert out["ok"] is True and out["target"] == f"[::1]:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_format_target_brackets_ipv6() -> None:
    from tl_mcp.dev.tool_webhook import format_target

    assert format_target("127.0.0.1", 9000) == "127.0.0.1:9000"
    assert format_target("::1", 9000) == "[::1]:9000"
