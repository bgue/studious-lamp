"""The bodies of the four read tools (T43). ``server.py`` owns names, schemas and error handling.

Each function runs inside ``guarded`` (the authorise hook has been called and expected failures
are mapped), opens a read-only unit of work with ``ctx.factory(True)`` and calls one service.
"""

from __future__ import annotations

from tl_api.routes.records import build_spec
from tl_core.query import count_query, run_query
from tl_core.services import link_queries, link_trace, queries
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.link_queries import LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode
from tl_core.uow import UnitOfWork

from tl_mcp.context import McpContext
from tl_mcp.models import LakeQueryOutput, SearchResult


def resolve_record_id(uow: UnitOfWork, record: str, scope: str | None) -> str:
    """The id of ``record``, which is a record id or (with ``scope``) a record key.

    An id is tried first; ids are ULIDs and cannot equal a numbered key. Raises
    ``RecordNotFoundError`` when neither matches.
    """
    found = queries.get_record_by_id(uow, record)
    if found is None and scope is not None:
        found = queries.get_record(uow, scope, record)
    if found is None:
        where = f" in scope {scope!r}" if scope is not None else " (give `scope` to look up a key)"
        raise RecordNotFoundError(f"no record {record!r}{where}")
    return str(found["id"])


def search_records_impl(
    ctx: McpContext, *, scope: str, q: str, limit: int, offset: int, order_by: str | None
) -> SearchResult:
    """Records of ``scope`` matching the query text ``q``, one page, with the total count.

    ``q`` is the shared query language. Build the spec with ``tl_api.routes.records.build_spec``
    (it parses ``q`` and ``order_by`` exactly as ``GET /records`` does), then ``run_query`` and
    ``count_query``. Raises ``QuerySyntaxError`` or ``ApiError``; ``guarded`` maps both.
    """
    spec = build_spec(scope, q, limit=limit, offset=offset, order_by=order_by)
    with ctx.factory(True) as uow:
        return SearchResult(
            records=run_query(uow, spec),
            total=count_query(uow, spec),
            limit=limit,
            offset=offset,
        )


def get_record_impl(ctx: McpContext, *, record: str, scope: str | None) -> dict[str, object]:
    """The record envelope for an id, or for a key with ``scope``."""
    with ctx.factory(True) as uow:
        record_id = resolve_record_id(uow, record, scope)
        found = queries.get_record_by_id(uow, record_id)
        assert found is not None
    return found


def get_links_impl(
    ctx: McpContext, *, record: str, scope: str | None, include_retracted: bool
) -> list[LinkView]:
    """Both directions of the record's links."""
    with ctx.factory(True) as uow:
        record_id = resolve_record_id(uow, record, scope)
        return link_queries.links_of(uow, record_id, include_retracted=include_retracted)


def trace_impl(
    ctx: McpContext, *, record: str, scope: str | None, depth: int, direction: TraceDirection
) -> TraceNode:
    """The tree of records within ``depth`` link hops."""
    with ctx.factory(True) as uow:
        record_id = resolve_record_id(uow, record, scope)
        return link_trace.trace(uow, record_id, depth=depth, direction=direction)


def lake_query_impl(ctx: McpContext, *, sql: str, limit: int) -> LakeQueryOutput:
    """One guarded read-only SELECT over the lake, as the acting agent.

    ``ctx.lake`` refuses anything but one SELECT over lake tables (``GuardError``), caps rows and
    bytes, times out, and writes one audit line with ``caller=ctx.actor``.
    """
    result = ctx.lake.query(sql, limit=limit, caller=ctx.actor)
    return LakeQueryOutput(
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        truncated_by=result.truncated_by,
        limit=result.limit,
        as_of_seq=result.as_of_seq,
        snapshot_id=result.snapshot_id,
        as_of=result.as_of_line(),
    )
