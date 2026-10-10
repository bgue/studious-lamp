"""Feed suggestions and composer completion (brief 21.2, 21.4). Read-only queries.

``feed_suggestions`` derives the pending ``#hold`` suggestions of posts; ``complete_tags`` answers
the composer after ``#`` or ``@``. Both read in the caller's transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.engine import Connection

from tl_core.feed.config import signal_tags
from tl_core.feed.tags import tag_key
from tl_core.feed.types import FeedItem
from tl_core.services.feed_queries import Completion, FeedSuggestion
from tl_core.uow import UnitOfWork

_KEYS_SQL = text("SELECT id, key FROM cur_core_record WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)
_RECORDS_SQL = text(
    "SELECT key, title FROM cur_core_record "
    "WHERE scope IN (:scope, 'company') AND voided = :no AND key IS NOT NULL "
    "AND LOWER(key) LIKE :p ESCAPE '\\' ORDER BY key LIMIT :limit"
)
_CODES_AND_TOPICS_SQL = text(
    "SELECT tag_key, kind, COUNT(*) AS n FROM cur_feed_tags "
    "WHERE scope = :scope AND kind IN ('code', 'topic') AND tag_key LIKE :p ESCAPE '\\' "
    "GROUP BY tag_key, kind ORDER BY n DESC, tag_key LIMIT :limit"
)
_MENTIONS_SQL = text(
    "SELECT tag_key, kind, COUNT(*) AS n FROM cur_feed_tags "
    "WHERE scope = :scope AND kind IN ('mention') AND tag_key LIKE :p ESCAPE '\\' "
    "GROUP BY tag_key, kind ORDER BY n DESC, tag_key LIMIT :limit"
)
_AUTHORS_SQL = text(
    "SELECT DISTINCT actor FROM cur_feed_items "
    "WHERE scope = :scope AND item_type = 'post' ORDER BY actor"
)


def _holds_a_record(item: FeedItem) -> bool:
    """A post, not retracted, with the signal tag ``hold`` and at least one referenced record."""
    return (
        item.item_type == "post"
        and not item.retracted
        and len(item.record_ids) > 0
        and any(tag.kind == "signal" and tag_key(tag) == "hold" for tag in item.tags)
    )


def feed_suggestions(uow: UnitOfWork, items: Sequence[FeedItem]) -> dict[str, list[FeedSuggestion]]:
    """Suggestions for the posts among ``items``, keyed by post id.

    A post that is not retracted, has the signal tag ``hold`` and references at least one record
    gets one ``FeedSuggestion`` per referenced record, in the order of ``record_ids``:
    kind ``constraint``, prompt ``Create a constraint on <key>?`` (the record's key, else its id).
    Posts with no suggestion are absent from the result.
    """
    held = [item for item in items if _holds_a_record(item)]
    if not held:
        return {}
    ids = list(dict.fromkeys(rid for item in held for rid in item.record_ids))
    rows = uow.conn().execute(_KEYS_SQL, {"ids": ids}).mappings().all()
    keys: dict[str, str | None] = {row["id"]: row["key"] for row in rows}
    found: dict[str, list[FeedSuggestion]] = {}
    for item in held:
        for rid in item.record_ids:
            key = keys.get(rid)
            suggestion = FeedSuggestion(
                item_id=item.id,
                kind="constraint",
                record_id=rid,
                record_key=key,
                prompt=f"Create a constraint on {key or rid}?",
            )
            found.setdefault(item.id, []).append(suggestion)
    return found


def _prefix_pattern(prefix: str) -> str:
    """A LIKE pattern for values that start with ``prefix``, case-insensitive, wildcards literal."""
    escaped = prefix.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


def _used(count: int) -> str:
    return "used 1 time" if count == 1 else f"used {count} times"


def _used_tags(
    conn: Connection, sql: TextClause, scope: str, pattern: str, limit: int
) -> list[Completion]:
    """Tags of ``sql`` used in the scope, most used first, then by text."""
    rows = conn.execute(sql, {"scope": scope, "p": pattern, "limit": limit}).mappings().all()
    return [Completion(row["tag_key"], row["kind"], _used(row["n"])) for row in rows]


def _hash_completions(conn: Connection, scope: str, prefix: str, limit: int) -> list[Completion]:
    pattern = _prefix_pattern(prefix)
    records = (
        conn.execute(_RECORDS_SQL, {"scope": scope, "no": False, "p": pattern, "limit": limit})
        .mappings()
        .all()
    )
    found = [Completion(row["key"], "record", row["title"]) for row in records]
    lowered = prefix.lower()
    found.extend(
        Completion(word, "signal", "signal tag")
        for word in signal_tags()
        if word.lower().startswith(lowered)
    )
    found.extend(_used_tags(conn, _CODES_AND_TOPICS_SQL, scope, pattern, limit))
    return found


def _author_completion(actor: str) -> tuple[str, str] | None:
    """The text and detail an author completes to, or None for actors that are not people."""
    if actor.startswith("user:"):
        return actor[len("user:") :], "person"
    if actor.startswith("agent:"):
        return actor, "agent"
    return None


def _at_completions(conn: Connection, scope: str, prefix: str, limit: int) -> list[Completion]:
    pattern = _prefix_pattern(prefix)
    found = _used_tags(conn, _MENTIONS_SQL, scope, pattern, limit)
    listed = {completion.text.lower() for completion in found}
    lowered = prefix.lower()
    for row in conn.execute(_AUTHORS_SQL, {"scope": scope}).mappings().all():
        author = _author_completion(row["actor"])
        if author is None:
            continue
        completed, detail = author
        if not completed.lower().startswith(lowered) or completed.lower() in listed:
            continue
        listed.add(completed.lower())
        found.append(Completion(completed, "mention", detail))
    return found


def complete_tags(
    uow: UnitOfWork, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
) -> list[Completion]:
    """Candidates for the composer after ``sigil`` and the typed ``prefix`` (case-insensitive).

    After ``#``, in this order and at most ``limit`` in all:

    1. Records of the scope and the company, never voided, whose key starts with the prefix, by
       key (kind ``record``, detail the title).
    2. Signal tags that start with the prefix, in the order of ``signal_tags()`` (kind ``signal``,
       detail ``signal tag``).
    3. Codes and topics already used in posts of the scope whose lower-cased text starts with the
       prefix, most used first then by text (kind ``code`` or ``topic``, text lower-case, detail
       ``used 3 times`` or ``used 1 time``).

    After ``@``: mentions already used in the scope (most used first, then by text; kind
    ``mention``, text lower-case, detail ``used N times``), then authors of posts in the scope that
    are people or agents: ``user:jsmith`` completes as ``jsmith`` (detail ``person``),
    ``agent:triage`` as ``agent:triage`` (detail ``agent``); ``svc:`` actors are left out. Authors
    already listed as a mention are not repeated. Authors are matched on the text they complete to.
    """
    conn = uow.conn()
    if sigil == "#":
        found = _hash_completions(conn, scope, prefix, limit)
    else:
        found = _at_completions(conn, scope, prefix, limit)
    return found[:limit]
