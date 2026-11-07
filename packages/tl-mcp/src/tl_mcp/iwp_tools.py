"""IWP tools (P2-I2-T09b): four reads and one proposal.

The reads answer from ``tl_mod_awp.iwp_views`` and the readiness from
``tl_mod_awp.readiness.views.visible_readiness``. Every read names its resource for the authorizer
(``guarded``) and reads as the lowest clearance, so a hidden record answers as a missing one.

``propose_iwp_scope`` files a pending proposal (``proposals.submit``); nothing changes until a
person with the ``user`` word accepts it (ADR-0014 section 8). The IWP and the scope items are
named by key and resolved under the agent's viewer; an unknown or hidden key answers one text.

The constraint tools (reads and ``propose_constraint``) are not here: an agent holds no
``core.constraint.*`` word, and agent use of core words is deferred to the Phase 3 agent layer
(ADR-0027).
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field
from tl_core import confidentiality
from tl_core.readiness.types import RecordRef
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_awp import iwp_views
from tl_mod_awp.commands import AddIwpScope
from tl_mod_awp.readiness.views import visible_readiness

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.schedule_read_tools import READ_ONLY
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

#: The five ``mcp.<tool>`` actions this module's tools ask the authorizer about. ``identity.py``
#: ORs them into ``MCP_ACTIONS``; a tool not listed there is refused.
IWP_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_iwps",
        "mcp.get_iwp",
        "mcp.list_iwp_scope",
        "mcp.get_iwp_readiness",
        "mcp.propose_iwp_scope",
    }
)

#: The most scope items one proposal names (the command takes at most 200).
MAX_PROPOSED_ITEMS = 50

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Number = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="The IWP's number, for example `P123-IWP-0001`.",
    ),
]
Key = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="A record's key, for example `P123-THR-0001`.",
    ),
]


class CheckBody(BaseModel):
    """One readiness check as a reader sees it: only records the reader may open in `resolve_via`
    (id, type, key); the counts are as evaluated and name no record."""

    name: str
    version: str
    state: str
    detail: str
    resolve_via: list[RecordRef]
    count_ok: int | None
    count_total: int | None


class ReadinessBody(BaseModel):
    """The last readiness evaluation of an IWP (no facts hash)."""

    iwp_id: str
    evaluated_at: str
    today: str
    ready: bool
    checks: list[CheckBody]


def _scope(project: str) -> str:
    return f"project:{project}"


def _resolve(uow: UnitOfWork, scope: str, key: str) -> str:
    """The id of the record with ``key`` the viewer may read. ``get_record`` answers ``None`` for a
    hidden record (ADR-0016), so an unknown and a hidden key are one error."""
    found = get_record(uow, scope, key)
    if found is None:
        raise RecordNotFoundError("no record with that key")
    return str(found["id"])


def list_iwps_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    discipline: str | None,
    foreman: str | None,
) -> list[iwp_views.IwpRow]:
    """The project's IWPs by number, hidden and void ones left out, optionally filtered."""
    with ctx.factory(True) as uow:
        return iwp_views.iwp_list(
            uow.conn(),
            _scope(project),
            state=state,
            discipline=discipline,
            foreman=foreman,
        )


def get_iwp_impl(ctx: McpContext, *, project: str, number: str) -> iwp_views.IwpDetail:
    """One IWP. A missing, hidden or voided IWP answers the same error."""
    with ctx.factory(True) as uow:
        found = iwp_views.iwp_detail(uow.conn(), _scope(project), number)
    if found is None:
        raise RecordNotFoundError(f"no IWP {number!r} in project {project!r}")
    return found


def list_iwp_scope_impl(ctx: McpContext, *, project: str, number: str) -> list[iwp_views.ScopeRow]:
    """The scope items of one IWP. A missing, hidden or voided IWP answers the same error."""
    with ctx.factory(True) as uow:
        found = iwp_views.iwp_scope(uow.conn(), _scope(project), number)
    if found is None:
        raise RecordNotFoundError(f"no IWP {number!r} in project {project!r}")
    return found


def get_iwp_readiness_impl(ctx: McpContext, *, project: str, number: str) -> ReadinessBody:
    """The last readiness evaluation of one IWP. Missing, hidden and never evaluated answer one
    error."""
    with ctx.factory(True) as uow:
        view = visible_readiness(
            uow.conn(), _scope(project), number, confidentiality.current_viewer()
        )
    if view is None:
        raise RecordNotFoundError(f"no IWP {number!r} in project {project!r}")
    return ReadinessBody(
        iwp_id=view.iwp_id,
        evaluated_at=view.evaluated_at,
        today=view.today,
        ready=view.ready,
        checks=[CheckBody(**c.model_dump()) for c in view.checks],
    )


def propose_iwp_scope_impl(
    ctx: McpContext,
    *,
    project: str,
    iwp: str,
    items: list[str],
    summary: str | None,
) -> ProposalResult:
    scope = _scope(project)
    with ctx.factory(True) as uow:
        iwp_id = _resolve(uow, scope, iwp)
        item_ids = [_resolve(uow, scope, item) for item in items]
    command = AddIwpScope(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        iwp=iwp_id,
        items=item_ids,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_iwp_scope",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Add {len(items)} scope items to {iwp}",
    )
    return _result(view)


def register_iwp_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the four IWP read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_iwps(
        project: Project,
        state: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only IWPs in this state."),
        ] = None,
        discipline: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only IWPs of this discipline."),
        ] = None,
        foreman: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only IWPs of this foreman."),
        ] = None,
    ) -> list[iwp_views.IwpRow]:
        """List a project's installation work packages (IWPs) by number.

        Hidden and void IWPs are left out. Use `get_iwp` for one IWP's fields and pins.
        """
        with guarded(ctx, "list_iwps", resource_name("iwps", project)):
            return list_iwps_impl(
                ctx, project=project, state=state, discipline=discipline, foreman=foreman
            )

    @server.tool(annotations=READ_ONLY)
    def get_iwp(project: Project, number: Number) -> iwp_views.IwpDetail:
        """Get one installation work package (IWP) with its fields.

        The result has its crew, sign-offs, pin count, open constraints and scope count by type.
        An IWP that does not exist, or that you may not read, gives the same error.
        """
        with guarded(ctx, "get_iwp", resource_name("iwp", project, number)):
            return get_iwp_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def list_iwp_scope(project: Project, number: Number) -> list[iwp_views.ScopeRow]:
        """List the scope items and tags of one installation work package (IWP), by type and key."""
        with guarded(ctx, "list_iwp_scope", resource_name("iwp", project, number)):
            return list_iwp_scope_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def get_iwp_readiness(project: Project, number: Number) -> ReadinessBody:
        """Get the last readiness evaluation of one installation work package (IWP).

        Each blocked check names only the records you may open. An IWP that does not exist, that
        you may not read, or that was never evaluated gives the same error.
        """
        with guarded(ctx, "get_iwp_readiness", resource_name("iwp", project, number)):
            return get_iwp_readiness_impl(ctx, project=project, number=number)

    @server.tool(annotations=PROPOSES)
    def propose_iwp_scope(
        project: Project,
        iwp: Annotated[Key, Field(description="The IWP's number.")],
        items: Annotated[
            list[Key],
            Field(min_length=1, max_length=MAX_PROPOSED_ITEMS, description="The record keys."),
        ],
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose adding scope items to an installation work package (IWP).

        Nothing is added now. A person who may change IWP scope accepts it in the review queue.
        """
        with guarded(ctx, "propose_iwp_scope", resource_name("iwp", project, iwp)):
            return propose_iwp_scope_impl(
                ctx, project=project, iwp=iwp, items=items, summary=summary
            )
