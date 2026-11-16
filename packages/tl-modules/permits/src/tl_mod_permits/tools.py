"""The agent tools of the permits module (P2-PTW T08): three reads and one proposal.

The reads answer from ``tl_mod_permits.views`` under ``confidentiality.current_viewer()``, the
viewer ``guarded`` sets (the lowest clearance for an agent), so a hidden permit answers as a missing
one: no row, no count, the same error. ``get_permit`` answers ``no permit <key>`` for a missing,
hidden and other-project key.

``propose_permit`` files a pending proposal of ``RequestPermit`` (``proposals.submit``); nothing
changes until a person who holds the ``permits.request`` word accepts it, and the accepting person
is the requester. There is no tool that approves, issues, suspends, resumes, hands back, closes or
cancels a permit.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field
from tl_core import confidentiality
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow
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

from tl_mod_permits import views as permit_views
from tl_mod_permits.commands import (
    MAX_AREA,
    MAX_DESCRIPTION,
    MAX_HOLDER,
    MAX_LOCATION,
    PermitType,
    RequestPermit,
)

#: The four ``mcp.<tool>`` actions this module's tools ask the authorizer about. ``identity.py``
#: ORs them into ``MCP_ACTIONS``; a tool not listed there is refused.
PERMIT_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_permits",
        "mcp.get_permit",
        "mcp.permit_board",
        "mcp.propose_permit",
    }
)

DEFAULT_LIMIT = 50

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Key = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="A permit's key, for example `P123-PTW-0001`.",
    ),
]


def _scope(project: str) -> str:
    return f"project:{project}"


def _resolve(uow: UnitOfWork, scope: str, key: str) -> str:
    """The id of the record with ``key`` the viewer may read. ``get_record`` answers ``None`` for a
    hidden record (ADR-0016), so an unknown and a hidden key are one error."""
    found = get_record(uow, scope, key)
    if found is None:
        raise RecordNotFoundError("no record with that key")
    return str(found["id"])


def list_permits_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    permit_type: str | None,
    area: str | None,
    holder: str | None,
    limit: int,
) -> permit_views.PermitPage:
    """The project's visible permits by key, with the total of the matches."""
    now = utcnow()
    with ctx.factory(True) as uow:
        return permit_views.permit_list(
            uow.conn(),
            _scope(project),
            now=now,
            state=state,
            permit_type=permit_type,
            area=area,
            holder=holder,
            limit=limit,
            viewer=confidentiality.current_viewer(),
        )


def get_permit_impl(ctx: McpContext, *, project: str, key: str) -> permit_views.PermitDetail:
    """One permit. A missing, hidden or other-project permit answers the same error."""
    now = utcnow()
    with ctx.factory(True) as uow:
        found = permit_views.permit_detail(
            uow.conn(),
            _scope(project),
            key,
            now=now,
            viewer=confidentiality.current_viewer(),
        )
    if found is None:
        raise RecordNotFoundError(f"no permit {key}")
    return found


def permit_board_impl(
    ctx: McpContext, *, project: str, area: str | None
) -> permit_views.PermitBoard:
    """The live permits (Lapsed, Suspended, Active) of the project by area, with the counts."""
    now = utcnow()
    with ctx.factory(True) as uow:
        return permit_views.permit_board(
            uow.conn(),
            _scope(project),
            area,
            now=now,
            viewer=confidentiality.current_viewer(),
        )


def propose_permit_impl(
    ctx: McpContext,
    *,
    project: str,
    permit_type: PermitType,
    area: str,
    location_text: str,
    work_description: str,
    holder: str,
    needed_from: str,
    needed_until: str,
    for_key: str | None,
    summary: str | None,
    intent: Intent | None = None,
) -> ProposalResult:
    scope = _scope(project)
    for_id: str | None = None
    if for_key is not None:
        with ctx.factory(True) as uow:
            for_id = _resolve(uow, scope, for_key)
    command = RequestPermit(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        intent=intent,
        permit_type=permit_type,
        for_record_id=for_id,
        area=area,
        location_text=location_text,
        work_description=work_description,
        holder=holder,
        needed_from=needed_from,
        needed_until=needed_until,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_permit",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Request {permit_type} permit: {area}",
    )
    return _result(view)


def register_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the three permit read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_permits(
        project: Project,
        state: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description=(
                    "Only permits in this state: Requested, Approved, Active, Lapsed, "
                    "Suspended, Handed back, Closed, Rejected or Cancelled."
                ),
            ),
        ] = None,
        permit_type: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only permits of this type."),
        ] = None,
        area: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_AREA, description="Only permits in this area."),
        ] = None,
        holder: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_HOLDER, description="Only permits of this holder."),
        ] = None,
        limit: Annotated[
            int,
            Field(ge=1, le=MAX_PART, description="The most rows to return."),
        ] = DEFAULT_LIMIT,
    ) -> permit_views.PermitPage:
        """List a project's permits by key, with the total number of matches.

        Use `get_permit` for one permit's fields and history. Permits you may not read are left
        out of the rows and the total.
        """
        with guarded(ctx, "list_permits", resource_name("permit", project)):
            return list_permits_impl(
                ctx,
                project=project,
                state=state,
                permit_type=permit_type,
                area=area,
                holder=holder,
                limit=limit,
            )

    @server.tool(annotations=READ_ONLY)
    def get_permit(project: Project, key: Key) -> permit_views.PermitDetail:
        """Get one permit with its fields, its dates and its state history.

        A permit that does not exist, that you may not read, or that is in another project gives
        the same error.
        """
        with guarded(ctx, "get_permit", resource_name("permit", project, key)):
            return get_permit_impl(ctx, project=project, key=key)

    @server.tool(annotations=READ_ONLY)
    def permit_board(
        project: Project,
        area: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_AREA, description="Only the permits in this area."),
        ] = None,
    ) -> permit_views.PermitBoard:
        """The live permits (Lapsed, Suspended and Active) by area, with the counts by state.

        Permits you may not read are left out of the board and the counts.
        """
        with guarded(ctx, "permit_board", resource_name("permit", project)):
            return permit_board_impl(ctx, project=project, area=area)

    @server.tool(annotations=PROPOSES)
    def propose_permit(
        project: Project,
        permit_type: Annotated[
            PermitType,
            Field(
                description=(
                    "The type: hot_work, confined_space, work_at_height, excavation, isolation "
                    "or general."
                )
            ),
        ],
        area: Annotated[
            str,
            Field(min_length=1, max_length=MAX_AREA, description="The area the work is in."),
        ],
        location_text: Annotated[
            str,
            Field(min_length=1, max_length=MAX_LOCATION, description="Where the work is."),
        ],
        work_description: Annotated[
            str,
            Field(min_length=1, max_length=MAX_DESCRIPTION, description="What the work is."),
        ],
        holder: Annotated[
            str,
            Field(min_length=1, max_length=MAX_HOLDER, description="Who holds the permit."),
        ],
        needed_from: Annotated[
            str,
            Field(max_length=10, description="The first day needed, YYYY-MM-DD."),
        ],
        needed_until: Annotated[
            str,
            Field(max_length=10, description="The last day needed, YYYY-MM-DD."),
        ],
        for_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="The key of the record the work is for, for example an IWP.",
            ),
        ] = None,
        summary: Summary = None,
        intent: IntentParam = None,
    ) -> ProposalResult:
        """Propose a new permit request.

        Nothing is requested now. A person who may request permits accepts it in the review
        queue, and the accepting person becomes the requester.
        """
        with guarded(ctx, "propose_permit", resource_name("permit", project)):
            return propose_permit_impl(
                ctx,
                project=project,
                permit_type=permit_type,
                area=area,
                location_text=location_text,
                work_description=work_description,
                holder=holder,
                needed_from=needed_from,
                needed_until=needed_until,
                for_key=for_key,
                summary=summary,
                intent=intent,
            )
