# P1-I4-T13 — MCP read tools for schedules and cost

Status: ready
Tier: haiku
Labels: mcp
Depends on: S10 and S7 on `p1/i4` (the MCP server, the views, the action list and the pinned tool lists are in the tree); no other ticket
Branch: `p1/i4-t13-mcp-schedule-read-tools`

## Goal
An agent that helps a planner can read the schedule and cost data: the schedules, their snapshots, the activities, what changed between two updates, the look-ahead, what an activity id resolves to, the float trend, the orphaned links, a record's activity links, and the cost codes and periods. `packages/tl-mcp/src/tl_mcp/schedule_read_tools.py` has the thirteen tools written (names, argument bounds, descriptions, the authorizer call); the thirteen `*_impl` functions they call raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11 and §18.** Agents read the suite through MCP tools and propose changes; they never change a record themselves. Every read goes through the authorizer with the action `mcp.<tool>` (`document.read` for an agent); the tool list is closed (`tl_mcp.identity.MCP_ACTIONS`).
>
> **ADR-0015.** The module views (`tl_mod_schedule.views`, `tl_mod_cost.views`) are the read shapes: an agent, the API and a screen see the same fields. A tool calls one view and returns what it returns; it parses nothing of its own, so a missing schedule is the module's error (`ToolError`), and a schedule of another project is not found.
>
> **Reads write nothing.** Each `*_impl` opens `ctx.factory(True)`: the `True` is read-only. `propose_publish_schedule_snapshot` (already built) is the only schedule tool that files anything, and only as a pending proposal.

### Specification
- Each `*_impl` is `with ctx.factory(True) as uow:` and one view call with `uow.conn()` and the scope `f"project:{project}"`, returned from inside the `with`. The model of the document tools (`document_tools.py`) is the same.
- `list_activities_impl` passes `critical=True` when `critical` is true and `None` otherwise (`False` would ask for the non-critical activities).
- `resolve_impl` turns the `as_of` text into what the view takes with `views.as_of_of`.
- The `register_schedule_read_tools` body, the argument bounds and the `guarded(...)` calls are written; do not change them. The tool list is pinned in `tests/test_mcp_server.py` and in `identity.MCP_ACTIONS`; both already hold the thirteen names.

### Learnings that apply
> **L-P1-I4-9.** `just check` takes over two minutes in a fresh worktree; the MCP package suite takes about five minutes. Give them a long timeout or run them in the background and wait.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-mcp/src/tl_mcp/schedule_read_tools.py` (the stub you complete; the whole file):
```python
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
```

`packages/tl-modules/schedule/src/tl_mod_schedule/views.py (excerpt)` (read-only for you):
```python
class ScheduleView(BaseModel):
    id: str
    code: str
    title: str
    schedule_type: str
    owner: str | None
    p6_project: str | None
    current_snapshot_number: int | None
    current_data_date: str | None
    snapshot_count: int

    @classmethod
    def of(cls, row: ScheduleRow, snapshot_count: int) -> ScheduleView:
        return cls(
            id=row.id,
            code=row.code,
            title=row.title,
            schedule_type=row.schedule_type,
            owner=row.owner,
            p6_project=row.p6_project,
            current_snapshot_number=row.current_snapshot_number,
            current_data_date=row.current_data_date,
            snapshot_count=snapshot_count,
        )

class ScheduleDetailView(ScheduleView):
    """A schedule with its snapshots, newest number first.

    ``links_being_checked`` is true while the job that flags the links to activities the current
    snapshot lacks (and restores the ones that came back) has work left: until it is done a link to
    a removed activity may still read as current (ADR-0015 section 5).
    """

    snapshots: list[SnapshotView]
    links_being_checked: bool = False

@dataclass(frozen=True)
class ActivityPage:
    """A page of a snapshot's activities and how many matched in all."""

    snapshot_key: str
    snapshot_number: int
    data_date: str | None
    total: int
    offset: int
    rows: tuple[ActivityRow, ...]

@dataclass(frozen=True)
class ActivityDetail:
    """One activity with the relationships that name it."""

    snapshot_key: str
    snapshot_number: int
    activity: ActivityRow
    predecessors: tuple[RelationshipRow, ...]
    successors: tuple[RelationshipRow, ...]

@dataclass(frozen=True)
class TrendPoint:
    """One activity in one published snapshot (the float trend of brief 9 M11)."""

    snapshot_number: int
    data_date: str | None
    state: str
    total_float_days: float | None
    early_start: str | None
    early_finish: str | None
    percent_complete: float
    critical: bool

def as_of_of(text: str | None) -> AsOf:
    """An as-of written as text: nothing or ``current`` is the current snapshot, ASCII digits a
    snapshot number, anything else a date for ``resolver.resolve_snapshot`` to judge."""
    ...

def schedule_views(conn: Connection, scope: str) -> list[ScheduleView]:
    ...

def schedule_detail(conn: Connection, scope: str, code: str) -> ScheduleDetailView:
    ...

def activity_page(
    conn: Connection,
    scope: str,
    code: str,
    number: int | None = None,
    *,
    critical: bool | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> ActivityPage:
    """A page of activities in file order. ``limit`` is cut to ``MAX_PAGE``."""
    ...

def activity_detail(
    conn: Connection, scope: str, code: str, activity_id: str, number: int | None = None
) -> ActivityDetail:
    ...

def float_trend(conn: Connection, scope: str, code: str, activity_id: str) -> list[TrendPoint]:
    """The activity in every published snapshot, oldest data date first (at most 500 points).

    A snapshot that lacks the activity is left out of the list. An activity no snapshot has is
    ``ActivityNotFoundError``.
    """
    ...

def comparison(
    conn: Connection,
    scope: str,
    code: str,
    new: int | None = None,
    old: int | None = None,
    *,
    limit: int = DEFAULT_COMPARE_LIMIT,
) -> Comparison:
    """What changed from ``old`` to ``new`` (default: the current snapshot and the one before).

    Both must be built. ``SnapshotNotFoundError`` when ``old`` is not given and ``new`` is the
    first. Each list is cut to ``limit`` rows (at most 5000); ``totals`` keeps the full counts.
    """
    ...

def look_ahead_view(
    conn: Connection, scope: str, code: str, number: int | None = None, weeks: int = 4
) -> LookAhead:
    """The look-ahead of a built snapshot (default: the current one). ``ValueError`` for weeks."""
    ...

def resolution(
    conn: Connection, scope: str, code: str, activity_id: str, as_of: AsOf = None
) -> Resolution:
    """What ``activity_id`` is now (``as_of`` ``None``) or as of a snapshot number or a date."""
    ...

def orphans(conn: Connection, scope: str, code: str) -> list[OrphanedLink]:
    """The links the last publication flagged because their activity left the schedule."""
    ...

def activity_links(conn: Connection, scope: str, record_id: str) -> list[ActivityLink]:
    """The activity links of a record of ``scope`` and what each resolves to now (at most 200)."""
    ...
```

`packages/tl-modules/cost/src/tl_mod_cost/views.py (excerpt)` (read-only for you):
```python
class CostCodeView(BaseModel):
    """A cost code with the latest figures a snapshot stated for it."""

    id: str
    code: str
    title: str
    parent_code: str | None
    level: int
    uom: str | None
    is_active: bool
    period: str | None  # the snapshot the figures come from
    as_of: str | None
    figures: dict[str, float | None]

    @classmethod
    def of(cls, row: registry.CostCodeRow) -> CostCodeView:
        return cls(
            id=row.id,
            code=row.code,
            title=row.title,
            parent_code=row.parent_code,
            level=row.level,
            uom=row.uom,
            is_active=row.is_active,
            period=row.period,
            as_of=row.as_of,
            figures=row.figures,
        )

class CostCodeDetailView(CostCodeView):
    """A code with its children's codes and the figures of every snapshot, oldest first."""

    children: list[str]
    history: list[SnapshotValueView]

class CostSnapshotView(BaseModel):
    id: str
    period: str
    revision: int
    key: str  # period@revision
    as_of: str
    currency: str | None
    source_name: str | None
    source_sha256: str | None
    row_count: int
    new_code_count: int
    revised_code_count: int
    created_at: str

    @classmethod
    def of(cls, row: registry.CostSnapshotRow) -> CostSnapshotView:
        return cls(
            id=row.id,
            period=row.period,
            revision=row.revision,
            key=f"{row.period}@{row.revision}",
            as_of=row.as_of,
            currency=row.currency,
            source_name=row.source_name,
            source_sha256=row.source_sha256,
            row_count=row.row_count,
            new_code_count=row.new_code_count,
            revised_code_count=row.revised_code_count,
            created_at=row.created_at,
        )

def cost_codes(
    conn: Connection,
    scope: str,
    *,
    parent: str | None = None,
    search: str | None = None,
    limit: int = 1000,
) -> list[CostCodeView]:
    """The cost codes of a scope by code. ``parent`` keeps the direct children of one code,
    ``search`` the codes whose code or title holds a text (any case). At most ``limit``."""
    ...

def cost_code_detail(conn: Connection, scope: str, code: str) -> CostCodeDetailView:
    ...

def cost_snapshots(conn: Connection, scope: str) -> list[CostSnapshotView]:
    """The snapshots of a scope, newest period and revision first."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/schedule_read_tools.py`
- `packages/tl-mcp/src/tl_mcp/document_tools.py (the same kind of tools, for the style)`
- `packages/tl-mcp/tests/mcp_harness.py (what the provided test calls; read only)`
- `docs/tickets/P1-I4/provided/t13-test_mcp_schedule_read_tools.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/schedule_read_tools.py (edit)`
- `packages/tl-mcp/tests/test_mcp_schedule_read_tools.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T13.md (create; commit it)`

## Lines you must not change
Everything in `schedule_read_tools.py` outside the thirteen `*_impl` functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), the aliases, `READ_ONLY`, `register_schedule_read_tools` with all its tools, their argument bounds, descriptions and the `guarded(...)` calls. The signatures and docstrings of the `*_impl` functions. `identity.py` and `test_mcp_server.py` (the closed action list and the pinned tool set). The provided test.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t13-test_mcp_schedule_read_tools.py.txt` to `packages/tl-mcp/tests/test_mcp_schedule_read_tools.py`. Do not edit it.
3. Implement the thirteen `*_impl` functions marked STEPS in `schedule_read_tools.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_mcp_schedule_read_tools.py -q
uv run pytest packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_mcp_identity.py packages/tl-mcp/tests/test_mcp_schedule_tools.py -q
```
Expected: `just check` clean; 13 tests pass in the provided file; the pinned-tool and identity tests pass. The MCP server runs on SQLite only, so there is no `--adapters` run.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a change to a view, `identity.py`, `server.py` or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
