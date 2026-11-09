"""The weekly-plan and look-ahead reads of the awp module (P2-I5-T11a2): the plan list, one plan
with its commitments, the miss-reason keys and the look-ahead of a schedule snapshot joined with the
IWPs linked to each activity.

Thin: one call into the readers per route, through the request's viewer (set by the
authentication middleware). Every route needs the action ``document.read``. A missing, hidden or
voided plan answers the one 404 ``record_not_found`` with the one text ``no week <week>``. The
look-ahead's schedule and snapshot answer the schedule routes' 404s (``schedule_not_found``,
``snapshot_not_found``). Mounted before the ``awp`` router, as the other awp reads.
"""

from __future__ import annotations

import dataclasses
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from tl_core import confidentiality
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import week_views
from tl_mod_awp.look_ahead_view import look_ahead_view
from tl_mod_schedule import views as schedule_views

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["awp"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]
WEEK_PATTERN = r"^\d{4}-W\d{2}$"


class LookAheadRowBody(BaseModel):
    """One activity of the look-ahead window (``tl_mod_schedule.lookahead.LookAheadRow``)."""

    activity_id: str
    name: str
    wbs_path: str
    status: str
    phase: str
    early_start: str | None
    early_finish: str | None
    total_float_days: float | None
    critical: bool
    percent_complete: float


class LookAheadIwpBody(BaseModel):
    """One IWP linked to an activity of the window (``look_ahead_view.LookAheadIwp``)."""

    id: str
    number: str
    state: str
    planned_start: str | None
    need_by: str | None
    evaluated: bool
    ready: bool
    checks_ok: int
    checks_total: int
    open_blocking: int


class LookAheadItemBody(BaseModel):
    """One look-ahead row with the IWPs linked to its activity, by number."""

    row: LookAheadRowBody
    iwps: list[LookAheadIwpBody]


class LookAheadBody(BaseModel):
    """The look-ahead of a snapshot joined with its IWPs (``look_ahead_view.LookAheadView``)."""

    snapshot_key: str
    data_date: str
    window_start: str
    window_end: str
    weeks: int
    lead_weeks: int
    counts: dict[str, int]
    items: list[LookAheadItemBody]


@router.get("/projects/{project}/awp/weeks", operation_id="list_weekly_plans")
def list_weekly_plans(
    ctx: Ctx,
    actor: Reader,
    project: str,
    limit: Annotated[int, Query(ge=1, le=week_views.MAX_WEEKS)] = 60,
) -> list[week_views.WeekRow]:
    """The weekly plans of the project, the latest week first, those the viewer may read."""
    with ctx.backend(True) as uow:
        return week_views.list_weeks(
            uow.conn(), f"project:{project}", confidentiality.current_viewer(), limit=limit
        )


@router.get("/projects/{project}/awp/weeks/{week}", operation_id="get_weekly_plan")
def get_weekly_plan(
    ctx: Ctx,
    actor: Reader,
    project: str,
    week: Annotated[str, Path(pattern=WEEK_PATTERN, description="An ISO week, `YYYY-Www`.")],
) -> week_views.WeekDetail:
    """One weekly plan with its commitments. 404 `record_not_found` when the plan is missing,
    voided or hidden from the viewer (the same answer for all three)."""
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        conn = uow.conn()
        viewer = confidentiality.current_viewer()
        found = [
            r
            for r in week_views.list_weeks(conn, scope, viewer, limit=week_views.MAX_WEEKS)
            if r.week == week
        ]
        if not found:
            raise RecordNotFoundError(f"no week {week!r}")
        return week_views.week_detail(conn, found[0].id, viewer)


@router.get("/projects/{project}/awp/miss-reasons", operation_id="list_miss_reasons")
def list_miss_reasons(ctx: Ctx, actor: Reader, project: str) -> list[str]:
    """The keys of the miss-reason code list of the adopted awp edition (no labels)."""
    with ctx.backend(True) as uow:
        return week_views.miss_reasons(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/awp/look-ahead", operation_id="get_awp_look_ahead")
def get_awp_look_ahead(
    ctx: Ctx,
    actor: Reader,
    project: str,
    schedule: Annotated[str, Query(min_length=1, max_length=64, description="A schedule code.")],
    snapshot: Annotated[
        int | None,
        Query(ge=1, le=10**9, description="A snapshot number; the current one if omitted."),
    ] = None,
    weeks: Annotated[int, Query(ge=1, le=26)] = 4,
) -> LookAheadBody:
    """What is under way and what starts in the next `weeks` weeks of the data date, each row with
    the IWPs linked to its activity. 404 `schedule_not_found` or `snapshot_not_found`; 409 when the
    snapshot is not built."""
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        conn = uow.conn()
        found = schedule_views.find_snapshot(
            conn, schedule_views.find_schedule(conn, scope, schedule), snapshot, built=True
        )
        view = look_ahead_view(conn, scope, found, confidentiality.current_viewer(), weeks=weeks)
        return LookAheadBody.model_validate(dataclasses.asdict(view))
