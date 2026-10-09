"""``GET /events`` (pull, paged by ``seq``) and ``GET /stream`` (push, SSE) (brief 11.1, 18.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.types import Receive, Send
from starlette.types import Scope as AsgiScope
from tl_core.changefeed import SubscriptionFilter, fetch_changes
from tl_core.ledger import Event

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError

router = APIRouter(tags=["events"])


class SlotResponse(StreamingResponse):
    """A streaming response that gives its stream slot back when the response is over.

    The slot is released here, not in the generator: a client that disconnects before the first
    chunk may leave the generator unstarted, and an unstarted generator never runs its ``finally``.
    """

    def __init__(self, content: AsyncIterator[str], release: Callable[[], None], **kw: Any) -> None:
        super().__init__(content, **kw)
        self._release = release

    async def __call__(self, scope: AsgiScope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._release()


Ctx = Annotated[ApiContext, Depends(get_ctx)]
Scope = Annotated[str | None, Query(description="Only this scope: `company` or `project:<id>`.")]
Types = Annotated[
    list[str] | None,
    Query(alias="type", description="Event type or glob (`Record.*`, `*.Created`); repeatable."),
]
RecordIds = Annotated[
    list[str] | None, Query(description="Only events of these records (and links to them).")
]


class EventPage(BaseModel):
    events: list[Event]
    next_seq: int  # pass as `after` to get the next page; never less than `after`
    has_more: bool


def build_filter(
    scope: str | None, types: list[str] | None, record_ids: list[str] | None
) -> SubscriptionFilter:
    return SubscriptionFilter.of(
        scope=scope or None,
        event_types=types or None,
        record_ids=record_ids or None,
    )


@router.get("/events", operation_id="list_events")
def list_events(
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("events.read"))],
    after: Annotated[int, Query(ge=0, description="Return events with a greater `seq`.")] = 0,
    scope: Scope = None,
    types: Types = None,
    record_id: RecordIds = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> EventPage:
    """The next events after `after`, oldest first, with the cursor to continue from."""
    page = fetch_changes(
        ctx.backend.ledger,
        after_seq=after,
        flt=build_filter(scope, types, record_id),
        limit=limit,
    )
    return EventPage(events=page.events, next_seq=page.next_seq, has_more=page.has_more)


@router.get(
    "/stream",
    operation_id="stream_events",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
        503: {"description": "Too many open streams."},
    },
)
async def stream_events(
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("events.stream"))],
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID", description="Resume after this `seq` (set by reconnects)."),
    ] = None,
    after: Annotated[int | None, Query(ge=0, description="Resume after this `seq`.")] = None,
    scope: Scope = None,
    types: Types = None,
    record_id: RecordIds = None,
) -> StreamingResponse:
    """Server-sent events: `id` is the ledger `seq`, `event` the event type, `data` the Event.

    Without `Last-Event-ID` or `after` the stream is live only. With one it first replays the
    ledger after that `seq`, then continues live without a gap.
    """
    cursor = after
    if last_event_id is not None and last_event_id.strip():
        try:
            cursor = int(last_event_id)
        except ValueError as exc:
            raise ApiError(
                422, "invalid_argument", "Last-Event-ID must be a ledger seq (an integer)"
            ) from exc
        if cursor < 0:
            raise ApiError(422, "invalid_argument", "Last-Event-ID must not be negative")
    flt = build_filter(scope, types, record_id)
    if not ctx.feed.try_open_stream():
        raise ApiError(503, "unavailable", "too many open event streams; try again later")
    return SlotResponse(
        ctx.feed.stream(flt, cursor),
        ctx.feed.release_stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
