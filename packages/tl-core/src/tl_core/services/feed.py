"""Post to the feed and edit a post (brief 21.1, 21.2). The entry point for WS-B and WS-C.

A post is its own ledger stream (``core.ActivityPost``, stream id = post id, scope = the project).
``handle_post`` parses the body for tags with the numbering patterns of the scope, appends
``Feed.Posted``, and, in the same unit of work, runs the existing ``SuggestLink`` handler once per
resolved record tag: relation ``references``, from the post to the record, source ``key_detected``,
causation = the posted event. Hashtags never change a record (brief 21.2); the only write beyond the
post is a *suggested* link that a person accepts or declines. A declined suggestion is not made
again, an existing link is not duplicated, and a voided record is not linked; the post itself is
still tagged.

Handlers never commit. ``SuggestLink`` raises before it appends, so skipping its refusals inside the
open unit of work leaves nothing half written (the caveat in ``tl_core.uow``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import field_validator
from sqlalchemy import text

from tl_core.feed.config import signal_tags
from tl_core.feed.tags import (
    parse_tags,
    record_ids_of,
    tags_to_payload,
)
from tl_core.feed.types import FEED_EDITED, FEED_POSTED, Importance, ParsedTag
from tl_core.ledger import Event, NewEvent
from tl_core.numbering.config import get_numbering
from tl_core.numbering.detect import KeyMatch, resolve_chips
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import (
    DuplicateLinkError,
    InvalidScopeError,
    NoChangesError,
    PostNotFoundError,
    PostRetractedError,
    RecordVoidedError,
    SuggestionDeclinedError,
)
from tl_core.services.links import SuggestLink, handle_suggest_link
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

POST_STREAM_TYPE = "core.ActivityPost"
MAX_BODY_LENGTH = 10_000

# Refusals of SuggestLink that are not errors for a post: the link is simply not suggested.
_NOT_SUGGESTED = (DuplicateLinkError, SuggestionDeclinedError, RecordVoidedError)

_POST_SQL = text(
    "SELECT item_id, scope, actor, summary, retracted, version, base_importance, reactions_json "
    "FROM cur_feed_items WHERE item_id = :post_id AND item_type = 'post'"
)
_POST_RECORDS_SQL = text(
    "SELECT record_id FROM cur_feed_tags WHERE item_id = :post_id AND kind = 'record' "
    "ORDER BY start_pos"
)


class PostToFeed(Command):
    """Post ``body`` to the project feed of ``scope`` as ``actor`` (person, agent or service).

    ``post_id`` lets a caller choose the id (None: a new ULID). ``importance`` is what the author
    declares; a signal tag in the body raises the effective level to high.
    """

    body: str
    importance: Importance = "normal"
    post_id: str | None = None

    @field_validator("body")
    @classmethod
    def _body_is_usable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body must not be blank")
        if len(value) > MAX_BODY_LENGTH:
            raise ValueError(f"body must be at most {MAX_BODY_LENGTH} characters")
        return value


class EditPost(Command):
    """Replace the body of a post. ``expected_version`` None: whatever version the post has now."""

    post_id: str
    body: str
    expected_version: int | None = None

    @field_validator("body")
    @classmethod
    def _body_is_usable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body must not be blank")
        if len(value) > MAX_BODY_LENGTH:
            raise ValueError(f"body must be at most {MAX_BODY_LENGTH} characters")
        return value


@dataclass(frozen=True)
class PostRow:
    """The current state of a post, read from ``cur_feed_items``."""

    post_id: str
    scope: str
    author: str
    body: str  # empty once retracted
    retracted: bool
    version: int  # ledger stream_version of the post stream
    base_importance: Importance
    reactions: dict[str, list[str]]  # reaction -> sorted actors


def load_post(uow: UnitOfWork, scope: str, post_id: str) -> PostRow:
    """The post, read in the caller's transaction. Raises ``PostNotFoundError`` if no post has this
    id in ``scope`` (a post of another project reads as absent)."""
    row = uow.conn().execute(_POST_SQL, {"post_id": post_id}).first()
    if row is None or row.scope != scope:
        raise PostNotFoundError(f"no post {post_id!r} in scope {scope!r}")
    reactions: dict[str, list[str]] = json.loads(row.reactions_json)
    return PostRow(
        post_id=row.item_id,
        scope=row.scope,
        author=row.actor,
        body=row.summary,
        retracted=bool(row.retracted),
        version=row.version,
        base_importance=row.base_importance,
        reactions=reactions,
    )


def _require_project(scope: str) -> None:
    if not scope.startswith("project:"):
        raise InvalidScopeError(f"a post belongs to a project; scope {scope!r} is not one")


def parse_post(uow: UnitOfWork, scope: str, body: str) -> list[ParsedTag]:
    """The tags of ``body`` with record keys resolved in ``scope`` (then ``company``)."""

    def resolve(match: KeyMatch) -> str | None:
        return resolve_chips(uow, scope, [match])[0].record_id

    return parse_tags(
        body,
        patterns=get_numbering().for_scope(scope),
        resolve=resolve,
        signal_tags=signal_tags(),
    )


def _suggest_references(
    uow: UnitOfWork,
    cmd: Command,
    post_id: str,
    record_ids: list[str],
    causing: Event,
    correlation_id: str,
) -> list[Event]:
    events: list[Event] = []
    for record_id in record_ids:
        try:
            result = handle_suggest_link(
                uow,
                SuggestLink(
                    actor=cmd.actor,
                    source=cmd.source,
                    scope=cmd.scope,
                    from_id=post_id,
                    to_id=record_id,
                    relation="references",
                    link_source="key_detected",
                    confidence=1.0,
                    correlation_id=correlation_id,
                    causation_id=causing.event_id,
                ),
            )
        except _NOT_SUGGESTED:
            continue
        events.extend(result.events)
    return events


def handle_post(uow: UnitOfWork, cmd: PostToFeed) -> CommandResult:
    """Append ``Feed.Posted`` and suggest a ``references`` link for each resolved record tag.

    ``CommandResult.stream_id`` is the post id, ``version`` 1, and ``events`` holds ``Feed.Posted``
    first, then one ``Link.Suggested`` per suggested link. Raises ``InvalidScopeError`` when
    ``scope`` is not a project; ``ConcurrencyError`` when a given ``post_id`` already exists.
    """
    _require_project(cmd.scope)
    post_id = cmd.post_id or new_ulid()
    correlation_id = cmd.correlation_id or new_ulid()
    tags = parse_post(uow, cmd.scope, cmd.body)
    record_ids = record_ids_of(tags)

    result = uow.append(
        stream_id=post_id,
        stream_type=POST_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type=FEED_POSTED,
                payload={
                    "post_id": post_id,
                    "body": cmd.body,
                    "author": cmd.actor,
                    "importance": cmd.importance,
                    "tags": tags_to_payload(tags),
                    "record_ids": record_ids,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=correlation_id,
        causation_id=cmd.causation_id,
    )
    events = list(result.events)
    events += _suggest_references(uow, cmd, post_id, record_ids, result.events[0], correlation_id)
    return CommandResult(stream_id=post_id, key=None, version=result.new_version, events=events)


def handle_edit_post(uow: UnitOfWork, cmd: EditPost) -> CommandResult:
    """Replace a post's body and tags; suggest links for records the edit adds.

    Appends ``Feed.Edited`` (the earlier text stays in the ledger). Records the edit removes keep
    whatever link was suggested before: only a person retracts a link. Raises ``PostNotFoundError``,
    ``PostRetractedError``, ``NoChangesError`` (same body) or ``ConcurrencyError``.
    """
    post = load_post(uow, cmd.scope, cmd.post_id)
    if post.retracted:
        raise PostRetractedError(f"post {cmd.post_id!r} was retracted and cannot be edited")
    if post.body == cmd.body:
        raise NoChangesError(f"the body of post {cmd.post_id!r} is already that text")
    tags = parse_post(uow, cmd.scope, cmd.body)
    record_ids = record_ids_of(tags)
    earlier: set[str] = {
        str(row.record_id)
        for row in uow.conn().execute(_POST_RECORDS_SQL, {"post_id": cmd.post_id})
    }
    correlation_id = cmd.correlation_id or new_ulid()

    payload: dict[str, Any] = {
        "post_id": cmd.post_id,
        "body": cmd.body,
        "tags": tags_to_payload(tags),
        "record_ids": record_ids,
    }
    result = uow.append(
        stream_id=cmd.post_id,
        stream_type=POST_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=cmd.expected_version if cmd.expected_version is not None else post.version,
        events=[NewEvent(event_type=FEED_EDITED, payload=payload)],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=correlation_id,
        causation_id=cmd.causation_id,
    )
    events = list(result.events)
    added = [record_id for record_id in record_ids if record_id not in earlier]
    events += _suggest_references(uow, cmd, cmd.post_id, added, result.events[0], correlation_id)
    return CommandResult(stream_id=cmd.post_id, key=None, version=result.new_version, events=events)
