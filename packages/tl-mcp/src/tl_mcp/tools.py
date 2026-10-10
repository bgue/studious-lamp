"""The bodies of the four read tools (T43). ``server.py`` owns names, schemas and error handling.

STUB (P0-I4-T43): function bodies below raise ``NotImplementedError``. Names, signatures and
docstrings are final; implement the bodies, then delete this paragraph.

Each function runs inside ``guarded`` (the authorise hook has been called and expected failures
are mapped), opens a read-only unit of work with ``ctx.factory(True)`` and calls one service.
"""

from __future__ import annotations

from tl_core.services.link_queries import LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode
from tl_core.uow import UnitOfWork

from tl_mcp.context import McpContext
from tl_mcp.models import SearchResult


def resolve_record_id(uow: UnitOfWork, record: str, scope: str | None) -> str:
    """The id of ``record``, which is a record id or (with ``scope``) a record key.

    An id is tried first; ids are ULIDs and cannot equal a numbered key. Raises
    ``RecordNotFoundError`` when neither matches.
    """
    raise NotImplementedError("STUB (P0-I4-T43)")


def search_records_impl(
    ctx: McpContext, *, scope: str, q: str, limit: int, offset: int, order_by: str | None
) -> SearchResult:
    """Records of ``scope`` matching the query text ``q``, one page, with the total count.

    ``q`` is the shared query language. Build the spec with ``tl_api.routes.records.build_spec``
    (it parses ``q`` and ``order_by`` exactly as ``GET /records`` does), then ``run_query`` and
    ``count_query``. Raises ``QuerySyntaxError`` or ``ApiError``; ``guarded`` maps both.
    """
    raise NotImplementedError("STUB (P0-I4-T43)")


def get_record_impl(ctx: McpContext, *, record: str, scope: str | None) -> dict[str, object]:
    """The record envelope for an id, or for a key with ``scope``."""
    raise NotImplementedError("STUB (P0-I4-T43)")


def get_links_impl(
    ctx: McpContext, *, record: str, scope: str | None, include_retracted: bool
) -> list[LinkView]:
    """Both directions of the record's links."""
    raise NotImplementedError("STUB (P0-I4-T43)")


def trace_impl(
    ctx: McpContext, *, record: str, scope: str | None, depth: int, direction: TraceDirection
) -> TraceNode:
    """The tree of records within ``depth`` link hops."""
    raise NotImplementedError("STUB (P0-I4-T43)")
