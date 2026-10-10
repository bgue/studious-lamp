"""``SimReader``: what ``sim_assert`` reads, and the HTTP implementation of it.

The reader returns plain dicts from the public API: the record envelopes (``cur_core_record``),
each record's links (``cur_links``), the feed's posts (``cur_feed_items``), the event pager
(``events``) and the proposal review queue. It never touches the database.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from tl_api.client import ApiClient

PAGE = 500  # the event pager's limit
FEED_PAGE = 200  # the feed route's limit (GET /feed answers 422 above it)


class SimReader(Protocol):
    def records(self) -> list[dict[str, Any]]:
        """Every record envelope of the run's scope."""
        ...

    def links(self, record_id: str) -> list[dict[str, Any]]:
        """The record's links in both directions: ``direction, relation, other_key, status``."""
        ...

    def posts(self) -> list[dict[str, Any]]:
        """Every post of the scope: ``actor, body, retracted``."""
        ...

    def events(self) -> list[dict[str, Any]]:
        """Every event of the scope: ``stream_id, event_type, actor, source, payload``, times."""
        ...

    def proposals(self) -> list[dict[str, Any]]:
        """Every proposal of the scope: ``agent, tool, status``."""
        ...


class FeedApi(Protocol):
    """The feed read of ``ApiClient`` (``ClientInterface.feed_page``)."""

    def feed_page(
        self, scope: str, *, item_type: Any = None, limit: int = 50, before_seq: int | None = None
    ) -> Any:
        """A ``FeedPage``: ``items`` (``actor``, ``summary``, ``retracted``) and ``next_before``."""
        ...


class HttpReader:
    """Reads a run's scope with an ``ApiClient`` (any token: reads are allowed to every actor)."""

    def __init__(self, api: ApiClient, scope: str) -> None:
        self._api = api
        self._scope = scope

    def records(self) -> list[dict[str, Any]]:
        return self._api.list_records(self._scope, limit=5000)

    def links(self, record_id: str) -> list[dict[str, Any]]:
        return [v.model_dump(mode="json") for v in self._api.links_of(record_id)]

    def posts(self) -> list[dict[str, Any]]:
        feed = cast("FeedApi", self._api)  # ApiClient gains feed_page with workstream B
        posts: list[dict[str, Any]] = []
        before: int | None = None
        while True:
            page = feed.feed_page(self._scope, item_type="post", limit=FEED_PAGE, before_seq=before)
            posts += [
                {"actor": i.actor, "body": i.summary, "retracted": i.retracted} for i in page.items
            ]
            if page.next_before is None:
                return posts
            before = page.next_before

    def events(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        after = 0
        while True:
            page = self._api.events_after(after, scope=self._scope, limit=PAGE)
            out += [e.model_dump(mode="json") for e in page.events]
            if not page.has_more:
                return out
            after = page.next_seq

    def proposals(self) -> list[dict[str, Any]]:
        return []  # the review queue is read here once the proposals service is wired
