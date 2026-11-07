"""Awp tools: the construction work packages, the WBS and the path of construction (P2-I1-T06).

Four read-only tools answer from ``tl_mod_awp.views``, so an agent, the API and a screen see the
same fields under the agent's viewer. ``propose_cwp`` never creates a CWP: it files a pending
proposal of ``CreateCwp``, and a person with the ``user`` word accepts it (ADR-0014 section 8).
The read tools need ``document.read`` like the other reads (``guarded``); the proposal goes
through ``write_tools`` the way ``tl_mcp.schedule_tools`` does.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import views
from tl_mod_awp.commands import CreateCwp

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.schedule_read_tools import READ_ONLY
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Number = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="The CWP's number, for example `P123-CWP-CIV-0001`.",
    ),
]


def list_cwps_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    discipline: str | None,
    cwa: str | None,
) -> list[views.CwpRow]:
    """The project's CWPs by number, void ones left out, optionally filtered."""
    with ctx.factory(True) as uow:
        return views.cwp_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            discipline=discipline,
            cwa=cwa,
        )


def get_cwp_impl(ctx: McpContext, *, project: str, number: str) -> views.CwpDetail:
    """One CWP. A missing, hidden, voided or other-project CWP answers the same error."""
    with ctx.factory(True) as uow:
        found = views.cwp_detail(uow.conn(), f"project:{project}", number)
    if found is None:
        raise RecordNotFoundError(f"no CWP {number!r} in project {project!r}")
    return found


def wbs_tree_impl(ctx: McpContext, *, project: str, depth: int | None) -> list[views.WbsRow]:
    """The WBS nodes depth-first, each with its rollup; ``depth`` keeps the nodes above it."""
    with ctx.factory(True) as uow:
        return views.wbs_tree(uow.conn(), f"project:{project}", depth=depth)


def path_impl(ctx: McpContext, *, project: str, version: int | None) -> views.PathView | None:
    """The path of construction at ``version`` (the current one when None), or None."""
    with ctx.factory(True) as uow:
        return views.path(uow.conn(), f"project:{project}", version=version)


def propose_cwp_impl(
    ctx: McpContext,
    *,
    project: str,
    discipline: str,
    title: str,
    cwa_code: str,
    planned_start: str | None,
    planned_finish: str | None,
    budget_hours: str | None,
    summary: str | None,
) -> ProposalResult:
    scope = f"project:{project}"
    command = CreateCwp(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        discipline=discipline,
        title=title,
        cwa_code=cwa_code,
        planned_start=planned_start,
        planned_finish=planned_finish,
        budget_hours=budget_hours,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_cwp",
        agent=ctx.actor,
        command=command,
        summary=summary or f'Create a {discipline} CWP "{title}" in {cwa_code}',
    )
    return _result(view)


def register_awp_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the four read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_cwps(
        project: Project,
        state: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only CWPs in this state (a NULL state reads as `Planned`).",
            ),
        ] = None,
        discipline: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only CWPs of this discipline."),
        ] = None,
        cwa: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only CWPs in this area's code."),
        ] = None,
    ) -> list[views.CwpRow]:
        """List a project's construction work packages (CWPs) by number.

        Void CWPs are left out. Use `get_cwp` for one CWP's fields, allocation and activities.
        """
        with guarded(ctx, "list_cwps", resource_name("cwps", project)):
            return list_cwps_impl(ctx, project=project, state=state, discipline=discipline, cwa=cwa)

    @server.tool(annotations=READ_ONLY)
    def get_cwp(project: Project, number: Number) -> views.CwpDetail:
        """Get one construction work package (CWP) with its fields.

        The result has its WBS allocation, the EWP and PWP packages it requires, and the activities
        it links to. A CWP that does not exist, or that you may not read, gives the same error.
        """
        with guarded(ctx, "get_cwp", resource_name("cwp", project, number)):
            return get_cwp_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def wbs_tree(
        project: Project,
        depth: Annotated[
            int | None,
            Field(ge=1, le=20, description="Keep the nodes this deep (1 is the top node alone)."),
        ] = None,
    ) -> list[views.WbsRow]:
        """List the work breakdown structure (WBS) depth-first, each node with its rollup."""
        with guarded(ctx, "wbs_tree", resource_name("wbs", project)):
            return wbs_tree_impl(ctx, project=project, depth=depth)

    @server.tool(annotations=READ_ONLY)
    def path_of_construction(
        project: Project,
        version: Annotated[
            int | None,
            Field(ge=1, le=10**9, description="A version of the path (default: the current one)."),
        ] = None,
    ) -> views.PathView | None:
        """Get the path of construction: the ordered construction work areas, at one version.

        Null when the project has no path, or no such version.
        """
        with guarded(ctx, "path_of_construction", resource_name("path", project)):
            return path_impl(ctx, project=project, version=version)

    @server.tool(annotations=PROPOSES)
    def propose_cwp(
        project: Project,
        discipline: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The discipline, `CIV`.")
        ],
        title: Annotated[str, Field(min_length=1, max_length=MAX_PART, description="The title.")],
        cwa_code: Annotated[
            str,
            Field(min_length=1, max_length=MAX_PART, description="The construction area's code."),
        ],
        planned_start: Annotated[
            str | None, Field(max_length=MAX_PART, description="The planned start date.")
        ] = None,
        planned_finish: Annotated[
            str | None, Field(max_length=MAX_PART, description="The planned finish date.")
        ] = None,
        budget_hours: Annotated[
            str | None, Field(max_length=MAX_PART, description="The budget, in hours.")
        ] = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a new construction work package (CWP).

        Nothing is created now. The proposal is checked now, so an error means it could not be
        applied (a bad date, an unknown area). A person who may edit CWPs accepts it in the review
        queue; accepting creates the CWP with its number from the discipline's pattern.
        """
        with guarded(ctx, "propose_cwp", resource_name("cwps", project)):
            return propose_cwp_impl(
                ctx,
                project=project,
                discipline=discipline,
                title=title,
                cwa_code=cwa_code,
                planned_start=planned_start,
                planned_finish=planned_finish,
                budget_hours=budget_hours,
                summary=summary,
            )
