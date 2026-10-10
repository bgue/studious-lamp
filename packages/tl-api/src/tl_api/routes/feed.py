"""Feed reads: the project feed, one post and composer completion (brief 21).

Thin: one tl_core call per route. Writing to the feed goes through the generated command routes
(``POST /commands/PostToFeed|EditPost|RetractPost|ReactToPost``, see ``tl_api.commands``), so a
post made over HTTP runs the same handler as one made from the TUI. A post of another project
reads as absent (``PostNotFoundError`` is 404 in the error table).
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from tl_core.feed.types import FeedItem
from tl_core.services import feed_completion, feed_queries
from tl_core.services.feed_queries import Completion, FeedPage

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["feed"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("feed.read"))]
ScopeParam = Annotated[str, Query(min_length=1, max_length=128, description="`project:<id>`.")]


@router.get("/feed", operation_id="get_feed")
def get_feed(
    ctx: Ctx,
    actor: Reader,
    scope: ScopeParam,
    record_id: Annotated[
        str | None, Query(max_length=128, description="Only items about this record.")
    ] = None,
    include_linked: Annotated[
        bool, Query(description="With `record_id`: also the records one link away.")
    ] = False,
    tag: Annotated[
        str | None,
        Query(
            max_length=200, description="A hashtag (`hold`, `area:A12`) or a mention (`@party:x`)."
        ),
    ] = None,
    item_type: Annotated[Literal["post", "card"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_seq: Annotated[
        int | None, Query(ge=0, description="`next_before` of the previous page.")
    ] = None,
) -> FeedPage:
    """Posts and event cards of a project, newest first, with record labels and `#hold` offers."""
    with ctx.backend(True) as uow:
        page = feed_queries.list_feed(
            uow,
            scope,
            record_id=record_id,
            include_linked=include_linked,
            tag=tag,
            item_type=item_type,
            limit=limit,
            before_seq=before_seq,
        )
        suggestions = feed_completion.feed_suggestions(uow, page.items)
        return dataclasses.replace(page, suggestions=suggestions)


@router.get("/feed/complete", operation_id="complete_feed_tag")
def complete_feed_tag(
    ctx: Ctx,
    actor: Reader,
    scope: ScopeParam,
    sigil: Annotated[Literal["#", "@"], Query(description="`#` for tags, `@` for people.")],
    prefix: Annotated[
        str, Query(max_length=100, description="What was typed after the sigil.")
    ] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
) -> list[Completion]:
    """Composer candidates after `#` (keys, signal tags, codes, topics) or `@` (people)."""
    with ctx.backend(True) as uow:
        return feed_completion.complete_tags(uow, scope, sigil, prefix, limit=limit)


@router.get("/feed/posts/{post_id}", operation_id="get_feed_post")
def get_feed_post(ctx: Ctx, actor: Reader, post_id: str, scope: ScopeParam) -> FeedItem:
    """One post with its tags and reaction counts; 404 when no post has this id in `scope`."""
    with ctx.backend(True) as uow:
        return feed_queries.get_post(uow, scope, post_id)
