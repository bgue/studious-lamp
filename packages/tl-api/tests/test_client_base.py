"""The client base: transport failures, the one retry, path segments, commands."""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest
from tl_api.client import ApiClient
from tl_api.client.base import ApiUnavailableError, quote
from tl_api.errors import ApiError
from tl_core.services.commands import CreateRecord


def client_for(handler: Any) -> tuple[ApiClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def wrapped(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request, len(seen))

    http = httpx2.Client(transport=httpx2.MockTransport(wrapped), base_url="http://x")
    return ApiClient("http://x", "t", http=http), seen


def test_connection_refused_is_api_unavailable_and_keeps_its_cause() -> None:
    gone = ApiClient("http://127.0.0.1:9", "t", timeout=2.0)
    try:
        with pytest.raises(ApiUnavailableError) as caught:
            gone._get_json("/health")  # pyright: ignore[reportPrivateUsage]
    finally:
        gone.close()
    err = caught.value
    assert err.status == 0 and err.error == "unreachable" and "cannot reach" in err.message
    assert isinstance(err.__cause__, httpx2.ConnectError)
    # both families catch it: the client's own error type and the transport error
    assert isinstance(err, ApiError) and isinstance(err, httpx2.TransportError)


def test_a_timeout_is_api_unavailable_and_is_not_retried() -> None:
    def slow(request: httpx2.Request, n: int) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow")

    api, seen = client_for(slow)
    with pytest.raises(ApiUnavailableError) as caught:
        api._get_json("/records")  # pyright: ignore[reportPrivateUsage]
    assert isinstance(caught.value.__cause__, httpx2.ReadTimeout) and len(seen) == 1


def test_a_get_is_sent_once_more_when_a_reused_connection_was_reset() -> None:
    def flaky(request: httpx2.Request, n: int) -> httpx2.Response:
        if n == 1:
            raise httpx2.RemoteProtocolError("server disconnected")
        return httpx2.Response(200, json={"ok": True})

    api, seen = client_for(flaky)
    assert api._get_json("/health") == {"ok": True}  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2


def test_a_get_that_fails_twice_is_api_unavailable() -> None:
    def broken(request: httpx2.Request, n: int) -> httpx2.Response:
        raise httpx2.ReadError("reset")

    api, seen = client_for(broken)
    with pytest.raises(ApiUnavailableError):
        api._get_json("/health")  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2


def test_a_write_is_never_sent_twice() -> None:
    def broken(request: httpx2.Request, n: int) -> httpx2.Response:
        raise httpx2.ReadError("reset")

    api, seen = client_for(broken)
    with pytest.raises(ApiUnavailableError):
        api._post_json("/commands/CreateRecord", {})  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ApiUnavailableError):
        api._send("PUT", "/uploads/x/content", content=b"x")  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2  # one attempt each


def test_a_dot_segment_is_refused_and_everything_else_is_escaped() -> None:
    for bad in (".", ".."):
        with pytest.raises(ValueError, match="cannot be used as an id"):
            quote(bad)
    assert quote("a.b") == "a.b" and quote("..x") == "..x" and quote("x..") == "x.."
    assert quote("../health") == "..%2Fhealth"
    assert quote("a b/c?d#e") == "a%20b%2Fc%3Fd%23e"
    assert quote("01J8XK") == "01J8XK"


def test_a_command_is_sent_without_actor_and_with_its_source() -> None:
    def echo(request: httpx2.Request, n: int) -> httpx2.Response:
        body = json.loads(request.content)
        assert "actor" not in body and body["source"] == "tui"
        assert request.url.path == "/commands/CreateRecord"
        assert request.headers["authorization"] == "Bearer t"
        return httpx2.Response(
            200, json={"stream_id": "S", "key": body["key"], "version": 1, "events": []}
        )

    api, _ = client_for(echo)
    cmd = CreateRecord(
        actor="user:me",
        source="tui",
        scope="project:P1",
        record_type="core.Record",
        title="T",
        key="K-1",
    )
    assert api._command("CreateRecord", cmd).key == "K-1"  # pyright: ignore[reportPrivateUsage]


def test_error_bodies_become_the_embedded_exceptions_and_others_become_api_error() -> None:
    from tl_core.services.errors import RecordNotFoundError

    def answer(request: httpx2.Request, n: int) -> httpx2.Response:
        if request.url.path == "/missing":
            return httpx2.Response(
                404, json={"error": "record_not_found", "message": "no record 'x'"}
            )
        if request.url.path == "/html":
            return httpx2.Response(502, text="<html>bad gateway</html>")
        return httpx2.Response(418, json={"error": "teapot", "message": "short"})

    api, _ = client_for(answer)
    with pytest.raises(RecordNotFoundError, match="no record 'x'"):
        api._get_json("/missing")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ApiError) as html:
        api._get_json("/html")  # pyright: ignore[reportPrivateUsage]
    assert html.value.status == 502 and "bad gateway" in html.value.message
    with pytest.raises(ApiError) as teapot:
        api._get_json("/teapot")  # pyright: ignore[reportPrivateUsage]
    assert teapot.value.error == "teapot"
