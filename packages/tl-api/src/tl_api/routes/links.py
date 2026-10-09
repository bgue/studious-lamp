"""Link reads: a record's links, the trace tree, expected links, counts, picker search (brief 7).

STUB (P0-I4-T41): the route bodies below raise ``NotImplementedError``. Signatures, decorators,
parameters and response models are final (the committed OpenAPI document depends on them);
implement the bodies only, then delete this paragraph.

Thin: one tl_core query per route. ``RecordNotFoundError`` becomes 404 through the error table.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_core.links.expected import MissingLink
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
    raise NotImplementedError("STUB (P0-I4-T41)")


@router.get("/records/{record_id}/trace", operation_id="get_record_trace")
def get_record_trace(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    depth: Annotated[int, Query(ge=0, le=8)] = 2,
    direction: Annotated[TraceDirection, Query()] = "both",
) -> TraceNode:
    """The tree of records within `depth` link hops of the record (brief 7.5)."""
    raise NotImplementedError("STUB (P0-I4-T41)")


@router.get("/records/{record_id}/expected-links", operation_id="get_expected_links")
def get_expected_links(ctx: Ctx, actor: Reader, record_id: str) -> list[MissingLink]:
    """Expected links the record does not have yet."""
    raise NotImplementedError("STUB (P0-I4-T41)")


@router.get("/links/counts", operation_id="get_link_counts")
def get_link_counts(
    ctx: Ctx,
    actor: Reader,
    record_id: Annotated[list[str], Query(min_length=1, max_length=500)],
) -> dict[str, LinkCounts]:
    """Link counts for each record id given (zeros for a record with no links)."""
    raise NotImplementedError("STUB (P0-I4-T41)")


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
    raise NotImplementedError("STUB (P0-I4-T41)")
