"""Subscription filters for the change feed (brief 5.3, 18.2).

A filter selects events by scope, event type (exact name or glob) and record id. The same filter
object is used by the in-process registry, the poller, the paged ``/events`` read and, later,
webhook subscriptions. A field left as ``None`` matches everything; an empty collection is a
mistake (it would match nothing) and raises ``ValueError``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import translate
from functools import lru_cache

from tl_core.ledger import Event

#: Payload keys through which a link event refers to the records at its two ends.
LINK_END_KEYS = ("from_ref", "to_ref")


@lru_cache(maxsize=512)
def _glob(pattern: str) -> re.Pattern[str]:
    return re.compile(translate(pattern))


def glob_match(pattern: str, text: str) -> bool:
    """Whether ``text`` matches the glob ``pattern`` (``*``, ``?``, ``[...]``), case-sensitive.

    The one glob used by every subscription filter, here and in ``tl_core.webhooks.filters``.
    """
    return _glob(pattern).match(text) is not None


@dataclass(frozen=True)
class SubscriptionFilter:
    """Which events a subscriber wants.

    ``scope``: exactly ``company`` or ``project:<id>``. ``event_types``: exact names or globs
    (``Record.*``, ``*.Created``, ``Link.Added``), case-sensitive. ``record_ids``: ids of records;
    an event matches when its stream is one of them, or, for a link event, when either end of the
    link (payload ``from_ref`` / ``to_ref``) is one of them, so a record's view hears about its
    links.
    """

    scope: str | None = None
    event_types: tuple[str, ...] | None = None
    record_ids: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.event_types is not None and not self.event_types:
            raise ValueError("event_types must not be empty; use None for every event type")
        if self.record_ids is not None and not self.record_ids:
            raise ValueError("record_ids must not be empty; use None for every record")

    @staticmethod
    def of(
        *,
        scope: str | None = None,
        event_types: Iterable[str] | None = None,
        record_ids: Iterable[str] | None = None,
    ) -> SubscriptionFilter:
        """Build a filter from any iterables (a list of types, a set of ids)."""
        return SubscriptionFilter(
            scope,
            None if event_types is None else tuple(event_types),
            None if record_ids is None else frozenset(record_ids),
        )

    def matches(self, event: Event) -> bool:
        """Whether ``event`` passes every part of the filter that is set."""
        if self.scope is not None and event.scope != self.scope:
            return False
        if self.event_types is not None and not any(
            glob_match(pattern, event.event_type) for pattern in self.event_types
        ):
            return False
        if self.record_ids is not None:
            if event.stream_id in self.record_ids:
                return True
            ends = (event.payload.get(key) for key in LINK_END_KEYS)
            return any(isinstance(end, str) and end in self.record_ids for end in ends)
        return True


ANY = SubscriptionFilter()
