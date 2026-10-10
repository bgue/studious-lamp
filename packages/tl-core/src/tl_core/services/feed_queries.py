"""Read queries over the feed projection (brief 21.3): the feed lists and the result types.

Plain dataclasses only: clients (CLI, TUI, API) never write SQL. Every function reads in the
caller's transaction (usually a read-only unit of work).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import BindParameter

from tl_core.feed.types import FeedItem, ParsedTag, TagKind
from tl_core.services.errors import PostNotFoundError
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


# Columns read for one feed row; every feed query selects exactly these, in this order.
_FEED_COLUMNS = (
    "SELECT i.item_id, i.item_type, i.scope, i.actor, i.occurred_at, i.seq, i.summary, "
    "i.importance, i.event_count, i.retracted, i.reactions_json FROM cur_feed_items i"
)
# The records one link away: both directions, live link statuses only (suggested and retracted
# links do not count). A link with a post at one end drops out of the join.
_LINKED_IDS_SQL = text(
    "SELECT DISTINCT c.id FROM cur_links l JOIN cur_core_record c "
    "ON c.id = CASE WHEN l.from_id = :id THEN l.to_id ELSE l.from_id END "
    "WHERE (l.from_id = :id OR l.to_id = :id) AND l.status IN ('active', 'stale', 'broken')"
)
_TAGS_SQL = text(
    "SELECT item_id, kind, tag_text, namespace, record_id, start_pos, end_pos, seq "
    "FROM cur_feed_tags WHERE item_id IN :ids ORDER BY item_id, start_pos, seq, tag_row_id"
).bindparams(bindparam("ids", expanding=True))
_LABELS_SQL = text("SELECT id, key, title FROM cur_core_record WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)
_POST_SQL = text(
    _FEED_COLUMNS + " WHERE i.item_id = :id AND i.item_type = 'post' AND i.scope = :scope"
)


def _unique(values: Iterable[str | None]) -> tuple[str, ...]:
    """The non-null values without repeats, in first-seen order."""
    seen: dict[str, None] = {}
    for value in values:
        if value is not None:
            seen.setdefault(value, None)
    return tuple(seen)


def _about_ids(conn: Connection, record_id: str, include_linked: bool) -> list[str]:
    """The record itself, plus with ``include_linked`` the records one link away from it."""
    found = [record_id]
    if include_linked:
        rows = conn.execute(_LINKED_IDS_SQL, {"id": record_id}).all()
        found.extend(row.id for row in rows)
    return list(dict.fromkeys(found))


def _feed_item(row: Any, tag_rows: Sequence[Any]) -> FeedItem:
    """One feed item from a ``cur_feed_items`` row and its ``cur_feed_tags`` rows (in order)."""
    occurred = row.occurred_at
    at = occurred if isinstance(occurred, datetime) else datetime.fromisoformat(occurred)
    is_post = row.item_type == "post"
    record_ids = _unique(t.record_id for t in tag_rows if t.kind == "record")
    if not is_post:
        record_ids = record_ids[:CARD_SUBJECTS_SHOWN]
    tags = (
        tuple(
            ParsedTag(
                text=t.tag_text,
                kind=t.kind,
                start=t.start_pos,
                end=t.end_pos,
                namespace=t.namespace,
                record_id=t.record_id,
            )
            for t in tag_rows
        )
        if is_post
        else ()
    )
    retracted = bool(row.retracted)
    reactions = {
        name: len(actors) for name, actors in json.loads(row.reactions_json).items() if actors
    }
    return FeedItem(
        id=row.item_id,
        item_type=row.item_type,
        scope=row.scope,
        actor=row.actor,
        at=at,
        seq=row.seq,
        summary="[retracted]" if retracted else row.summary,
        importance=row.importance,
        record_ids=record_ids,
        tags=tags,
        event_count=row.event_count,
        retracted=retracted,
        reactions=reactions,
    )


def _feed_items(conn: Connection, rows: Sequence[Any]) -> list[FeedItem]:
    """Build the items of ``rows``, fetching the tags of all of them in one query."""
    if not rows:
        return []
    tag_rows = conn.execute(_TAGS_SQL, {"ids": [row.item_id for row in rows]}).all()
    by_item: dict[str, list[Any]] = {}
    for tag_row in tag_rows:
        by_item.setdefault(tag_row.item_id, []).append(tag_row)
    return [_feed_item(row, by_item.get(row.item_id, [])) for row in rows]


def _labels(conn: Connection, record_ids: Sequence[str]) -> dict[str, str]:
    """Each record id's key, else its title."""
    if not record_ids:
        return {}
    rows = conn.execute(_LABELS_SQL, {"ids": list(record_ids)}).all()
    return {row.id: row.key or row.title for row in rows}


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
    """
    conn = uow.conn()
    clauses = ["i.scope = :scope"]
    params: dict[str, Any] = {"scope": scope, "limit": limit + 1}
    bindings: list[BindParameter[Any]] = []
    if item_type is not None:
        clauses.append("i.item_type = :item_type")
        params["item_type"] = item_type
    if before_seq is not None:
        clauses.append("i.seq < :before_seq")
        params["before_seq"] = before_seq
    if record_id is not None:
        params["record_ids"] = _about_ids(conn, record_id, include_linked)
        bindings.append(bindparam("record_ids", expanding=True))
        clauses.append(
            "i.item_id IN (SELECT t.item_id FROM cur_feed_tags t "
            "WHERE t.kind = 'record' AND t.record_id IN :record_ids)"
        )
    if tag is not None:
        # A mention is looked up as "@..."; any other tag matches signal, code and topic tags.
        key = tag[1:] if tag[:1] in ("#", "@") else tag
        params["tag_key"] = key.lower()
        kinds = (
            "t.kind = 'mention'" if tag.startswith("@") else "t.kind IN ('signal', 'code', 'topic')"
        )
        clauses.append(
            "i.item_id IN (SELECT t.item_id FROM cur_feed_tags t "
            f"WHERE t.tag_key = :tag_key AND {kinds})"
        )
    sql = f"{_FEED_COLUMNS} WHERE {' AND '.join(clauses)} ORDER BY i.occurred_at DESC, i.seq DESC"
    sql += " LIMIT :limit"
    rows = conn.execute(text(sql).bindparams(*bindings), params).all()
    more = len(rows) > limit
    items = _feed_items(conn, rows[:limit] if more else rows)
    about = list(dict.fromkeys(rid for item in items for rid in item.record_ids))
    return FeedPage(
        items=items,
        labels=_labels(conn, about),
        next_before=items[-1].seq if more and items else None,
    )


def get_post(uow: UnitOfWork, scope: str, post_id: str) -> FeedItem:
    """One post as a ``FeedItem`` (with its tags and reaction counts).

    Raises ``PostNotFoundError`` when no post has this id in ``scope``.
    """
    conn = uow.conn()
    rows = conn.execute(_POST_SQL, {"id": post_id, "scope": scope}).all()
    if not rows:
        raise PostNotFoundError(f"no post {post_id!r} in scope {scope!r}")
    return _feed_items(conn, rows)[0]
