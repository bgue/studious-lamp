"""The review queue: list and show proposals, accept or reject one (brief 11.3, 18.12).

Agents propose through MCP (``tl_mcp``); a person decides here. Accepting runs the stored command as
the token's actor with ``source`` ``mcp:<agent>`` (``tl_core.services.proposals``). A command that
is refused on accept is answered 200 with the proposal in status ``failed`` and the error in
``reason``: the decision was recorded, and the person sees why it did not apply. An agent token is
refused with 403 ``proposal_decider``; that is the meaning of "a person accepts", not a permission
model (ADR-0005).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from tl_core.proposals.types import ProposalStatus, ProposalView
from tl_core.services import proposals
from tl_core.util import effective_time

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_api.effective import EFFECTIVE_AT_HEADER, resolve_effective_at

router = APIRouter(tags=["proposals"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("proposal.read"))]
Acceptor = Annotated[str, Depends(guard("proposal.accept"))]
Rejector = Annotated[str, Depends(guard("proposal.reject"))]
API_SOURCE = "api"


class AcceptBody(BaseModel):
    """Body of ``POST /proposals/{id}/accept``."""

    model_config = ConfigDict(extra="forbid")

    roles: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list,
        max_length=20,
        description="Workflow roles the accepting person holds (a stub until auth, brief 8).",
    )


class RejectBody(BaseModel):
    """Body of ``POST /proposals/{id}/reject``."""

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=proposals.MAX_REASON)]


@router.get("/proposals", operation_id="list_proposals")
def list_proposals(
    ctx: Ctx,
    actor: Reader,
    scope: Annotated[str, Query(min_length=1, max_length=128, description="Scope of the queue.")],
    status: Annotated[ProposalStatus, Query(description="Only this status.")] = "pending",
    agent: Annotated[str | None, Query(max_length=128, description="Only this proposer.")] = None,
    all_statuses: Annotated[
        bool, Query(alias="all", description="Every status; `status` is then ignored.")
    ] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ProposalView]:
    """Proposals of a scope, oldest first (the order to review them in)."""
    with ctx.backend(True) as uow:
        return proposals.list_proposals(
            uow.conn(), scope, status=None if all_statuses else status, agent=agent, limit=limit
        )


@router.get("/proposals/{proposal_id}", operation_id="get_proposal")
def get_proposal(
    ctx: Ctx,
    actor: Reader,
    proposal_id: str,
    scope: Annotated[
        str, Query(min_length=1, max_length=128, description="The scope of the queue it is in.")
    ],
) -> ProposalView:
    """One proposal with the command it carries; 404 when it is in another scope."""
    with ctx.backend(True) as uow:
        return proposals.get_proposal(uow.conn(), proposal_id, scope=scope)


SimulatedTime = Annotated[
    str | None,
    Header(
        alias=EFFECTIVE_AT_HEADER,
        description="Simulated time stamped as the decision's (and the accepted command's) "
        "effective_at. Accepted only when the proposal is in a simulation scope "
        "`project:sim-<run>`; any other scope is a 400 `effective_time_forbidden`.",
    ),
]


def simulated_time(ctx: ApiContext, proposal_id: str, header: str | None) -> datetime | None:
    """The instant ``X-TL-Effective-At`` asks for, checked against the proposal's own scope."""
    if header is None:
        return None
    with ctx.backend(True) as uow:
        scope = proposals.get_proposal(uow.conn(), proposal_id).scope
    return resolve_effective_at(header, scope)


@router.post("/proposals/{proposal_id}/accept", operation_id="accept_proposal")
def accept_proposal(
    ctx: Ctx,
    actor: Acceptor,
    proposal_id: str,
    effective_at: SimulatedTime = None,
    body: AcceptBody | None = None,
) -> ProposalView:
    """Run the proposal's command as the caller and record the decision.

    The answer has `status` `accepted`, or `failed` with the refusal in `reason` when the command
    could not be applied (the record changed, a guard failed); nothing of the command is kept then.
    """
    roles = body.roles if body is not None else []
    when = simulated_time(ctx, proposal_id, effective_at)
    with effective_time(when):
        return proposals.accept_or_fail(
            ctx.backend, proposal_id=proposal_id, by=actor, roles=roles, source=API_SOURCE
        )


@router.post("/proposals/{proposal_id}/reject", operation_id="reject_proposal")
def reject_proposal(
    ctx: Ctx,
    actor: Rejector,
    proposal_id: str,
    body: RejectBody,
    effective_at: SimulatedTime = None,
) -> ProposalView:
    """Reject a pending proposal with a reason. The command never runs."""
    when = simulated_time(ctx, proposal_id, effective_at)
    with effective_time(when), ctx.backend(False) as uow:
        return proposals.reject_proposal(
            uow, proposal_id=proposal_id, by=actor, reason=body.reason, source=API_SOURCE
        )
