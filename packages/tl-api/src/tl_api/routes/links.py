"""Link reads: a record's links, the trace tree, expected links, counts, picker search (brief 7).

Thin: one tl_core query per route. ``RecordNotFoundError`` becomes 404 through the error table.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_core.links.expected import MissingLink, missing_expected_links
from tl_core.services import link_queries, link_trace
from tl_core.services.link_queries import LinkCounts, LinkTarget, LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["links"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("link.read"))]


@router.get("/records/{record_id}/links", operation_id="get_record_links")
def get_record_links(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    include_retracted: Annotated[bool, Query()] = False,
) -> list[LinkView]:
    """Both directions of the record's links, each with its label as read from this record."""
    with ctx.backend(True) as uow:
        return link_queries.links_of(uow, record_id, include_retracted=include_retracted)


@router.get("/records/{record_id}/trace", operation_id="get_record_trace")
def get_record_trace(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    depth: Annotated[int, Query(ge=0, le=8)] = 2,
    direction: Annotated[TraceDirection, Query()] = "both",
) -> TraceNode:
    """The tree of records within `depth` link hops of the record (brief 7.5)."""
    with ctx.backend(True) as uow:
        return link_trace.trace(uow, record_id, depth=depth, direction=direction)


@router.get("/records/{record_id}/expected-links", operation_id="get_expected_links")
def get_expected_links(ctx: Ctx, actor: Reader, record_id: str) -> list[MissingLink]:
    """Expected links the record does not have yet."""
    with ctx.backend(True) as uow:
        return missing_expected_links(uow, record_id)


@router.get("/links/counts", operation_id="get_link_counts")
def get_link_counts(
    ctx: Ctx,
    actor: Reader,
    record_id: Annotated[list[str], Query(min_length=1, max_length=500)],
) -> dict[str, LinkCounts]:
    """Link counts for each record id given (zeros for a record with no links)."""
    with ctx.backend(True) as uow:
        return link_queries.link_counts(uow, record_id)


@router.get("/links/search", operation_id="search_linkable")
def search_linkable(
    ctx: Ctx,
    actor: Reader,
    scope: Annotated[str, Query()],
    q: Annotated[str, Query(description="Words that must occur in the key or title.")] = "",
    record_type: Annotated[str | None, Query()] = None,
    exclude_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[LinkTarget]:
    """Records the link picker may offer from this scope (its own and the company's)."""
    with ctx.backend(True) as uow:
        return link_queries.search_linkable(
            uow, scope, q, record_type=record_type, exclude_id=exclude_id, limit=limit
        )
