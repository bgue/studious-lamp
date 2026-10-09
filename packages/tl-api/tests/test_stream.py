"""``GET /stream``: server-sent events over a real server (httpx streaming, short timeouts)."""

from __future__ import annotations

import sys
import time
from collections.abc import AsyncIterator, Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

import httpx2
import pytest
from harness import ALICE, BOB, SCOPE, Harness, LiveServer
from tl_adapters.sqlite.uow import open_uow
from tl_api.app import create_app
from tl_api.tokens import TokenStore
from tl_core.ledger import NewEvent

TIMEOUT = httpx2.Timeout(5.0, read=5.0)


class Reader:
    """Reads SSE messages from a streaming response."""

    def __init__(self, response: httpx2.Response) -> None:
        self._lines = response.iter_lines()
        self.comments: list[str] = []

    def message(self) -> dict[str, str]:
        """The next message (skipping comment lines, which are kept in ``comments``)."""
        fields: dict[str, str] = {}
        for line in self._lines:
            if line == "":
                if fields:
                    return fields
                continue
            if line.startswith(":"):
                self.comments.append(line)
                continue
            name, _, value = line.partition(": ")
            fields[name] = value
        raise AssertionError("the stream ended")

    def seqs(self, count: int) -> list[int]:
        return [int(self.message()["id"]) for _ in range(count)]


@contextmanager
def open_stream(
    server: LiveServer, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> Iterator[Reader]:
    with httpx2.Client(base_url=server.base_url, timeout=TIMEOUT) as client:
        sent = {"Authorization": f"Bearer {server.token}", **(headers or {})}
        with client.stream("GET", "/stream", params=params, headers=sent) as response:
            assert response.status_code == 200, response.read()
            assert response.headers["content-type"].startswith("text/event-stream")
            yield Reader(response)


def write_elsewhere(h: Harness, key: str) -> None:
    """A write from 'another process': a new engine, no bus, no shared state with the app."""
    with open_uow(h.db) as uow:
        uow.append(
            stream_id=f"R-{key}",
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": "core.Record", "key": key, "title": key, "psets": {}},
                )
            ],
            actor="user:other",
            source="test",
            correlation_id="c",
        )


def test_an_in_process_write_reaches_the_stream(harness: Harness) -> None:
    with harness.live() as server, open_stream(server) as stream:
        made = harness.create_record("LIVE-1")
        message = stream.message()
    assert message["id"] == "1" and message["event"] == "Record.Created"
    import json

    event = json.loads(message["data"])
    assert event["stream_id"] == made.stream_id and event["seq"] == 1


def test_a_write_from_another_process_reaches_the_stream_through_the_poller(
    harness: Harness,
) -> None:
    with harness.live() as server, open_stream(server) as stream:
        started = time.monotonic()
        write_elsewhere(harness, "OTHER-1")
        assert stream.seqs(1) == [1]
    assert time.monotonic() - started < 2.0  # the demo promise


def test_last_event_id_resumes_without_a_gap_or_a_repeat(harness: Harness) -> None:
    for n in range(3):
        harness.create_record(f"OLD-{n}")
    with harness.live() as server, open_stream(server, headers={"Last-Event-ID": "1"}) as stream:
        assert stream.seqs(2) == [2, 3]  # replayed
        harness.create_record("NEW-1")
        write_elsewhere(harness, "NEW-2")
        assert stream.seqs(2) == [4, 5]  # live, once each, in order


def test_the_after_parameter_resumes_like_the_header(harness: Harness) -> None:
    for n in range(3):
        harness.create_record(f"OLD-{n}")
    with harness.live() as server, open_stream(server, {"after": 2}) as stream:
        assert stream.seqs(1) == [3]


def test_a_long_backlog_is_replayed_in_pages(harness: Harness) -> None:
    from tl_api import feed

    total = feed.CATCH_UP_PAGE * 2 + 5
    with harness.backend(False) as uow:
        for n in range(total):
            uow.append(
                stream_id=f"B-{n}",
                stream_type="core.Record",
                scope=SCOPE,
                expected_version=0,
                events=[
                    NewEvent(
                        event_type="Record.Created",
                        payload={"record_type": "core.Record", "key": f"B-{n}", "title": "t"},
                    )
                ],
                actor="user:t",
                source="test",
                correlation_id="c",
            )
    with harness.live() as server, open_stream(server, {"after": 0}) as stream:
        assert stream.seqs(total) == list(range(1, total + 1))


def test_filters_apply_to_the_replay_and_the_live_part(harness: Harness) -> None:
    harness.create_record("P1-OLD")
    harness.create_record("P9-OLD", scope="project:P9")
    with (
        harness.live() as server,
        open_stream(server, {"after": 0, "scope": "project:P9"}) as stream,
    ):
        assert stream.seqs(1) == [2]
        harness.create_record("P1-NEW")
        harness.create_record("P9-NEW", scope="project:P9")
        assert stream.seqs(1) == [4]


def test_an_idle_stream_sends_keep_alive_comments(harness: Harness) -> None:
    harness.app.state.ctx.feed.wait_s = 0.1
    with harness.live() as server, open_stream(server) as stream:
        time.sleep(1.0)  # idle for longer than the keep-alive period
        harness.create_record("WAKE")  # one message so the reader returns after the comments
        stream.message()
    assert any("keep-alive" in c for c in stream.comments)


def test_a_stream_needs_a_token_and_a_valid_cursor(harness: Harness) -> None:
    with harness.live() as server, httpx2.Client(base_url=server.base_url, timeout=TIMEOUT) as c:
        assert c.get("/stream").status_code == 401
        bad = c.get(
            "/stream",
            headers={"Authorization": f"Bearer {server.token}", "Last-Event-ID": "abc"},
        )
        assert bad.status_code == 422 and bad.json()["error"] == "invalid_argument"
        negative = c.get("/stream", params={"after": -1}, headers=harness.headers(ALICE))
        assert negative.status_code == 422


def test_too_many_streams_are_refused_and_a_closed_stream_frees_its_slot(
    harness: Harness,
) -> None:
    app = create_app(
        harness.backend,
        settings=replace(harness.settings, max_streams=1, sse_wait_s=0.1),
        tokens=TokenStore(harness.settings.tokens_path),
    )
    other = Harness(**{**harness.__dict__, "app": app})
    with other.live(BOB) as server:
        with open_stream(server):
            with httpx2.Client(base_url=server.base_url, timeout=TIMEOUT) as c:
                refused = c.get("/stream", headers={"Authorization": f"Bearer {server.token}"})
            assert refused.status_code == 503 and refused.json()["error"] == "unavailable"
        feed = app.state.ctx.feed
        deadline = time.monotonic() + 5
        while feed.open_streams and time.monotonic() < deadline:
            time.sleep(0.05)
        assert feed.open_streams == 0


@pytest.mark.skipif(sys.platform == "win32", reason="loopback sockets only")
def test_the_stream_is_cut_off_cleanly_when_the_server_stops(harness: Harness) -> None:
    with harness.live() as server, open_stream(server):
        pass  # leaving both blocks must not hang


def test_a_client_that_hangs_up_before_the_first_chunk_frees_its_slot(harness: Harness) -> None:
    """End to end smoke test. Depending on timing the server may drop the connection before the
    route runs, so the guarantee itself is the deterministic test below (a response whose body
    never starts still releases its slot)."""
    import socket

    feed = harness.app.state.ctx.feed
    with harness.live() as server:
        port = int(server.base_url.rsplit(":", 1)[1])
        for _ in range(5):
            sock = socket.create_connection(("127.0.0.1", port), timeout=5)
            request = (
                f"GET /stream HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {server.token}\r\n\r\n"
            )
            sock.sendall(request.encode())
            sock.close()  # gone before the server wrote anything
        deadline = time.monotonic() + 5
        while feed.open_streams and time.monotonic() < deadline:
            time.sleep(0.05)
        assert feed.open_streams == 0


def test_the_slot_is_released_even_when_the_response_never_starts() -> None:
    import asyncio

    from starlette.requests import ClientDisconnect
    from tl_api.routes.events import SlotResponse

    released: list[int] = []

    async def unused() -> AsyncIterator[str]:
        yield "never iterated"

    async def receive() -> dict[str, str]:
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        raise OSError("client is gone")

    async def run() -> None:
        response = SlotResponse(unused(), lambda: released.append(1), media_type="text/plain")
        scope = {"type": "http", "asgi": {"spec_version": "2.4"}, "method": "GET", "headers": []}
        with pytest.raises(ClientDisconnect):
            await response(scope, receive, send)

    asyncio.run(run())
    assert released == [1]
