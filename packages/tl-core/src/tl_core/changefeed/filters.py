"""Subscription filters for the change feed (brief 5.3, 18.2).

A filter selects events by scope, event type (exact name or glob) and record id. The same filter
object is used by the in-process registry, the poller, the paged ``/events`` read and, later,
webhook subscriptions. A field left as ``None`` matches everything; an empty collection is a
mistake (it would match nothing) and raises ``ValueError``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fnmatch import translate
from functools import lru_cache

from tl_core.auth.projector import ACCOUNT_STREAM_TYPE
from tl_core.ledger import Event

#: Streams no default filter lets through.
INTERNAL_STREAM_TYPES: frozenset[str] = frozenset({ACCOUNT_STREAM_TYPE})

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
    #: Streams whose events this subscriber must never see. **Fail closed:** the default hides
    #: the account streams (usernames, roles; ADR-0009), so a consumer that builds a filter without
    #: thinking about it (the embedded TUI, ``tl events``, the registry) never shows them. A caller
    #: that holds an admin principal passes ``hide_stream_types=()``.
    hide_stream_types: frozenset[str] = INTERNAL_STREAM_TYPES
    #: An extra test the API adds for the caller (record visibility of thread events, P1-I7). It
    #: runs last and **fails closed**: an exception counts as "not visible".
    visible: Callable[[Event], bool] | None = None

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
        hide_stream_types: Iterable[str] | None = None,
        visible: Callable[[Event], bool] | None = None,
    ) -> SubscriptionFilter:
        """Build a filter from any iterables (a list of types, a set of ids)."""
        return SubscriptionFilter(
            scope,
            None if event_types is None else tuple(event_types),
            None if record_ids is None else frozenset(record_ids),
            INTERNAL_STREAM_TYPES if hide_stream_types is None else frozenset(hide_stream_types),
            visible,
        )

    def matches(self, event: Event) -> bool:
        """Whether ``event`` passes every part of the filter that is set."""
        if not self._matches(event):
            return False
        if self.visible is None:
            return True
        try:
            return bool(self.visible(event))
        except Exception:  # noqa: BLE001 - fail closed: what cannot be checked is not shown
            return False

    def _matches(self, event: Event) -> bool:
        if event.stream_type in self.hide_stream_types:
            return False
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


ANY = SubscriptionFilter()  # hides the internal streams like every default filter
