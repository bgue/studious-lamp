"""The awp progress and count reads (P2-I5-T11a1): the IWP log counts, one IWP's earned progress,
the progress roll-up, the two KPI tiles and the record hash a sign-off carries.

Thin: one call into the awp readers per route, through the request's viewer (set by the
authentication middleware). Every route needs the action ``document.read``. A missing or hidden IWP
answers the one 404 ``record_not_found``, the same text for both. Mounted before the ``awp`` router
so that ``iwps/counts`` is not read as an IWP number.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from tl_core import confidentiality
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import iwp_views
from tl_mod_awp.handlers.signoff import iwp_record_hash
from tl_mod_awp.iwp_counts import IwpCountRow, iwp_counts
from tl_mod_awp.kpis import KpiTile, kpi_rows
from tl_mod_awp.progress import engine
from tl_mod_awp.progress.rollup import progress_rollup

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["awp"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]


class ProgressItem(BaseModel):
    """One scope item of an IWP: its key, earned percent, the steps earned and the hours."""

    key: str
    pct: Decimal
    steps: list[str]
    hours: Decimal | None


class IwpProgress(BaseModel):
    """The earned progress of one IWP (the stored figure, the items the viewer may open)."""

    number: str
    pct: Decimal
    edition: str
    items: list[ProgressItem]
    notes: list[str]


class CwpRollupRow(BaseModel):
    """Earned and planned hours of one CWP by its key."""

    key: str
    iwps: int
    earned_hours: Decimal
    hours: Decimal


class NodeRollupRow(BaseModel):
    """Earned hours of one WBS node against its budget (percent None without a budget)."""

    earned_hours: Decimal
    budget_hours: Decimal | None
    pct: Decimal | None


class CostLineRollupRow(BaseModel):
    """Earned hours of one cost code against its budget; ``code`` None is the unallocated line."""

    code: str | None
    earned_hours: Decimal
    budget_hours: Decimal | None


class RollupBody(BaseModel):
    """The progress roll-up of a project (``progress.rollup.ProgressRollup``)."""

    scope: str
    as_of_seq: int
    cwps: list[CwpRollupRow]
    nodes: list[NodeRollupRow]
    lines: list[CostLineRollupRow]
    notes: list[str]


class IwpHash(BaseModel):
    """The record hash an IWP sign-off carries (SHA-256, hex)."""

    number: str
    record_hash: str


@router.get("/projects/{project}/awp/iwps/counts", operation_id="list_iwp_counts")
def list_iwp_counts(ctx: Ctx, actor: Reader, project: str) -> list[IwpCountRow]:
    """The IWP log counts by number: Ready checks, open blocking constraints and the state-since
    date, for the viewer-visible IWPs (at most 500). A hidden IWP is absent."""
    with ctx.backend(True) as uow:
        return iwp_counts(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/awp/iwps/{number}/progress", operation_id="get_iwp_progress")
def get_iwp_progress(ctx: Ctx, actor: Reader, project: str, number: str) -> IwpProgress:
    """The earned progress of one IWP. 404 `record_not_found` when it is missing or hidden."""
    with ctx.backend(True) as uow:
        conn = uow.conn()
        detail = iwp_views.iwp_detail(conn, f"project:{project}", number)
        if detail is None:
            raise RecordNotFoundError(f"no IWP {number!r}")
        earned = engine.earned_fraction(conn, detail.id, viewer=confidentiality.current_viewer())
        return IwpProgress(
            number=detail.number,
            pct=earned.pct,
            edition=earned.edition,
            items=[
                ProgressItem(key=i.key, pct=i.pct, steps=list(i.steps), hours=i.hours)
                for i in earned.items
            ],
            notes=list(earned.notes),
        )


@router.get("/projects/{project}/awp/progress/rollup", operation_id="get_progress_rollup")
def get_progress_rollup(ctx: Ctx, actor: Reader, project: str) -> RollupBody:
    """The earned hours of the project by CWP, WBS node and cost code, through the viewer's
    class filter."""
    with ctx.backend(True) as uow:
        found = progress_rollup(
            uow.conn(), f"project:{project}", viewer=confidentiality.current_viewer()
        )
        return RollupBody.model_validate(dataclasses.asdict(found))


@router.get("/projects/{project}/awp/kpis", operation_id="list_kpis")
def list_kpis(ctx: Ctx, actor: Reader, project: str) -> list[KpiTile]:
    """The two KPI tiles: PPC and percent constraint-free, in their fixed order."""
    with ctx.backend(True) as uow:
        return kpi_rows(uow.conn(), f"project:{project}", confidentiality.current_viewer())


@router.get("/projects/{project}/awp/iwps/{number}/hash", operation_id="get_iwp_hash")
def get_iwp_hash(ctx: Ctx, actor: Reader, project: str, number: str) -> IwpHash:
    """The record hash of one IWP, the value a sign-off carries. 404 `record_not_found` when the
    IWP is missing or hidden (the same answer as the progress read)."""
    with ctx.backend(True) as uow:
        conn = uow.conn()
        detail = iwp_views.iwp_detail(conn, f"project:{project}", number)
        if detail is None:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return IwpHash(number=detail.number, record_hash=iwp_record_hash(conn, detail.id))
