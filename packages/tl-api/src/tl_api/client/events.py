"""The change feed over HTTP: paged pull and an SSE stream that reconnects by itself (T48).

STUB (P0-I4-T48): function bodies below raise ``NotImplementedError``. Names, signatures and
docstrings are final; implement the bodies, then delete this paragraph.

``stream_events`` yields ``Event`` objects in ``seq`` order, once each. When the connection drops
it reconnects with ``Last-Event-ID`` set to the last ``seq`` it yielded, after a short growing
pause, so a consumer that just loops over it misses nothing and sees nothing twice.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator, Sequence

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
        raise NotImplementedError("STUB (P0-I4-T48)")

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
        raise NotImplementedError("STUB (P0-I4-T48)")


def parse_stream(lines: Iterator[str]) -> Iterator[Event]:
    """Events from the lines of an SSE body: ``data:`` fields are joined, comments are skipped."""
    raise NotImplementedError("STUB (P0-I4-T48)")
