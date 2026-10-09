"""Retract a post and react to a post (brief 21.1).

Both act on the post stream (``core.ActivityPost``) of a post that ``handle_post`` made. They read
the post with ``tl_core.services.feed.load_post`` in the caller's transaction, check it, and append
one event. Handlers never commit. Authorisation is not part of Phase 0 (ADR-0005): anyone may
retract or react; the actor is recorded on the event.
"""

from __future__ import annotations

from pydantic import field_validator

from tl_core.feed.types import Reaction
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork


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

    STUB: replace this paragraph and the body (P0-I6-T01). Raises ``PostNotFoundError`` and
    ``PostRetractedError``.
    """
    raise NotImplementedError


def handle_react_to_post(uow: UnitOfWork, cmd: ReactToPost) -> CommandResult:
    """Append ``Feed.Reacted`` (payload ``post_id``, ``reaction``, ``on``).

    STUB: replace this paragraph and the body (P0-I6-T01). Raises ``ReactionsDisabledError``,
    ``PostNotFoundError``, ``PostRetractedError`` and ``NoChangesError``.
    """
    raise NotImplementedError
