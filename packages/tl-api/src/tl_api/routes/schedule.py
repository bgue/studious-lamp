"""Reads of the schedule module: schedules, snapshots, activities, comparison, links (P1-I4).

Thin, like the document reads: one call into ``tl_mod_schedule.views`` per route. Writes are the
module's commands (``POST /commands/DefineSchedule``, ``OpenScheduleSnapshot``,
``StartScheduleSnapshot``, ``PublishScheduleSnapshot`` and the rest; ``tl_mod_schedule.commands``
has their access levels); the XER file itself goes up through the file routes, slot ``xer``.
Every read needs the action ``document.read``, which agents hold because they only read. A P6
activity id may hold ``/``, so the routes that take one use a path parameter and a distinct
prefix, as ``document-diffs`` does.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from tl_mod_schedule import views
from tl_mod_schedule.compare import Comparison
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.resolver import ActivityLink, OrphanedLink, Resolution

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["schedule"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]
Snapshot = Annotated[
    int | None, Query(ge=1, le=10**9, description="A snapshot number; the current one if omitted.")
]


@router.get("/projects/{project}/schedules", operation_id="list_schedules")
def list_schedules(ctx: Ctx, actor: Reader, project: str) -> list[views.ScheduleView]:
    """A project's schedules by code, without snapshots."""
    with ctx.backend(True) as uow:
        return views.schedule_views(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/schedules/{code}", operation_id="get_schedule")
def get_schedule(ctx: Ctx, actor: Reader, project: str, code: str) -> views.ScheduleDetailView:
    """One schedule with its snapshots, newest first. 404 `schedule_not_found`."""
    with ctx.backend(True) as uow:
        return views.schedule_detail(uow.conn(), f"project:{project}", code)


@router.get(
    "/projects/{project}/schedules/{code}/snapshots/{number}", operation_id="get_schedule_snapshot"
)
def get_schedule_snapshot(
    ctx: Ctx,
    actor: Reader,
    project: str,
    code: str,
    number: Annotated[int, Path(ge=1, le=10**9)],
) -> views.SnapshotView:
    """One snapshot by number. 404 `snapshot_not_found`."""
    with ctx.backend(True) as uow:
        return views.snapshot_view(uow.conn(), f"project:{project}", code, number)


@router.get("/projects/{project}/schedules/{code}/activities", operation_id="list_activities")
def list_activities(
    ctx: Ctx,
    actor: Reader,
    project: str,
    code: str,
    snapshot: Snapshot = None,
    critical: Annotated[bool | None, Query()] = None,
    status: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=200, description="In the id or the name.")] = None,
    limit: Annotated[int, Query(ge=1, le=views.MAX_PAGE)] = 200,
    offset: Annotated[int, Query(ge=0, le=10**7)] = 0,
) -> views.ActivityPage:
    """A page of a built snapshot's activities in file order. 409 `snapshot_state` if unbuilt."""
    with ctx.backend(True) as uow:
        return views.activity_page(
            uow.conn(),
            f"project:{project}",
            code,
            snapshot,
            critical=critical,
            status=status,
            search=q,
            limit=limit,
            offset=offset,
        )


@router.get("/projects/{project}/schedules/{code}/comparison", operation_id="compare_snapshots")
def compare_snapshots(
    ctx: Ctx,
    actor: Reader,
    project: str,
    code: str,
    new: Snapshot = None,
    old: Annotated[
        int | None, Query(ge=1, le=10**9, description="Default: the one before.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=views.MAX_COMPARE_LIMIT)] = views.DEFAULT_COMPARE_LIMIT,
) -> Comparison:
    """What changed between two built snapshots, each list cut to `limit` rows with the totals."""
    with ctx.backend(True) as uow:
        return views.comparison(uow.conn(), f"project:{project}", code, new, old, limit=limit)


@router.get("/projects/{project}/schedules/{code}/look-ahead", operation_id="get_look_ahead")
def get_look_ahead(
    ctx: Ctx,
    actor: Reader,
    project: str,
    code: str,
    snapshot: Snapshot = None,
    weeks: Annotated[int, Query(ge=1, le=26)] = 4,
) -> LookAhead:
    """What is under way and what starts in the next `weeks` weeks of the data date."""
    with ctx.backend(True) as uow:
        return views.look_ahead_view(uow.conn(), f"project:{project}", code, snapshot, weeks)


@router.get("/projects/{project}/schedules/{code}/orphans", operation_id="list_orphaned_links")
def list_orphaned_links(ctx: Ctx, actor: Reader, project: str, code: str) -> list[OrphanedLink]:
    """Links the last publication flagged because their activity left the schedule."""
    with ctx.backend(True) as uow:
        return views.orphans(uow.conn(), f"project:{project}", code)


@router.get(
    "/projects/{project}/schedules/{code}/activity-details/{activity_id:path}",
    operation_id="get_schedule_activity",
)
def get_schedule_activity(
    ctx: Ctx, actor: Reader, project: str, code: str, activity_id: str, snapshot: Snapshot = None
) -> views.ActivityDetail:
    """One activity with its predecessors and successors. 404 `activity_not_found`."""
    with ctx.backend(True) as uow:
        return views.activity_detail(uow.conn(), f"project:{project}", code, activity_id, snapshot)


@router.get(
    "/projects/{project}/schedules/{code}/activity-trends/{activity_id:path}",
    operation_id="get_activity_trend",
)
def get_activity_trend(
    ctx: Ctx, actor: Reader, project: str, code: str, activity_id: str
) -> list[views.TrendPoint]:
    """The activity's float and dates in every published snapshot, oldest first."""
    with ctx.backend(True) as uow:
        return views.float_trend(uow.conn(), f"project:{project}", code, activity_id)


@router.get(
    "/projects/{project}/schedules/{code}/activity-resolutions/{activity_id:path}",
    operation_id="resolve_activity",
)
def resolve_activity(
    ctx: Ctx,
    actor: Reader,
    project: str,
    code: str,
    activity_id: str,
    as_of: Annotated[
        str | None,
        Query(
            max_length=40,
            description="A snapshot number, a date (YYYY-MM-DD), a minute, or `current`.",
        ),
    ] = None,
) -> Resolution:
    """What the activity is now, or as of a snapshot or a date (`state` says which it is)."""
    with ctx.backend(True) as uow:
        return views.resolution(
            uow.conn(), f"project:{project}", code, activity_id, views.as_of_of(as_of)
        )


@router.get("/records/{record_id}/activity-links", operation_id="list_activity_links")
def list_activity_links(ctx: Ctx, actor: Reader, record_id: str) -> list[ActivityLink]:
    """The activity links of a record and what each resolves to now."""
    with ctx.backend(True) as uow:
        return views.activity_links(uow.conn(), record_id)
