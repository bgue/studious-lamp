"""Retract a post and react to a post (brief 21.1).

Both act on the post stream (``core.ActivityPost``) of a post that ``handle_post`` made. They read
the post with ``tl_core.services.feed.load_post`` in the caller's transaction, check it, and append
one event. Handlers never commit. Authorisation is not part of Phase 0 (ADR-0005): anyone may
retract or react; the actor is recorded on the event.
"""

from __future__ import annotations

from pydantic import field_validator

from tl_core.feed.config import reactions_enabled
from tl_core.feed.types import FEED_REACTED, FEED_RETRACTED, Reaction
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import (
    NoChangesError,
    PostRetractedError,
    ReactionsDisabledError,
)
from tl_core.services.feed import POST_STREAM_TYPE, load_post
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid


class RetractPost(Command):
    """Retract a post with a reason. ``expected_version`` None: whatever version it has now."""

    post_id: str
    reason: str
    expected_version: int | None = None

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class ReactToPost(Command):
    """Set (``on`` true) or clear (``on`` false) the actor's ``reaction`` on a post."""

    post_id: str
    reaction: Reaction
    on: bool = True
    expected_version: int | None = None


def handle_retract_post(uow: UnitOfWork, cmd: RetractPost) -> CommandResult:
    """Append ``Feed.Retracted`` (payload ``post_id``, ``reason``).

    The post is read in the caller's transaction and refused before anything is appended. Raises
    ``PostNotFoundError`` (unknown post, or a post of another scope), ``PostRetractedError``
    (already retracted) or ``ConcurrencyError`` (a wrong ``expected_version``).
    """
    post = load_post(uow, cmd.scope, cmd.post_id)
    if post.retracted:
        raise PostRetractedError(f"post {cmd.post_id!r} was already retracted")
    result = uow.append(
        stream_id=cmd.post_id,
        stream_type=POST_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=cmd.expected_version if cmd.expected_version is not None else post.version,
        events=[
            NewEvent(
                event_type=FEED_RETRACTED,
                payload={"post_id": cmd.post_id, "reason": cmd.reason},
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.post_id,
        key=None,
        version=result.new_version,
        events=list(result.events),
    )


def handle_react_to_post(uow: UnitOfWork, cmd: ReactToPost) -> CommandResult:
    """Append ``Feed.Reacted`` (payload ``post_id``, ``reaction``, ``on``).

    Refused before anything is appended. Raises ``ReactionsDisabledError`` (the
    ``feed.reactions.enabled`` switch is off), ``PostNotFoundError``, ``PostRetractedError``,
    ``NoChangesError`` (the reaction is already in the state asked for) or ``ConcurrencyError``.
    """
    if not reactions_enabled():
        raise ReactionsDisabledError("reactions are switched off (feed.reactions.enabled)")
    post = load_post(uow, cmd.scope, cmd.post_id)
    if post.retracted:
        raise PostRetractedError(f"post {cmd.post_id!r} was retracted and cannot be reacted to")
    already = cmd.actor in post.reactions.get(cmd.reaction, [])
    if already == cmd.on:
        state = "set" if cmd.on else "clear"
        raise NoChangesError(f"{cmd.reaction!r} on post {cmd.post_id!r} is already {state}")
    result = uow.append(
        stream_id=cmd.post_id,
        stream_type=POST_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=cmd.expected_version if cmd.expected_version is not None else post.version,
        events=[
            NewEvent(
                event_type=FEED_REACTED,
                payload={"post_id": cmd.post_id, "reaction": cmd.reaction, "on": cmd.on},
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.post_id,
        key=None,
        version=result.new_version,
        events=list(result.events),
    )
