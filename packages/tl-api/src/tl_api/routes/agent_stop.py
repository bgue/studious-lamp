"""The per-agent stop switch over HTTP (P2-X2, ADR-0029 decision 6).

Three admin routes: stop an agent, resume it, list the stopped agents with the held count the
reader may see. Every route is admin-only (the guard actions are `admin.agents.*`, so the
`Authorizer` answers 403 `forbidden` to a `user` and to every agent). Thin: one
`tl_core.services.agent_stop` call per route inside `ctx.backend()`; the token's actor is the
command's actor. Refusals are the existing rows of `tl_api.errors` (403 `forbidden`, 404
`account_not_found`). The list reads through `confidentiality.current_viewer()`, so a held
proposal the reader may not read is neither counted nor named.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from tl_core import confidentiality
from tl_core.services.agent_stop import (
    MAX_REASON,
    AgentStopResult,
    ResumeAgent,
    StopAgent,
    StoppedAgent,
    handle_resume_agent,
    handle_stop_agent,
    list_stopped,
)

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["admin"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Stopper = Annotated[str, Depends(guard("admin.agents.stop"))]
Resumer = Annotated[str, Depends(guard("admin.agents.resume"))]
Lister = Annotated[str, Depends(guard("admin.agents.list"))]
AGENT_STOP_SOURCE = "api"
MAX_AGENT = 200


class AdminStopAgentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(max_length=MAX_AGENT, description="`agent:<name>`.")
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class AdminResumeAgentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(max_length=MAX_AGENT, description="`agent:<name>`.")


@router.post(
    "/admin/agents/stop",
    operation_id="admin_stop_agent",
    response_model=AgentStopResult,
)
def stop_agent(body: AdminStopAgentBody, ctx: Ctx, actor: Stopper) -> AgentStopResult:
    """Stop an agent: its new filings are refused and its pending proposals show as held.

    Stopping a stopped agent writes nothing: `changed: false`. Refusals: 403 `forbidden` (not an
    admin person), 404 `account_not_found` (an unknown agent or one that never filed).
    """
    command = StopAgent(actor=actor, source=AGENT_STOP_SOURCE, agent=body.agent, reason=body.reason)
    with ctx.backend() as uow:
        return handle_stop_agent(uow, command)


@router.post(
    "/admin/agents/resume",
    operation_id="admin_resume_agent",
    response_model=AgentStopResult,
)
def resume_agent(body: AdminResumeAgentBody, ctx: Ctx, actor: Resumer) -> AgentStopResult:
    """Resume a stopped agent. Resuming a running agent writes nothing: `changed: false`.

    Refusals: 403 `forbidden`, 404 `account_not_found`.
    """
    command = ResumeAgent(actor=actor, source=AGENT_STOP_SOURCE, agent=body.agent)
    with ctx.backend() as uow:
        return handle_resume_agent(uow, command)


@router.get(
    "/admin/agents/stopped",
    operation_id="admin_list_stopped_agents",
    response_model=list[StoppedAgent],
)
def list_stopped_agents(
    ctx: Ctx,
    actor: Lister,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[StoppedAgent]:
    """The agents stopped now, each with the held count the reader may see (ADR-0016)."""
    with ctx.backend(True) as uow:
        return list_stopped(uow.conn(), confidentiality.current_viewer(), limit=limit)
