"""Inspection tools (P2-INSP-T07): four reads and one proposal.

The reads answer from ``tl_mod_quality.insp_views`` under ``confidentiality.current_viewer()``,
the viewer ``guarded`` sets (the lowest clearance for an agent), so a hidden inspection answers as
a missing one. ``get_inspection`` and ``get_checklist`` answer one error for a missing, hidden and
other-project key.

``propose_inspection`` files a pending proposal of ``PlanInspection`` (``proposals.submit``);
nothing is planned until a person with the ``quality.inspection.plan`` word accepts it in the
review queue (ADR-0014 section 8, ADR-0027). ``subject_key`` and ``for_key`` are resolved to ids
under the agent's viewer; an unknown or hidden key answers one text. There is no tool that
schedules, records, verifies, reinspects or cancels an inspection.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field
from tl_core import confidentiality
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_quality import insp_views
from tl_mod_quality.commands import MAX_SHORT, MAX_TITLE, PlanInspection

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.intent_param import IntentParam
from tl_mcp.schedule_read_tools import READ_ONLY
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

#: The five ``mcp.<tool>`` actions this module's tools ask the authorizer about. ``identity.py``
#: ORs them into ``MCP_ACTIONS``; a tool not listed there is refused.
INSP_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_inspections",
        "mcp.get_inspection",
        "mcp.list_checklists",
        "mcp.get_checklist",
        "mcp.propose_inspection",
    }
)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Key = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="A key, for example `P123-INS-0001` or `P123-CHK-0001`.",
    ),
]
Limit = Annotated[
    int,
    Field(ge=1, le=MAX_PART, description="The most rows to list (default 50)."),
]
Point = Literal["hold", "witness", "review", "surveillance"]


def _scope(project: str) -> str:
    return f"project:{project}"


def _resolve(uow: UnitOfWork, scope: str, key: str) -> str:
    """The id of the record with ``key`` the viewer may read. ``get_record`` answers ``None`` for a
    hidden record (ADR-0016), so an unknown and a hidden key are one error."""
    found = get_record(uow, scope, key)
    if found is None:
        raise RecordNotFoundError("no record with that key")
    return str(found["id"])


def list_inspections_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    point: str | None,
    area: str | None,
    inspector: str | None,
    subject_key: str | None,
    for_key: str | None,
    limit: int,
) -> insp_views.InspectionPage:
    """The project's visible inspections by key, with the total of the matches."""
    with ctx.factory(True) as uow:
        return insp_views.inspection_list(
            uow.conn(),
            _scope(project),
            state=state,
            point=point,
            area=area,
            inspector=inspector,
            subject_key=subject_key,
            for_key=for_key,
            limit=limit,
            viewer=confidentiality.current_viewer(),
        )


def get_inspection_impl(ctx: McpContext, *, project: str, key: str) -> insp_views.InspectionDetail:
    """One inspection. A missing, hidden or other-project inspection answers the same error."""
    with ctx.factory(True) as uow:
        found = insp_views.inspection_detail(
            uow.conn(), _scope(project), key, viewer=confidentiality.current_viewer()
        )
    if found is None:
        raise RecordNotFoundError(f"no inspection {key}")
    return found


def list_checklists_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    discipline: str | None,
    limit: int,
) -> insp_views.ChecklistPage:
    """The project's visible checklists by key, with the total of the matches."""
    with ctx.factory(True) as uow:
        return insp_views.checklist_list(
            uow.conn(),
            _scope(project),
            state=state,
            discipline=discipline,
            limit=limit,
            viewer=confidentiality.current_viewer(),
        )


def get_checklist_impl(ctx: McpContext, *, project: str, key: str) -> insp_views.ChecklistDetail:
    """One checklist with its questions. A missing, hidden or other-project one answers the same
    error."""
    with ctx.factory(True) as uow:
        found = insp_views.checklist_detail(
            uow.conn(), _scope(project), key, viewer=confidentiality.current_viewer()
        )
    if found is None:
        raise RecordNotFoundError(f"no checklist {key}")
    return found


def propose_inspection_impl(
    ctx: McpContext,
    *,
    project: str,
    subject_key: str,
    title: str,
    point: Point,
    for_key: str | None,
    area: str | None,
    planned_on: str | None,
    summary: str | None,
    intent: Intent | None = None,
) -> ProposalResult:
    scope = _scope(project)
    with ctx.factory(True) as uow:
        subject_id = _resolve(uow, scope, subject_key)
        for_id: str | None = None if for_key is None else _resolve(uow, scope, for_key)
    command = PlanInspection(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        title=title,
        subject_id=subject_id,
        point=point,
        for_iwp_id=for_id,
        area=area,
        planned_on=planned_on,
        intent=intent,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_inspection",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Plan inspection: {title}",
    )
    return _result(view)


def register_insp_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the four inspection read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_inspections(
        project: Project,
        state: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only inspections in this state: Planned, Scheduled, Done, Verified "
                "or Cancelled.",
            ),
        ] = None,
        point: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only this point: hold, witness, review or surveillance.",
            ),
        ] = None,
        area: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only inspections in this area."),
        ] = None,
        inspector: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only this inspector."),
        ] = None,
        subject_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only inspections of this record key.",
            ),
        ] = None,
        for_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only inspections for this work package key.",
            ),
        ] = None,
        limit: Limit = 50,
    ) -> insp_views.InspectionPage:
        """List a project's inspections by key, with the total number of matches.

        Use `get_inspection` for one inspection's fields, answers and history. Inspections you may
        not read are left out.
        """
        with guarded(ctx, "list_inspections", resource_name("inspection", project)):
            return list_inspections_impl(
                ctx,
                project=project,
                state=state,
                point=point,
                area=area,
                inspector=inspector,
                subject_key=subject_key,
                for_key=for_key,
                limit=limit,
            )

    @server.tool(annotations=READ_ONLY)
    def get_inspection(project: Project, key: Key) -> insp_views.InspectionDetail:
        """Get one inspection with its point, subject, result, verification, reinspection and the
        punch items raised against it.

        An inspection that does not exist, that you may not read, or that is in another project
        gives the same error.
        """
        with guarded(ctx, "get_inspection", resource_name("inspection", project, key)):
            return get_inspection_impl(ctx, project=project, key=key)

    @server.tool(annotations=READ_ONLY)
    def list_checklists(
        project: Project,
        state: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only checklists in this state: Draft, Published or Retired.",
            ),
        ] = None,
        discipline: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only this discipline."),
        ] = None,
        limit: Limit = 50,
    ) -> insp_views.ChecklistPage:
        """List a project's checklists by key, with the total number of matches.

        Use `get_checklist` for one checklist's questions. Checklists you may not read are left
        out.
        """
        with guarded(ctx, "list_checklists", resource_name("checklist", project)):
            return list_checklists_impl(
                ctx, project=project, state=state, discipline=discipline, limit=limit
            )

    @server.tool(annotations=READ_ONLY)
    def get_checklist(project: Project, key: Key) -> insp_views.ChecklistDetail:
        """Get one checklist with its questions, version and publication history.

        A checklist that does not exist or that is in another project gives the same error.
        """
        with guarded(ctx, "get_checklist", resource_name("checklist", project, key)):
            return get_checklist_impl(ctx, project=project, key=key)

    @server.tool(annotations=PROPOSES)
    def propose_inspection(
        project: Project,
        subject_key: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="The key of the record to inspect, for example an IWP.",
            ),
        ],
        title: Annotated[
            str,
            Field(min_length=1, max_length=MAX_TITLE, description="The inspection's title."),
        ],
        point: Annotated[
            Point,
            Field(description="The inspection point: hold, witness, review or surveillance."),
        ],
        for_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="The key of the work package it is for.",
            ),
        ] = None,
        area: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_SHORT, description="The area it is in."),
        ] = None,
        planned_on: Annotated[
            str | None,
            Field(max_length=10, description="The planned date, YYYY-MM-DD."),
        ] = None,
        summary: Summary = None,
        intent: IntentParam = None,
    ) -> ProposalResult:
        """Propose a new inspection, planned.

        Nothing is planned now. A person who may plan inspections accepts it in the review queue.
        """
        with guarded(ctx, "propose_inspection", resource_name("inspection", project)):
            return propose_inspection_impl(
                ctx,
                project=project,
                subject_key=subject_key,
                title=title,
                point=point,
                for_key=for_key,
                area=area,
                planned_on=planned_on,
                summary=summary,
                intent=intent,
            )
