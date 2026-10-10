"""Feed contracts for P0-I6 (brief §21.1–§21.3, §19.2).

Frozen for the increment: change only by orchestrator decision.

Posts are ledger events on their own stream (stream_type ``core.ActivityPost``, stream id = post
id, scope = the project). Event cards are projection-only: rendered from ledger events, never
events themselves. Hashtags never mutate records (§21.2); a record-reference tag at most creates a
*suggested* ``references`` link.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# Event types on a core.ActivityPost stream. Payload classes live in schema/core/feed.yaml.
# Feed.Posted: {post_id, body, author, importance, tags: [ParsedTag as dict], record_ids}
FEED_POSTED = "Feed.Posted"
# Feed.Edited: {post_id, body, tags, record_ids}; a full replacement, history stays in the ledger
FEED_EDITED = "Feed.Edited"
# Feed.Retracted: {post_id, reason}; the projection keeps a tombstone row
FEED_RETRACTED = "Feed.Retracted"
# Feed.Reacted: {post_id, reaction: Reaction, on: bool}
FEED_REACTED = "Feed.Reacted"

TagKind = Literal["record", "code", "signal", "topic", "mention"]
Reaction = Literal["ack", "+1", "resolved"]
Importance = Literal["low", "normal", "high"]

# about:config default (§30 `feed.signal_tags`). Phase 0 reads this constant; settings arrive in
# P0-I8.
DEFAULT_SIGNAL_TAGS: tuple[str, ...] = ("safety", "hold", "decision", "urgent", "fyi")


@dataclass(frozen=True)
class ParsedTag:
    """One `#tag` or `@mention` found in a post body.

    text: as written, without the leading sigil (``47-1234-S03``, ``area:A12``, ``hold``,
      ``party:acme-nde``).
    kind: record (fits a numbering pattern of the scope), code (``ns:value``), signal (in the
      signal set), mention (``@``), otherwise topic. Precedence: mention, record, code, signal,
      topic.
    start, end: character offsets of the whole token including the sigil, for highlighting.
    namespace: for code and mention tags, the part before ``:`` (``area``, ``party``), else None.
    record_id: for a record tag that resolved to an existing record in the scope or company,
      else None.
    """

    text: str
    kind: TagKind
    start: int
    end: int
    namespace: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class FeedItem:
    """One row of a feed query: a post or an event card, newest first by ``at`` then ``seq``.

    For a post, ``id`` is the post id; for a card, a deterministic card id derived from its first
    event id. ``event_count`` is 1 for a post; for a card, the number of aggregated ledger events.
    """

    id: str
    item_type: Literal["post", "card"]
    scope: str
    actor: str
    at: datetime
    seq: int
    summary: str  # post body (or "[retracted]") or the card's rendered summary
    importance: Importance
    record_ids: tuple[str, ...] = ()
    tags: tuple[ParsedTag, ...] = ()
    event_count: int = 1
    retracted: bool = False
    reactions: dict[str, int] = field(default_factory=dict[str, int])


# Card aggregation (supervisor-built, deterministic on rebuild): consecutive ledger events with the
# same actor, event_type and scope, whose recorded_at lies within CARD_WINDOW_SECONDS of the card's
# first event, extend that card; any other event in the same scope closes it. Feed.* events never
# become cards.
CARD_WINDOW_SECONDS = 600
