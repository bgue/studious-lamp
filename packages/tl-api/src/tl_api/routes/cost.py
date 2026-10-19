"""Reads of the cost module: cost codes with their figures, and the snapshots (P1-I4).

Thin: one call into ``tl_mod_cost.views`` per route. The one write is the module's command
``POST /commands/ImportCostSnapshot`` (admin: the figures are money; the body is limited like every
command body, so a larger file is imported with ``tl cost import``). Every read needs the action
``document.read``, which agents hold because they only read.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_mod_cost import views

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["cost"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]


@router.get("/projects/{project}/cost-snapshots", operation_id="list_cost_snapshots")
def list_cost_snapshots(ctx: Ctx, actor: Reader, project: str) -> list[views.CostSnapshotView]:
    """A project's cost snapshots, newest period and revision first."""
    with ctx.backend(True) as uow:
        return views.cost_snapshots(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/cost-codes", operation_id="list_cost_codes")
def list_cost_codes(
    ctx: Ctx,
    actor: Reader,
    project: str,
    parent: Annotated[str | None, Query(max_length=64, description="Direct children of.")] = None,
    q: Annotated[str | None, Query(max_length=200, description="In the code or the title.")] = None,
    limit: Annotated[int, Query(ge=1, le=views.MAX_CODES)] = 1000,
) -> list[views.CostCodeView]:
    """A project's cost codes by code with the latest figures stated for each."""
    with ctx.backend(True) as uow:
        return views.cost_codes(
            uow.conn(), f"project:{project}", parent=parent, search=q, limit=limit
        )


@router.get("/projects/{project}/cost-codes/{code:path}", operation_id="get_cost_code")
def get_cost_code(ctx: Ctx, actor: Reader, project: str, code: str) -> views.CostCodeDetailView:
    """One cost code, its children and the figures of every snapshot. 404 `cost_code_not_found`."""
    with ctx.backend(True) as uow:
        return views.cost_code_detail(uow.conn(), f"project:{project}", code)
