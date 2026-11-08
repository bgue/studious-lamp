"""Insights: the Checks read of one record and the one telemetry write (ADR-0028).

``GET /records/{id}/checks`` reads five existing sources through ``record_checks`` and writes
nothing; a hidden record answers as an unknown one. ``POST /insights/needs`` appends one row of
``telemetry_need`` (ids and words, no content). The viewer role and the actor come from the token,
never the body; an ``agent:`` token is refused, and the action is in no agent allow-list.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_principal
from tl_core.auth.types import Principal
from tl_core.insights.checks import record_checks, record_facts
from tl_core.insights.types import CheckFinding
from tl_core.services.errors import RecordNotFoundError
from tl_core.telemetry import note_need, role_word

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError
from tl_api.insights_sources import sources_for
from tl_api.ratelimit import SourceLimiter

router = APIRouter(tags=["insights"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("record.read"))]
#: Not in any agent allow-list (``tl_core.auth.provider.AGENT_ACTIONS``): closed to agents.
NEED_ACTION = "insights.note_need"
Noter = Annotated[str, Depends(guard(NEED_ACTION))]
Who = Annotated[Principal, Depends(current_principal)]

NEEDS_PER_WINDOW = 30
NEEDS_WINDOW_S = 600.0
#: Process-local sliding window per actor (a second layer, as ``tl_api.ratelimit``).
NEED_LIMITER = SourceLimiter(NEEDS_PER_WINDOW, NEEDS_WINDOW_S)


class NeedIn(BaseModel):
    """What a screen may say about a need: kind, trigger, type and, for a request, a record."""

    model_config = ConfigDict(extra="forbid")

    request_kind: str
    trigger: str
    record_type: str
    record_id: str | None = None


@router.get("/records/{record_id}/checks", operation_id="get_record_checks")
def get_record_checks(ctx: Ctx, actor: Reader, who: Who, record_id: str) -> list[CheckFinding]:
    """What needs attention on the record, from five sources. 404 `record_not_found` when the
    record is unknown or hidden from the caller (the same body)."""
    with ctx.backend(True) as uow:
        facts = record_facts(uow.conn(), record_id)
        if facts is None:
            raise RecordNotFoundError(f"no record {record_id!r}")
        sources = sources_for(uow.conn(), holder_for_principal(who), facts.scope)
        return record_checks(uow.conn(), facts, sources)


@router.post("/insights/needs", operation_id="note_need", status_code=204)
def post_need(ctx: Ctx, actor: Noter, who: Who, body: NeedIn) -> Response:
    """Record that a need was shown. 403 for an agent token, 429 `rate_limited` past 30 in 10
    minutes per actor, 204 otherwise (also when the write itself failed: it is never the caller's
    problem)."""
    if who.kind == "agent" or actor.startswith("agent:"):
        raise ApiError(403, "forbidden", "not open to agents")
    if NEED_LIMITER.retry_after(actor) > 0:
        raise ApiError(429, "rate_limited", "too many requests")
    NEED_LIMITER.record_failure(actor)  # counts this request
    with ctx.backend(False) as uow:
        conn = uow.conn()
        scope: str | None = None
        record_id = body.record_id
        if record_id is not None:
            row = conn.execute(
                text("SELECT scope FROM cur_core_record WHERE id = :id"), {"id": record_id}
            ).first()
            if row is None or confidentiality.is_hidden(conn, record_id):
                record_id = None  # unknown and hidden alike: no id, no answer that differs
            else:
                scope = str(row.scope)
        try:
            note_need(
                conn,
                request_kind=body.request_kind,
                trigger=body.trigger,
                record_type=body.record_type,
                viewer_role=role_word(who.roles),
                outcome="shown",
                scope=scope,
                record_id=record_id,
            )
        except ValueError as exc:
            raise ApiError(422, "invalid_argument", str(exc)) from exc
    return Response(status_code=204)
