"""Paged, filtered reads of the event log for clients that resume by ``seq`` (brief 5.3).

``GET /events?after=`` and a reconnecting SSE client use :func:`fetch_changes`: it returns the
matching events after a cursor together with the cursor to continue from. The cursor also moves
past events the filter rejected, so a selective filter never makes a client re-scan the same
stretch of the log.

STUB (P0-I4-T01): the names, signatures and docstrings are final; the body of
``fetch_changes`` is the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from dataclasses import dataclass

from tl_core.changefeed.filters import SubscriptionFilter
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
    raise NotImplementedError
