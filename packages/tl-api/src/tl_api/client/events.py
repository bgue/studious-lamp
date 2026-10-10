"""The change feed over HTTP: paged pull and an SSE stream that reconnects by itself (T48).

``stream_events`` yields ``Event`` objects in ``seq`` order, once each. When the connection drops
it reconnects with ``Last-Event-ID`` set to the last ``seq`` it yielded, after a short growing
pause, so a consumer that just loops over it misses nothing and sees nothing twice.
"""

from __future__ import annotations

import time
from collections.abc import Generator, Iterator, Sequence

import httpx2
from tl_core.ledger import Event

from tl_api.client.base import ApiClientBase
from tl_api.models import EventPage

RECONNECT_FIRST_S = 0.25
RECONNECT_MAX_S = 5.0


class EventsApi(ApiClientBase):
    def events_after(
        self,
        after: int = 0,
        *,
        scope: str | None = None,
        types: Sequence[str] | None = None,
        record_ids: Sequence[str] | None = None,
        limit: int = 500,
    ) -> EventPage:
        """One page of events with ``seq`` greater than ``after`` (``GET /events``)."""
        data = self._get_json(
            "/events",
            {
                "after": after,
                "scope": scope,
                "type": list(types) if types else None,
                "record_id": list(record_ids) if record_ids else None,
                "limit": limit,
            },
        )
        return self._model(EventPage, data)

    def stream_events(
        self,
        *,
        after: int | None = None,
        scope: str | None = None,
        types: Sequence[str] | None = None,
        record_ids: Sequence[str] | None = None,
        reconnect: bool = True,
    ) -> Generator[Event]:
        """Events from ``GET /stream``. ``after=None`` is live only; ``after=n`` replays first.

        Blocks while idle (keep-alive comments are skipped). Stops, raising nothing, when the
        generator is closed; with ``reconnect=False`` it also stops when the connection ends.
        An error response (401, 503 ...) raises its mapped exception.
        """
        last = after
        pause = RECONNECT_FIRST_S
        while True:
            headers = dict(self._auth)
            if last is not None:
                headers["Last-Event-ID"] = str(last)
            params = {
                "scope": scope,
                "type": list(types) if types else None,
                "record_id": list(record_ids) if record_ids else None,
            }
            params = {k: v for k, v in params.items() if v is not None}
            try:
                with self._http.stream(
                    "GET",
                    "/stream",
                    params=params,
                    headers=headers,
                    timeout=httpx2.Timeout(10.0, read=None),
                ) as response:
                    if response.status_code >= 400:
                        response.read()
                        raise self.error_from(response)
                    pause = RECONNECT_FIRST_S
                    for event in parse_stream(response.iter_lines()):
                        if last is not None and event.seq <= last:
                            continue
                        last = event.seq
                        yield event
            except httpx2.TransportError:
                if not reconnect:
                    raise
            if not reconnect:
                return
            time.sleep(pause)
            pause = min(pause * 2, RECONNECT_MAX_S)


def parse_stream(lines: Iterator[str]) -> Iterator[Event]:
    """Events from the lines of an SSE body: ``data:`` fields are joined, comments are skipped."""
    data: list[str] = []
    for line in lines:
        if line == "":
            if data:
                yield Event.model_validate_json("\n".join(data))
                data = []
        elif line.startswith("data:"):
            value = line[len("data:") :]
            data.append(value[1:] if value.startswith(" ") else value)
