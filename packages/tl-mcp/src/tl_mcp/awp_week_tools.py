"""Weekly-plan tools (P2-I5-T11c): five reads of the weekly cycle, the state the CLI and API show.

``list_weekly_plans`` and ``get_weekly_plan`` answer from ``tl_mod_awp.week_views``;
``get_iwp_progress`` from ``iwp_views.iwp_detail`` and ``progress.engine.earned_fraction``;
``get_progress_rollup`` from ``progress.rollup.progress_rollup``; ``list_kpis`` from
``tl_mod_awp.kpis.kpi_rows``. Every read names its resource for the authorizer (``guarded``) and
reads as the lowest clearance, so a hidden record answers as a missing one.

Nothing here writes. The look-ahead needs a schedule snapshot and stays off MCP this increment
(D29). The five ``mcp.<tool>`` actions are in ``WEEK_MCP_ACTIONS``; ``identity.py`` ORs them into
``MCP_ACTIONS``, so a tool not listed there is refused.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field
from tl_core import confidentiality
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import iwp_views, kpis, week_views
from tl_mod_awp.progress import engine
from tl_mod_awp.progress.rollup import progress_rollup

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.schedule_read_tools import READ_ONLY

#: The five ``mcp.<tool>`` actions this module's tools ask the authorizer about.
WEEK_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_weekly_plans",
        "mcp.get_weekly_plan",
        "mcp.get_iwp_progress",
        "mcp.get_progress_rollup",
        "mcp.list_kpis",
    }
)

#: The most weekly plans ``list_weekly_plans`` returns (the latest weeks first).
LIST_LIMIT = 60

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Week = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="The week as `YYYY-Www`, for example `2026-W45`.",
    ),
]
Number = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="The IWP's number, for example `P123-IWP-0001`.",
    ),
]

#: The one answer for a plan that is absent, hidden or of another week (same text for each).
NO_PLAN = "no weekly plan for that week"


class ItemBody(BaseModel):
    """One scope item of an IWP as far as the reader may open it."""

    key: str
    pct: Decimal
    steps: list[str]
    hours: Decimal | None = None


class IwpProgressBody(BaseModel):
    """The earned progress of one IWP: the stored figure, its edition, items and notes."""

    number: str
    pct: Decimal
    edition: str
    items: list[ItemBody]
    notes: list[str]


class CwpRow(BaseModel):
    cwp_id: str
    key: str
    iwps: int
    earned_hours: Decimal
    hours: Decimal


class NodeRow(BaseModel):
    node_id: str
    earned_hours: Decimal
    budget_hours: Decimal | None = None
    pct: Decimal | None = None


class CostLineRow(BaseModel):
    cost_code_id: str | None = None
    code: str | None = None
    earned_hours: Decimal
    budget_hours: Decimal | None = None


class RollupBody(BaseModel):
    """Earned hours of a project by CWP, WBS node and cost code, as the viewer may see them."""

    scope: str
    as_of_seq: int
    cwps: list[CwpRow]
    nodes: list[NodeRow]
    lines: list[CostLineRow]
    notes: list[str]


def _scope(project: str) -> str:
    return f"project:{project}"


def list_weekly_plans_impl(ctx: McpContext, *, project: str) -> list[week_views.WeekRow]:
    """The project's weekly plans, the latest week first, those the viewer may read."""
    with ctx.factory(True) as uow:
        return week_views.list_weeks(
            uow.conn(),
            _scope(project),
            confidentiality.current_viewer(),
            limit=LIST_LIMIT,
        )


def get_weekly_plan_impl(ctx: McpContext, *, project: str, week: str) -> week_views.WeekDetail:
    """One weekly plan with its commitments. A missing, hidden or voided plan answers one error."""
    with ctx.factory(True) as uow:
        conn = uow.conn()
        viewer = confidentiality.current_viewer()
        plans = week_views.list_weeks(conn, _scope(project), viewer, limit=week_views.MAX_WEEKS)
        match = next((plan for plan in plans if plan.week == week), None)
        if match is None:
            raise RecordNotFoundError(NO_PLAN)
        return week_views.week_detail(conn, match.id, viewer)


def get_iwp_progress_impl(ctx: McpContext, *, project: str, number: str) -> IwpProgressBody:
    """The earned progress of one IWP. A missing, hidden or voided IWP answers the same error."""
    with ctx.factory(True) as uow:
        conn = uow.conn()
        found = iwp_views.iwp_detail(conn, _scope(project), number)
        if found is None:
            raise RecordNotFoundError(f"no IWP {number!r} in project {project!r}")
        earned = engine.earned_fraction(conn, found.id, viewer=confidentiality.current_viewer())
    return IwpProgressBody(
        number=found.number,
        pct=earned.pct,
        edition=earned.edition,
        items=[
            ItemBody(key=item.key, pct=item.pct, steps=list(item.steps), hours=item.hours)
            for item in earned.items
        ],
        notes=earned.notes,
    )


def get_progress_rollup_impl(ctx: McpContext, *, project: str) -> RollupBody:
    """The earned hours of the project by CWP, WBS node and cost code, under the viewer."""
    with ctx.factory(True) as uow:
        rolled = progress_rollup(
            uow.conn(), _scope(project), viewer=confidentiality.current_viewer()
        )
    return RollupBody.model_validate(dataclasses.asdict(rolled))


def list_kpis_impl(ctx: McpContext, *, project: str) -> list[kpis.KpiTile]:
    """The two KPI tiles of the weekly cycle (PPC and constraint-free), under the viewer."""
    with ctx.factory(True) as uow:
        return kpis.kpi_rows(uow.conn(), _scope(project), confidentiality.current_viewer())


def register_week_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the five weekly-plan read tools to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_weekly_plans(project: Project) -> list[week_views.WeekRow]:
        """List a project's weekly plans, the latest week first, with state and PPC.

        Plans you may not read are left out.
        """
        with guarded(ctx, "list_weekly_plans", resource_name("weeks", project)):
            return list_weekly_plans_impl(ctx, project=project)

    @server.tool(annotations=READ_ONLY)
    def get_weekly_plan(project: Project, week: Week) -> week_views.WeekDetail:
        """Get one weekly plan (`YYYY-Www`) with its commitments and notes.

        A commitment of an IWP you may not read is left out, with a note. A week with no plan, or
        a plan you may not read, gives the same error.
        """
        with guarded(ctx, "get_weekly_plan", resource_name("week", project, week)):
            return get_weekly_plan_impl(ctx, project=project, week=week)

    @server.tool(annotations=READ_ONLY)
    def get_iwp_progress(project: Project, number: Number) -> IwpProgressBody:
        """Get the earned progress of one installation work package (IWP): its percent, edition,
        scope items with their steps and hours, and notes.

        An IWP that does not exist, or that you may not read, gives the same error.
        """
        with guarded(ctx, "get_iwp_progress", resource_name("iwp", project, number)):
            return get_iwp_progress_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def get_progress_rollup(project: Project) -> RollupBody:
        """Get the earned hours of a project by construction work package (CWP), WBS node and cost
        code. Records you may not read are left out, without a note."""
        with guarded(ctx, "get_progress_rollup", resource_name("progress", project)):
            return get_progress_rollup_impl(ctx, project=project)

    @server.tool(annotations=READ_ONLY)
    def list_kpis(project: Project) -> list[kpis.KpiTile]:
        """List the two weekly-cycle KPI tiles: PPC over the last closed weeks, and the percent of
        live IWPs with no open blocking constraint. A tile with nothing to count has no value."""
        with guarded(ctx, "list_kpis", resource_name("kpis", project)):
            return list_kpis_impl(ctx, project=project)
