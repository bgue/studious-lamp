"""FeedProjector: posts, event cards and tags into ``cur_feed_items`` and ``cur_feed_tags``.

Brief 21.1, FANOUT decision D1. Two jobs, both deterministic (rows depend only on the event and on
rows this projector already wrote; no clock, no outside reads):

* ``Feed.Posted|Edited|Retracted|Reacted`` maintain one row per post. A retracted post keeps its
  row as a tombstone: the body is dropped and so are its non-record tags, so it leaves hashtag
  feeds but stays in the feed of the records it referenced.
* Every other event (the projector sets ``handles_all``) goes through the card rules in
  ``tl_core.feed.cards``. They decide, per scope, whether the event extends the open card, starts
  a new one, closes it, or is ignored. A card's subject records are rows of ``cur_feed_tags``.

It must see every event, in ``seq`` order, for its cards to equal those of a rebuild; ``rebuild``
replays the whole ledger, so they do. It reads only its own tables, so rebuilding it alone is safe.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.feed.cards import (
    OpenCard,
    card_id_for,
    disposition,
    render_card_summary,
    subjects_of,
    to_us,
)
from tl_core.feed.tags import effective_importance, tag_key, tags_from_payload
from tl_core.feed.types import (
    FEED_EDITED,
    FEED_POSTED,
    FEED_REACTED,
    FEED_RETRACTED,
    ParsedTag,
)
from tl_core.ledger import Event, iso_utc

_INSERT_ITEM_SQL = text(
    "INSERT INTO cur_feed_items (item_id, item_type, scope, actor, occurred_at, seq, summary, "
    "importance, base_importance, event_type, event_count, first_us, first_seq, open_scope, "
    "retracted, retract_reason, edit_count, reactions_json, version) VALUES (:item_id, "
    ":item_type, :scope, :actor, :occurred_at, :seq, :summary, :importance, :base_importance, "
    ":event_type, :event_count, :first_us, :first_seq, :open_scope, :retracted, "
    ":retract_reason, :edit_count, :reactions_json, :version)"
)
_INSERT_TAG_SQL = text(
    "INSERT INTO cur_feed_tags (tag_row_id, item_id, scope, kind, tag_text, tag_key, namespace, "
    "record_id, start_pos, end_pos, seq) VALUES (:tag_row_id, :item_id, :scope, :kind, "
    ":tag_text, :tag_key, :namespace, :record_id, :start_pos, :end_pos, :seq)"
)
_TAG_EXISTS_SQL = text("SELECT 1 FROM cur_feed_tags WHERE tag_row_id = :tag_row_id")
_OPEN_CARD_SQL = text(
    "SELECT item_id, actor, event_type, first_us, event_count FROM cur_feed_items "
    "WHERE open_scope = :scope"
)
_CLOSE_CARD_SQL = text("UPDATE cur_feed_items SET open_scope = NULL WHERE item_id = :item_id")
_EXTEND_CARD_SQL = text(
    "UPDATE cur_feed_items SET event_count = :event_count, occurred_at = :occurred_at, "
    "seq = :seq, summary = :summary WHERE item_id = :item_id"
)
_POST_SQL = text(
    "SELECT base_importance, reactions_json, retracted FROM cur_feed_items "
    "WHERE item_id = :item_id AND item_type = 'post'"
)
_EDIT_SQL = text(
    "UPDATE cur_feed_items SET summary = :summary, importance = :importance, "
    "edit_count = edit_count + 1, version = :version WHERE item_id = :item_id"
)
_RETRACT_SQL = text(
    "UPDATE cur_feed_items SET summary = '', retracted = :retracted, "
    "retract_reason = :reason, version = :version WHERE item_id = :item_id"
)
_REACT_SQL = text(
    "UPDATE cur_feed_items SET reactions_json = :reactions_json, version = :version "
    "WHERE item_id = :item_id"
)
_DELETE_TAGS_SQL = text("DELETE FROM cur_feed_tags WHERE item_id = :item_id")
_DELETE_NON_RECORD_TAGS_SQL = text(
    "DELETE FROM cur_feed_tags WHERE item_id = :item_id AND kind <> 'record'"
)


def _tag_params(
    item_id: str,
    scope: str,
    *,
    kind: str,
    tag_text: str,
    key: str,
    namespace: str | None,
    record_id: str | None,
    start: int,
    end: int,
    seq: int,
) -> dict[str, Any]:
    return {
        "tag_row_id": f"{item_id}|{kind}|{key}|{start}",
        "item_id": item_id,
        "scope": scope,
        "kind": kind,
        "tag_text": tag_text,
        "tag_key": key,
        "namespace": namespace,
        "record_id": record_id,
        "start_pos": start,
        "end_pos": end,
        "seq": seq,
    }


def _post_tag_rows(item_id: str, event: Event, tags: Iterable[ParsedTag]) -> list[dict[str, Any]]:
    return [
        _tag_params(
            item_id,
            event.scope,
            kind=tag.kind,
            tag_text=tag.text,
            key=tag_key(tag),
            namespace=tag.namespace,
            record_id=tag.record_id,
            start=tag.start,
            end=tag.end,
            seq=event.seq,
        )
        for tag in tags
    ]


class FeedProjector:
    name = "feed"
    handles: frozenset[str] = frozenset()
    handles_all = True  # cards are made of every event type (see tl_core.feed.cards)

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_feed_items", dialect) + statements("cur_feed_tags", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_feed_tags"))
        conn.execute(text("DELETE FROM cur_feed_items"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == FEED_POSTED:
            self._posted(conn, event)
        elif event.event_type == FEED_EDITED:
            self._edited(conn, event)
        elif event.event_type == FEED_RETRACTED:
            self._retracted(conn, event)
        elif event.event_type == FEED_REACTED:
            self._reacted(conn, event)
        self._cards(conn, event)

    # --- posts ------------------------------------------------------------------------------

    def _posted(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        post_id: str = payload["post_id"]
        tags = tags_from_payload(payload.get("tags") or [])
        declared = payload.get("importance") or "normal"
        conn.execute(
            _INSERT_ITEM_SQL,
            {
                "item_id": post_id,
                "item_type": "post",
                "scope": event.scope,
                "actor": event.actor,
                "occurred_at": iso_utc(event.recorded_at),
                "seq": event.seq,
                "summary": payload["body"],
                "importance": effective_importance(declared, tags),
                "base_importance": declared,
                "event_type": None,
                "event_count": 1,
                "first_us": None,
                "first_seq": None,
                "open_scope": None,
                "retracted": False,
                "retract_reason": None,
                "edit_count": 0,
                "reactions_json": "{}",
                "version": event.stream_version,
            },
        )
        for row in _post_tag_rows(post_id, event, tags):
            conn.execute(_INSERT_TAG_SQL, row)

    def _post_row(self, conn: Connection, event: Event) -> Any:
        row = conn.execute(_POST_SQL, {"item_id": event.payload["post_id"]}).first()
        if row is None:
            raise LookupError(f"no cur_feed_items post for {event.payload['post_id']}")
        return row

    def _edited(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        post_id: str = payload["post_id"]
        row = self._post_row(conn, event)
        tags = tags_from_payload(payload.get("tags") or [])
        conn.execute(
            _EDIT_SQL,
            {
                "item_id": post_id,
                "summary": payload["body"],
                "importance": effective_importance(row.base_importance, tags),
                "version": event.stream_version,
            },
        )
        conn.execute(_DELETE_TAGS_SQL, {"item_id": post_id})
        for tag_row in _post_tag_rows(post_id, event, tags):
            conn.execute(_INSERT_TAG_SQL, tag_row)

    def _retracted(self, conn: Connection, event: Event) -> None:
        post_id: str = event.payload["post_id"]
        self._post_row(conn, event)
        conn.execute(
            _RETRACT_SQL,
            {
                "item_id": post_id,
                "retracted": True,
                "reason": event.payload.get("reason"),
                "version": event.stream_version,
            },
        )
        conn.execute(_DELETE_NON_RECORD_TAGS_SQL, {"item_id": post_id})

    def _reacted(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        row = self._post_row(conn, event)
        reactions: dict[str, list[str]] = json.loads(row.reactions_json)
        actors = set(reactions.get(payload["reaction"], []))
        if payload["on"]:
            actors.add(event.actor)
        else:
            actors.discard(event.actor)
        if actors:
            reactions[payload["reaction"]] = sorted(actors)
        else:
            reactions.pop(payload["reaction"], None)
        conn.execute(
            _REACT_SQL,
            {
                "item_id": payload["post_id"],
                "reactions_json": json.dumps(reactions, sort_keys=True, separators=(",", ":")),
                "version": event.stream_version,
            },
        )

    # --- cards ------------------------------------------------------------------------------

    def _cards(self, conn: Connection, event: Event) -> None:
        found = conn.execute(_OPEN_CARD_SQL, {"scope": event.scope}).first()
        open_card = (
            OpenCard(
                found.item_id, found.actor, found.event_type, found.first_us, found.event_count
            )
            if found is not None
            else None
        )
        action = disposition(open_card, event)
        if action == "ignore":
            return
        if action == "close":
            if open_card is not None:
                conn.execute(_CLOSE_CARD_SQL, {"item_id": open_card.item_id})
            return
        if action == "extend" and open_card is not None:
            count = open_card.event_count + 1
            conn.execute(
                _EXTEND_CARD_SQL,
                {
                    "item_id": open_card.item_id,
                    "event_count": count,
                    "occurred_at": iso_utc(event.recorded_at),
                    "seq": event.seq,
                    "summary": render_card_summary(event.actor, event.event_type, count),
                },
            )
            card_id = open_card.item_id
        else:
            if open_card is not None:
                conn.execute(_CLOSE_CARD_SQL, {"item_id": open_card.item_id})
            card_id = card_id_for(event.event_id)
            conn.execute(
                _INSERT_ITEM_SQL,
                {
                    "item_id": card_id,
                    "item_type": "card",
                    "scope": event.scope,
                    "actor": event.actor,
                    "occurred_at": iso_utc(event.recorded_at),
                    "seq": event.seq,
                    "summary": render_card_summary(event.actor, event.event_type, 1),
                    "importance": "low",
                    "base_importance": "low",
                    "event_type": event.event_type,
                    "event_count": 1,
                    "first_us": to_us(event.recorded_at),
                    "first_seq": event.seq,
                    "open_scope": event.scope,
                    "retracted": False,
                    "retract_reason": None,
                    "edit_count": 0,
                    "reactions_json": "{}",
                    "version": None,
                },
            )
        for record_id in subjects_of(event):
            params = _tag_params(
                card_id,
                event.scope,
                kind="record",
                tag_text=record_id,
                key=record_id,
                namespace=None,
                record_id=record_id,
                start=0,
                end=0,
                seq=event.seq,
            )
            if conn.execute(_TAG_EXISTS_SQL, {"tag_row_id": params["tag_row_id"]}).first() is None:
                conn.execute(_INSERT_TAG_SQL, params)
