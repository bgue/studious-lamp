"""What happened around a record (P2-INS-S1, INS-A1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_core.insights.activity import record_activity
from tl_core.insights.types import ActivityPage
from tl_core.services import queries
from tl_core.services.errors import RecordNotFoundError

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["records"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
#: Closed to agents until someone allows it (``AGENT_ACTIONS`` does not list it).
Reader = Annotated[str, Depends(guard("activity.read"))]


@router.get("/records/{record_id}/activity", operation_id="get_record_activity")
def get_record_activity(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    revisions_only: bool = False,
    related: bool = True,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 120,
) -> ActivityPage:
    """The record's events, its thread, links, files, proposals, constraints and readiness checks,
    newest first, with one hop of causal events of linked records. 404 when the record is unknown
    or the reader may not read it (the same answer as ``/history``)."""
    with ctx.backend(True) as uow:
        if queries.get_record_by_id(uow, record_id) is None:
            raise RecordNotFoundError(f"no record {record_id!r}")
        return record_activity(
            uow,
            record_id,
            revisions_only=revisions_only,
            related=related,
            before_seq=before_seq,
            limit=limit,
        )
