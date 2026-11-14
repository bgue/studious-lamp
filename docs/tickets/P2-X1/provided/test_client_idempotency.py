"""P2-X1-T02: the client sends a key on POST /commands/ and retries once with the same key."""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest
from tl_api.client import ApiClient
from tl_api.client.base import ApiUnavailableError
from tl_api.errors import ApiError
from tl_core.services.commands import CreateRecord

OK = {"stream_id": "S", "key": "REC-1", "version": 1, "events": []}


def client_for(handler: Any) -> tuple[ApiClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def wrapped(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request, len(seen))

    http = httpx2.Client(transport=httpx2.MockTransport(wrapped), base_url="http://x")
    return ApiClient("http://x", "t", http=http), seen


def command(**extra: Any) -> CreateRecord:
    return CreateRecord(
        actor="user:amy",
        source="tui",
        scope="project:P1",
        record_type="core.Record",
        title="t",
        **extra,
    )


def key_of(request: httpx2.Request) -> str | None:
    return json.loads(request.content).get("idempotency_key")


def test_a_command_without_a_key_is_sent_with_a_generated_one() -> None:
    api, seen = client_for(lambda r, n: httpx2.Response(200, json=OK))
    api._command("create_record", command())  # pyright: ignore[reportPrivateUsage]
    key = key_of(seen[0])
    assert key is not None and 1 <= len(key) <= 128 and key.isascii() and key.isprintable()
    assert " " not in key


def test_two_commands_get_two_different_keys() -> None:
    api, seen = client_for(lambda r, n: httpx2.Response(200, json=OK))
    api._command("create_record", command())  # pyright: ignore[reportPrivateUsage]
    api._command("create_record", command())  # pyright: ignore[reportPrivateUsage]
    assert key_of(seen[0]) != key_of(seen[1])


def test_a_caller_key_is_kept() -> None:
    api, seen = client_for(lambda r, n: httpx2.Response(200, json=OK))
    api._command("create_record", command(idempotency_key="mine-1"))  # pyright: ignore[reportPrivateUsage]
    assert key_of(seen[0]) == "mine-1"


@pytest.mark.parametrize(
    "failure",
    [httpx2.ReadTimeout("slow"), httpx2.RemoteProtocolError("reset"), httpx2.ReadError("reset")],
)
def test_a_reset_or_timeout_is_retried_once_with_the_same_key(failure: Exception) -> None:
    def flaky(request: httpx2.Request, n: int) -> httpx2.Response:
        if n == 1:
            raise failure
        return httpx2.Response(200, json=OK)

    api, seen = client_for(flaky)
    api._command("create_record", command())  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2 and key_of(seen[0]) == key_of(seen[1]) is not None


def test_a_caller_key_is_reused_on_the_retry() -> None:
    def flaky(request: httpx2.Request, n: int) -> httpx2.Response:
        if n == 1:
            raise httpx2.ReadTimeout("slow")
        return httpx2.Response(200, json=OK)

    api, seen = client_for(flaky)
    api._command("create_record", command(idempotency_key="mine-2"))  # pyright: ignore[reportPrivateUsage]
    assert [key_of(r) for r in seen] == ["mine-2", "mine-2"]


def test_two_failures_are_api_unavailable_after_exactly_two_sends() -> None:
    def broken(request: httpx2.Request, n: int) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow")

    api, seen = client_for(broken)
    with pytest.raises(ApiUnavailableError):
        api._command("create_record", command())  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2


def test_an_error_answer_is_not_retried() -> None:
    body = {"error": "teapot", "message": "short"}
    api, seen = client_for(lambda r, n: httpx2.Response(418, json=body))
    with pytest.raises(ApiError):
        api._command("create_record", command())  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 1


def test_other_posts_and_gets_are_unchanged() -> None:
    def slow(request: httpx2.Request, n: int) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow")

    api, seen = client_for(slow)
    with pytest.raises(ApiUnavailableError):
        api._post_json("/links", {"a": 1})  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 1 and b"idempotency_key" not in seen[0].content
