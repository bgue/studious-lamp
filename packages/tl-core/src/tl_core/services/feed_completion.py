"""Feed suggestions and composer completion (brief 21.2, 21.4). Read-only queries.

``feed_suggestions`` derives the pending ``#hold`` suggestions of posts; ``complete_tags`` answers
the composer after ``#`` or ``@``. Both read in the caller's transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from tl_core.feed.types import FeedItem
from tl_core.services.feed_queries import Completion, FeedSuggestion
from tl_core.uow import UnitOfWork


def feed_suggestions(uow: UnitOfWork, items: Sequence[FeedItem]) -> dict[str, list[FeedSuggestion]]:
    """Suggestions for the posts among ``items``, keyed by post id.

    A post that is not retracted, has the signal tag ``hold`` and references at least one record
    gets one ``FeedSuggestion`` per referenced record, in the order of ``record_ids``:
    kind ``constraint``, prompt ``Create a constraint on <key>?`` (the record's key, else its id).
    Posts with no suggestion are absent from the result.

    STUB: replace this paragraph and the body (P0-I6-T03).
    """
    raise NotImplementedError


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

    STUB: replace this paragraph and the body (P0-I6-T03).
    """
    raise NotImplementedError
