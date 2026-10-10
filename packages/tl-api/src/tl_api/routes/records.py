"""Record reads: list and query, count, lookup by key, one record, its history (brief 11.1, 10.2).

The query language is parsed here with ``tl_core.query.parse``; a syntax error is the table's 400
``query_syntax`` with its position (O3). Listing always runs through ``run_query``, so ``q``,
``status``, ``record_type`` and ``order_by`` combine in one place.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from tl_core.ledger import Event
from tl_core.query import And, Compare, Expr, QuerySpec, count_query, parse, run_query
from tl_core.services import queries
from tl_core.services.errors import RecordNotFoundError

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError
from tl_api.models import CountOut, RecordOut

router = APIRouter(tags=["records"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("record.read"))]
ScopeParam = Annotated[str, Query(description="`company` or `project:<id>`.")]
QueryParam = Annotated[
    str | None,
    Query(description="Filter in the query language (`status:open linked:NCR`)."),
]
Direction = Literal["asc", "desc"]


def parse_order_by(text: str | None) -> list[tuple[str, Direction]]:
    """``"title:desc,psets.v.size"`` to ``[("title", "desc"), ("psets.v.size", "asc")]``.

    Items are separated by commas; each is a column or pset path, optionally followed by `:asc` or
    `:desc` (default asc). Blank or ``None`` gives ``[]``. Raises ``ApiError(422,
    "invalid_argument", ...)`` for an empty item or a direction other than asc or desc.
    """
    if text is None or not text.strip():
        return []
    ordering: list[tuple[str, Direction]] = []
    for item in text.split(","):
        column, _, direction = item.strip().partition(":")
        column = column.strip()
        direction = direction.strip().lower() or "asc"
        if not column or direction not in ("asc", "desc"):
            raise ApiError(
                422,
                "invalid_argument",
                f"order_by item {item!r} must be <column>[:asc|:desc]",
            )
        ordering.append((column, "asc" if direction == "asc" else "desc"))
    return ordering


def build_spec(
    scope: str,
    q: str | None,
    *,
    record_type: str | None = None,
    status: str | None = None,
    include_voided: bool = False,
    limit: int | None = 500,
    offset: int = 0,
    order_by: str | None = None,
) -> QuerySpec:
    """The ``QuerySpec`` for the request parameters. ``status`` is ANDed with the parsed ``q``.

    Raises ``QuerySyntaxError`` (from ``parse``) and ``ApiError`` 422 (from ``parse_order_by``).
    """
    where: Expr | None = parse(q) if q else None
    if status is not None:
        condition = Compare("status", "=", status)
        where = condition if where is None else And((where, condition))
    return QuerySpec(
        scope=scope,
        record_type=record_type,
        where=where,
        order_by=parse_order_by(order_by),
        limit=limit,
        offset=offset,
        include_voided=include_voided,
    )


@router.get("/records", operation_id="list_records")
def list_records(
    ctx: Ctx,
    actor: Reader,
    scope: ScopeParam,
    q: QueryParam = None,
    record_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query(description="Same as `status:<value>` in `q`.")] = None,
    include_voided: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    order_by: Annotated[
        str | None,
        Query(description="Comma-separated `column[:asc|:desc]`; psets as `psets.<pset>.<prop>`."),
    ] = None,
) -> list[RecordOut]:
    """Records of a scope, filtered by the query language, ordered and paged."""
    spec = build_spec(
        scope,
        q,
        record_type=record_type,
        status=status,
        include_voided=include_voided,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    try:
        with ctx.backend(True) as uow:
            rows = run_query(uow, spec)
    except ValueError as exc:  # an unknown order column
        raise ApiError(422, "invalid_argument", str(exc)) from exc
    return [RecordOut(**row) for row in rows]


@router.get("/records/count", operation_id="count_records")
def count_records(
    ctx: Ctx,
    actor: Reader,
    scope: ScopeParam,
    q: QueryParam = None,
    record_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    include_voided: Annotated[bool, Query()] = False,
) -> CountOut:
    """How many records match (`limit`, `offset` and ordering do not apply)."""
    spec = build_spec(
        scope,
        q,
        record_type=record_type,
        status=status,
        include_voided=include_voided,
    )
    with ctx.backend(True) as uow:
        return CountOut(count=count_query(uow, spec))


@router.get("/records/lookup", operation_id="lookup_record")
def lookup_record(
    ctx: Ctx,
    actor: Reader,
    scope: ScopeParam,
    key: Annotated[str, Query(description="The record's key, e.g. `P123-NCR-0042`.")],
    response: Response,
) -> RecordOut:
    """The record with this key in this scope (voided ones included). 404 when there is none."""
    with ctx.backend(True) as uow:
        row = queries.get_record(uow, scope, key)
    if row is None:
        raise RecordNotFoundError(f"no record with key {key!r} in scope {scope!r}")
    response.headers["ETag"] = f'"{row["version"]}"'
    return RecordOut(**row)


@router.get("/records/{record_id}", operation_id="get_record")
def get_record(ctx: Ctx, actor: Reader, record_id: str, response: Response) -> RecordOut:
    """One record by id. The `ETag` header is the stream version (brief 11.1)."""
    with ctx.backend(True) as uow:
        row = queries.get_record_by_id(uow, record_id)
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    response.headers["ETag"] = f'"{row["version"]}"'
    return RecordOut(**row)


@router.get("/records/{record_id}/history", operation_id="get_record_history")
def get_record_history(ctx: Ctx, actor: Reader, record_id: str) -> list[Event]:
    """Every event of the record's stream, oldest first. 404 when the record is unknown."""
    with ctx.backend(True) as uow:
        events = queries.record_history(uow, record_id)
    if not events:
        raise RecordNotFoundError(f"no record {record_id!r}")
    return events
