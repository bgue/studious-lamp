# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""Schedule and cost read tools: schedules, snapshots, comparison, look-ahead, cost codes (T13).

Thirteen read-only tools. An agent that helps a planner needs to know what the current schedule
says, what changed since the last update, which activity a record points at and what has gone
stale; these answer from the module's views, so an agent, the API and a screen see the same
fields. None of them writes: publishing a snapshot is proposed with
``propose_publish_schedule_snapshot`` (``tl_mcp.schedule_tools``) and a document controller
accepts it. Every tool names its resource for the authorizer (``guarded``), so reading needs
``document.read`` like the other reads.


STUB (P1-I4-T13): the bodies of the thirteen `*_impl` functions are `NotImplementedError`; the
tools in `register_schedule_read_tools` (names, argument bounds, descriptions, the `guarded`
authorizer call) are written and call them. The ticket fills the bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_mod_cost import views as cost_views
from tl_mod_schedule import views
from tl_mod_schedule.compare import Comparison
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.resolver import ActivityLink, OrphanedLink, Resolution

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Schedule = Annotated[
    str, Field(min_length=1, max_length=MAX_PART, description="The schedule's code, `MAIN`.")
]
ActivityId = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The P6 activity id, `A1230`."),
]
Snapshot = Annotated[
    int | None,
    Field(ge=1, le=10**9, description="A snapshot number (default: the current snapshot)."),
]


def list_schedules_impl(ctx: McpContext, *, project: str) -> list[views.ScheduleView]:
    """The project's schedules by code, without snapshots."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.schedule_views(conn, scope)`.
    raise NotImplementedError


def get_schedule_impl(ctx: McpContext, *, project: str, schedule: str) -> views.ScheduleDetailView:
    """One schedule with its snapshots, newest first."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.schedule_detail(conn, scope, schedule)`.
    raise NotImplementedError


def list_activities_impl(
    ctx: McpContext,
    *,
    project: str,
    schedule: str,
    snapshot: int | None,
    critical: bool,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> views.ActivityPage:
    """A page of the activities of a built snapshot, in file order."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.activity_page(conn, scope, schedule,
    #    snapshot, critical=..., status=status, search=search, limit=limit, offset=offset)`;
    #    pass `critical=True` when `critical` is true and `None` otherwise (`False` would
    #    ask for the non-critical ones).
    raise NotImplementedError


def get_activity_impl(
    ctx: McpContext, *, project: str, schedule: str, activity_id: str, snapshot: int | None
) -> views.ActivityDetail:
    """One activity with its predecessors and successors."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.activity_detail(conn, scope, schedule,
    #    activity_id, snapshot)`.
    raise NotImplementedError


def compare_impl(
    ctx: McpContext,
    *,
    project: str,
    schedule: str,
    new: int | None,
    old: int | None,
    limit: int,
) -> Comparison:
    """What changed from ``old`` to ``new`` (default: the current snapshot and the one before)."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.comparison(conn, scope, schedule, new, old,
    #    limit=limit)`.
    raise NotImplementedError


def look_ahead_impl(
    ctx: McpContext, *, project: str, schedule: str, snapshot: int | None, weeks: int
) -> LookAhead:
    """What is under way or starts within ``weeks`` weeks of the snapshot's data date."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.look_ahead_view(conn, scope, schedule,
    #    snapshot, weeks)`.
    raise NotImplementedError


def resolve_impl(
    ctx: McpContext, *, project: str, schedule: str, activity_id: str, as_of: str | None
) -> Resolution:
    """What an activity id is now, or as of a snapshot number or a date."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.resolution(conn, scope, schedule,
    #    activity_id, views.as_of_of(as_of))`; `as_of_of` turns the text into what the view
    #    takes.
    raise NotImplementedError


def trend_impl(
    ctx: McpContext, *, project: str, schedule: str, activity_id: str
) -> list[views.TrendPoint]:
    """One activity's float and dates in every published snapshot, oldest first."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.float_trend(conn, scope, schedule,
    #    activity_id)`.
    raise NotImplementedError


def orphans_impl(ctx: McpContext, *, project: str, schedule: str) -> list[OrphanedLink]:
    """The links whose activity is not in the current snapshot."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.orphans(conn, scope, schedule)`.
    raise NotImplementedError


def record_links_impl(ctx: McpContext, *, project: str, record_id: str) -> list[ActivityLink]:
    """The activity links of one record and what each resolves to now."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `views.activity_links(conn, scope, record_id)`.
    raise NotImplementedError


def list_cost_codes_impl(
    ctx: McpContext, *, project: str, parent: str | None, search: str | None, limit: int
) -> list[cost_views.CostCodeView]:
    """The project's cost codes by code with their latest figures."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `cost_views.cost_codes(conn, scope, parent=parent,
    #    search=search, limit=limit)`.
    raise NotImplementedError


def get_cost_code_impl(
    ctx: McpContext, *, project: str, code: str
) -> cost_views.CostCodeDetailView:
    """One cost code with its children and the figures of every snapshot."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `cost_views.cost_code_detail(conn, scope, code)`.
    raise NotImplementedError


def list_cost_snapshots_impl(ctx: McpContext, *, project: str) -> list[cost_views.CostSnapshotView]:
    """The project's imported cost periods, newest first."""
    # STEPS
    # 1. Open `with ctx.factory(True) as uow:` (the `True` is read-only), call the view with
    #    `uow.conn()` and the scope `f"project:{project}"`, and return its result from
    #    inside the `with`. The view is `cost_views.cost_snapshots(conn, scope)`.
    raise NotImplementedError


def register_schedule_read_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the thirteen read tools to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_schedules(project: Project) -> list[views.ScheduleView]:
        """List a project's P6 schedules (brief 9 M11) by code.

        Each row has the schedule's type, its current snapshot number and data date, and how many
        snapshots it has. Use `get_schedule` for the snapshots themselves.
        """
        with guarded(ctx, "list_schedules", resource_name("schedules", project)):
            return list_schedules_impl(ctx, project=project)

    @server.tool(annotations=READ_ONLY)
    def get_schedule(project: Project, schedule: Schedule) -> views.ScheduleDetailView:
        """Get one schedule with its snapshots, newest first.

        A snapshot is one uploaded XER file: its state (`Valid`, `Published`, `Superseded`,
        `Invalid`, ...), data date, counts and the problems found. `links_being_checked` is true
        for a short while after a publication: links to activities that left the schedule may
        still read as current until the worker has flagged them.
        """
        with guarded(ctx, "get_schedule", resource_name("schedule", project, schedule)):
            return get_schedule_impl(ctx, project=project, schedule=schedule)

    @server.tool(annotations=READ_ONLY)
    def list_schedule_activities(
        project: Project,
        schedule: Schedule,
        snapshot: Snapshot = None,
        critical: Annotated[bool, Field(description="Only critical activities.")] = False,
        status: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="`not_started`, `in_progress` or `completed`."),
        ] = None,
        search: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Text in the activity id or name."),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=1000, description="Rows in the page.")] = 200,
        offset: Annotated[int, Field(ge=0, le=10**7, description="Rows to skip.")] = 0,
    ) -> views.ActivityPage:
        """List the activities of a schedule snapshot (default: the current one), in file order.

        Durations and floats are in hours, as P6 writes them. `total` is how many matched in all.
        """
        with guarded(ctx, "list_schedule_activities", resource_name("schedule", project, schedule)):
            return list_activities_impl(
                ctx,
                project=project,
                schedule=schedule,
                snapshot=snapshot,
                critical=critical,
                status=status,
                search=search,
                limit=limit,
                offset=offset,
            )

    @server.tool(annotations=READ_ONLY)
    def get_schedule_activity(
        project: Project, schedule: Schedule, activity_id: ActivityId, snapshot: Snapshot = None
    ) -> views.ActivityDetail:
        """Get one activity of a snapshot with its predecessors and successors."""
        with guarded(ctx, "get_schedule_activity", resource_name("schedule", project, schedule)):
            return get_activity_impl(
                ctx, project=project, schedule=schedule, activity_id=activity_id, snapshot=snapshot
            )

    @server.tool(annotations=READ_ONLY)
    def compare_schedule_snapshots(
        project: Project,
        schedule: Schedule,
        new: Snapshot = None,
        old: Snapshot = None,
        limit: Annotated[int, Field(ge=1, le=5000, description="Rows kept per list.")] = 200,
    ) -> Comparison:
        """Compare two snapshots of a schedule (default: the current one with the one before).

        Returns activities added and removed, date shifts in calendar days (positive is later),
        total-float changes in days (negative is erosion), logic changes, progress changes,
        activities that entered or left the critical set and the shift of the latest early
        finish. `totals` has the full count of each list; `cut` says whether a list was limited.
        Use it before proposing to publish a snapshot.
        """
        with guarded(
            ctx, "compare_schedule_snapshots", resource_name("schedule", project, schedule)
        ):
            return compare_impl(
                ctx, project=project, schedule=schedule, new=new, old=old, limit=limit
            )

    @server.tool(annotations=READ_ONLY)
    def get_look_ahead(
        project: Project,
        schedule: Schedule,
        snapshot: Snapshot = None,
        weeks: Annotated[int, Field(ge=1, le=26, description="Weeks to look ahead.")] = 4,
    ) -> LookAhead:
        """Get the look-ahead of a snapshot: what is under way, late to start, or starting soon.

        The window starts at the snapshot's data date, not at today's date. Each row has its
        phase (`in_progress`, `late_start`, `starting`), dates and float in days.
        """
        with guarded(ctx, "get_look_ahead", resource_name("schedule", project, schedule)):
            return look_ahead_impl(
                ctx, project=project, schedule=schedule, snapshot=snapshot, weeks=weeks
            )

    @server.tool(annotations=READ_ONLY)
    def resolve_schedule_activity(
        project: Project,
        schedule: Schedule,
        activity_id: ActivityId,
        as_of: Annotated[
            str | None,
            Field(
                max_length=MAX_PART,
                description="`current` (default), a snapshot number, or a date `YYYY-MM-DD`.",
            ),
        ] = None,
    ) -> Resolution:
        """Say what an activity id is now, or as of a snapshot or a date.

        `state` is `current`, `as_of`, `orphaned` (it left the schedule), `unknown_activity` or
        `no_snapshot`; the activity's fields come with it when it exists.
        """
        with guarded(
            ctx, "resolve_schedule_activity", resource_name("schedule", project, schedule)
        ):
            return resolve_impl(
                ctx, project=project, schedule=schedule, activity_id=activity_id, as_of=as_of
            )

    @server.tool(annotations=READ_ONLY)
    def get_activity_float_trend(
        project: Project, schedule: Schedule, activity_id: ActivityId
    ) -> list[views.TrendPoint]:
        """Follow one activity's total float and dates through every published snapshot."""
        with guarded(ctx, "get_activity_float_trend", resource_name("schedule", project, schedule)):
            return trend_impl(ctx, project=project, schedule=schedule, activity_id=activity_id)

    @server.tool(annotations=READ_ONLY)
    def list_orphaned_links(project: Project, schedule: Schedule) -> list[OrphanedLink]:
        """List the links to activities that are no longer in the current snapshot.

        These links were flagged stale when a snapshot without the activity was published. A link
        a person flagged is not listed here.
        """
        with guarded(ctx, "list_orphaned_links", resource_name("schedule", project, schedule)):
            return orphans_impl(ctx, project=project, schedule=schedule)

    @server.tool(annotations=READ_ONLY)
    def get_record_activity_links(
        project: Project,
        record_id: Annotated[
            str, Field(min_length=26, max_length=26, description="The record's id (26 characters).")
        ],
    ) -> list[ActivityLink]:
        """List the schedule activities a record is linked to and what each resolves to now."""
        with guarded(ctx, "get_record_activity_links", resource_name("record", project, record_id)):
            return record_links_impl(ctx, project=project, record_id=record_id)

    @server.tool(annotations=READ_ONLY)
    def list_cost_codes(
        project: Project,
        parent: Annotated[
            str | None, Field(max_length=MAX_PART, description="Only the children of this code.")
        ] = None,
        search: Annotated[
            str | None, Field(max_length=MAX_PART, description="Text in the code or title.")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=1000, description="Rows to return.")] = 200,
    ) -> list[cost_views.CostCodeView]:
        """List a project's cost codes (brief 9 M11) with the latest figures a snapshot stated.

        `figures` has hours, quantity and amount, each as budget, actual, earned, ftc and eac.
        """
        with guarded(ctx, "list_cost_codes", resource_name("cost", project)):
            return list_cost_codes_impl(
                ctx, project=project, parent=parent, search=search, limit=limit
            )

    @server.tool(annotations=READ_ONLY)
    def get_cost_code(
        project: Project,
        code: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The cost code, `4210-PIP`.")
        ],
    ) -> cost_views.CostCodeDetailView:
        """Get one cost code with its children and what every snapshot said about it."""
        with guarded(ctx, "get_cost_code", resource_name("cost", project, code)):
            return get_cost_code_impl(ctx, project=project, code=code)

    @server.tool(annotations=READ_ONLY)
    def list_cost_snapshots(project: Project) -> list[cost_views.CostSnapshotView]:
        """List a project's imported cost periods, newest first, with their row counts."""
        with guarded(ctx, "list_cost_snapshots", resource_name("cost", project)):
            return list_cost_snapshots_impl(ctx, project=project)
