"""HTTP client: the event feed, paged and streamed (P0-I4-T48)."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import httpx2
import pytest
from harness import SCOPE, Harness
from tl_api.client import ApiClient
from tl_api.client import events as events_module
from tl_api.client.events import parse_stream
from tl_api.errors import ApiError
from tl_core.ledger import Event


def collect(stream: Iterator[Event], count: int, timeout: float = 10.0) -> list[Event]:
    """Take ``count`` events from a stream that may block; fail instead of hanging."""
    got: list[Event] = []
    done = threading.Event()

    def run() -> None:
        for event in stream:
            got.append(event)
            if len(got) == count:
                break
        done.set()

    threading.Thread(target=run, daemon=True).start()
    assert done.wait(timeout), f"expected {count} events, got {[e.seq for e in got]}"
    return got


def test_events_after_pages_and_filters(harness: Harness) -> None:
    for n in range(4):
        harness.create_record(f"K-{n}")
    harness.create_record("OTHER", scope="project:P999")
    api = harness.api()
    page = api.events_after(0, limit=3)
    assert [e.seq for e in page.events] == [1, 2, 3] and page.has_more
    rest = api.events_after(page.next_seq)
    assert [e.seq for e in rest.events] == [4, 5] and not rest.has_more
    only = api.events_after(0, scope=SCOPE)
    assert [e.payload["key"] for e in only.events] == ["K-0", "K-1", "K-2", "K-3"]
    assert api.events_after(0, types=["Link.*"]).events == []
    assert [e.seq for e in api.events_after(0, types=["*.Created"], limit=2).events] == [1, 2]
    one = api.events_after(0, record_ids=[only.events[1].stream_id])
    assert [e.seq for e in one.events] == [2]


def test_stream_events_replays_then_goes_live(harness: Harness) -> None:
    harness.create_record("OLD-1")
    harness.create_record("OLD-2")
    with harness.live_api() as api:
        stream = api.stream_events(after=0)
        first_two = collect(stream, 2)
        assert [e.payload["key"] for e in first_two] == ["OLD-1", "OLD-2"]
        harness.create_record("LIVE-1")
        (live,) = collect(stream, 1)
        assert live.seq == 3 and live.payload["key"] == "LIVE-1"
        stream.close()


def test_stream_events_without_a_cursor_is_live_only(harness: Harness) -> None:
    harness.create_record("OLD")
    with harness.live_api() as api:
        stream = api.stream_events()
        threading.Timer(0.5, lambda: harness.create_record("NEW")).start()
        (event,) = collect(stream, 1)
        assert event.payload["key"] == "NEW"
        stream.close()


def test_stream_filters_apply(harness: Harness) -> None:
    harness.create_record("P1-OLD")
    harness.create_record("P9-OLD", scope="project:P9")
    with harness.live_api() as api:
        stream = api.stream_events(after=0, scope="project:P9")
        (event,) = collect(stream, 1)
        assert event.payload["key"] == "P9-OLD"
        stream.close()


def test_a_refused_stream_raises_the_mapped_error() -> None:
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(401, json={"error": "unauthorized", "message": "no"})
    )
    client = ApiClient(
        "http://x", "t", http=httpx2.Client(transport=transport, base_url="http://x")
    )
    with pytest.raises(ApiError) as caught:
        next(client.stream_events())
    assert caught.value.status == 401


def sse(*seqs: int) -> bytes:
    lines = []
    for seq in seqs:
        event = {
            "event_type": "Record.Created",
            "payload": {"n": seq},
            "seq": seq,
            "event_id": f"E{seq}",
            "stream_id": "S",
            "stream_type": "core.Record",
            "stream_version": seq,
            "scope": SCOPE,
            "actor": "user:a",
            "recorded_at": "2026-10-10T00:00:00Z",
            "effective_at": "2026-10-10T00:00:00Z",
            "correlation_id": "c",
            "causation_id": None,
            "source": "test",
            "prev_hash": None,
            "hash": "h",
        }
        import json

        lines.append(f"id: {seq}\nevent: Record.Created\ndata: {json.dumps(event)}\n\n")
    return (": connected\n\n" + "".join(lines) + ": keep-alive\n\n").encode()


def test_a_dropped_connection_is_resumed_from_the_last_seq_without_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(events_module, "RECONNECT_FIRST_S", 0.0)
    seen_headers: list[str | None] = []
    bodies = [sse(1, 2), sse(2, 3, 4)]  # the second answer overlaps by one event

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen_headers.append(request.headers.get("last-event-id"))
        return httpx2.Response(
            200, content=bodies.pop(0), headers={"content-type": "text/event-stream"}
        )

    client = ApiClient(
        "http://x",
        "t",
        http=httpx2.Client(transport=httpx2.MockTransport(handler), base_url="http://x"),
    )
    stream = client.stream_events(after=0)
    got = collect(stream, 4)
    stream.close()
    assert [e.seq for e in got] == [1, 2, 3, 4]
    assert seen_headers == ["0", "2"]  # the resume point is the last seq yielded


def test_without_reconnect_the_stream_ends_with_the_connection() -> None:
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200, content=sse(1, 2)))
    client = ApiClient(
        "http://x", "t", http=httpx2.Client(transport=transport, base_url="http://x")
    )
    assert [e.seq for e in client.stream_events(reconnect=False)] == [1, 2]


def test_parse_stream_joins_data_lines_and_skips_comments() -> None:
    event = sse(7).decode().splitlines()
    assert [e.seq for e in parse_stream(iter(event))] == [7]
    assert list(parse_stream(iter([": hello", "", "retry: 1000", ""]))) == []
