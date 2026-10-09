"""Read queries over the feed projection (brief 21.3): the feed lists and the result types.

Plain dataclasses only: clients (CLI, TUI, API) never write SQL. Every function reads in the
caller's transaction (usually a read-only unit of work).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tl_core.feed.types import FeedItem, TagKind
from tl_core.uow import UnitOfWork

CARD_SUBJECTS_SHOWN = 20  # record ids a card item lists, in the order the events touched them


@dataclass(frozen=True)
class FeedSuggestion:
    """A pending suggestion beside a post: ``#hold`` on a post that references a record offers a
    constraint (brief 21.2). It is derived from the post's tags, never stored, and accepting it is
    not built in Phase 0 (the review queue arrives with the MCP workstream)."""

    item_id: str  # the post
    kind: Literal["constraint"]
    record_id: str
    record_key: str | None
    prompt: str  # "Create a constraint on P123-REC-0042?"


@dataclass(frozen=True)
class FeedPage:
    """One page of a feed, newest first.

    ``labels`` maps every record id the items mention (``FeedItem.record_ids``) to the record's key,
    else its title, so a client can show ``jsmith created 3 records (P1-REC-0001 ...)``.
    ``suggestions`` maps a post id to its suggestions (filled by ``feed_suggestions``, not by
    ``list_feed``). ``next_before`` is the ``before_seq`` for the next page, or None at the end.
    """

    items: list[FeedItem]
    labels: dict[str, str] = field(default_factory=dict[str, str])
    suggestions: dict[str, list[FeedSuggestion]] = field(
        default_factory=dict[str, list[FeedSuggestion]]
    )
    next_before: int | None = None


@dataclass(frozen=True)
class Completion:
    """A candidate for the composer after ``#`` or ``@``. ``text`` has no sigil."""

    text: str
    kind: TagKind
    detail: str  # the record title, "signal tag", "used 3 times", "person", "agent"


def list_feed(
    uow: UnitOfWork,
    scope: str,
    *,
    record_id: str | None = None,
    include_linked: bool = False,
    tag: str | None = None,
    item_type: Literal["post", "card"] | None = None,
    limit: int = 50,
    before_seq: int | None = None,
) -> FeedPage:
    """Feed items of ``scope``, newest first (``occurred_at`` then ``seq``, both descending).

    Filters (all optional, combined with AND):

    * ``item_type``: only posts or only cards.
    * ``record_id``: items about that record (a post that tags it, a card whose events touched it).
      With ``include_linked``, also items about records one link away: links in status active,
      stale or broken, either direction, to a record (suggested and retracted links do not count).
    * ``tag``: a hashtag (``hold``, ``#hold``, ``area:A12``; case-insensitive; matches signal, code
      and topic tags, never mentions) or, with a leading ``@``, a mention (``@party:fab-a``).
    * ``before_seq``: only items with a smaller ``seq`` (the previous page's ``next_before``).

    Retracted posts are listed as tombstones (``retracted`` true, summary ``[retracted]``), except
    in a ``tag`` feed (their non-record tags are gone). ``labels`` maps each record id of the items
    to its key, else its title. ``suggestions`` stays empty (see ``feed_suggestions``).
    ``next_before`` is the last item's ``seq`` when more items follow, else None.

    STUB: replace this paragraph and the body (P0-I6-T02).
    """
    raise NotImplementedError


def get_post(uow: UnitOfWork, scope: str, post_id: str) -> FeedItem:
    """One post as a ``FeedItem`` (with its tags and reaction counts).

    Raises ``PostNotFoundError`` when no post has this id in ``scope``.

    STUB: replace this paragraph and the body (P0-I6-T02).
    """
    raise NotImplementedError
