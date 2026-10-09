"""Paged, filtered reads of the event log for clients that resume by ``seq`` (brief 5.3).

``GET /events?after=`` and a reconnecting SSE client use :func:`fetch_changes`: it returns the
matching events after a cursor together with the cursor to continue from. The cursor also moves
past events the filter rejected, so a selective filter never makes a client re-scan the same
stretch of the log.
"""

from __future__ import annotations

from dataclasses import dataclass

from tl_core.changefeed.filters import ANY, SubscriptionFilter
from tl_core.ledger import Event, Ledger

DEFAULT_LIMIT = 500
PAGE = 500  # rows read from the ledger per query
MAX_SCAN_PAGES = 20  # ledger pages examined per call; bounds the work for a very selective filter


@dataclass(frozen=True)
class ChangePage:
    """One page of matching events, in ascending ``seq`` order."""

    events: list[Event]
    next_seq: int  # pass as ``after_seq`` to get the next page; never less than ``after_seq``
    has_more: bool  # True when more events may follow (limit or scan cap reached)


def fetch_changes(
    ledger: Ledger,
    *,
    after_seq: int = 0,
    flt: SubscriptionFilter | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ChangePage:
    """The next ``limit`` events after ``after_seq`` that match ``flt`` (all events when ``None``).

    The ledger is read ``PAGE`` rows at a time (``flt.scope`` is passed down to ``read_after``)
    and each event is tested with ``flt.matches``. At most ``MAX_SCAN_PAGES`` pages are read per
    call. Raises ``ValueError`` when ``limit`` is below 1 or ``after_seq`` is negative.
    """
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    if after_seq < 0:
        raise ValueError(f"after_seq must not be negative, got {after_seq}")
    active = ANY if flt is None else flt
    events: list[Event] = []
    cursor = after_seq
    for _ in range(MAX_SCAN_PAGES):
        page = ledger.read_after(cursor, scope=active.scope, limit=PAGE)
        for event in page:
            if active.matches(event):
                if len(events) == limit:
                    # The extra event is not consumed; the next call finds it again.
                    return ChangePage(events, events[-1].seq, True)
                events.append(event)
            cursor = event.seq
        if len(page) < PAGE:
            return ChangePage(events, cursor, False)
    return ChangePage(events, cursor, True)
