"""IWP and constraint tools (P2-I2-T09b): seven reads and two proposals.

The IWP reads answer from ``tl_mod_awp.iwp_views`` and the readiness from
``tl_mod_awp.readiness.views.visible_readiness``; the constraint reads answer from
``tl_core.constraints``. Every read names its resource for the authorizer (``guarded``) and reads
as the lowest clearance, so a hidden record answers as a missing one. The three constraint reads
first check the access word ``core.constraint.view`` for the agent's actor before any lookup.

``propose_constraint`` and ``propose_iwp_scope`` file a pending proposal (``proposals.submit``);
nothing changes until a person with the ``user`` word accepts it (ADR-0014 section 8). The
subject, the IWP and the scope items are named by key and resolved under the agent's viewer; an
unknown or hidden key answers one text.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field
from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.constraints.commands import ACCESS_MODULE, RECORD_TYPE, VIEW_WORD, RaiseConstraint
from tl_core.constraints.queries import (
    MAX_LIMIT,
    ConstraintView,
    count_constraints,
    get_constraint,
    list_constraints,
)
from tl_core.constraints.review import ConstraintGroup, review_groups
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

#: The nine ``mcp.<tool>`` actions this module's tools ask the authorizer about. ``identity.py``
#: ORs them into ``MCP_ACTIONS``; a tool not listed there is refused.
IWP_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_iwps",
        "mcp.get_iwp",
        "mcp.list_iwp_scope",
        "mcp.get_iwp_readiness",
        "mcp.list_constraints",
        "mcp.get_constraint",
        "mcp.constraint_groups",
        "mcp.propose_constraint",
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
Word = Annotated[str, Field(min_length=1, max_length=MAX_PART)]
Severity = Literal["blocking", "advisory"]
Category = Literal[
    "materials",
    "labour",
    "scaffold",
    "equipment",
    "permit",
    "engineering",
    "rfi",
    "predecessor",
    "other",
]
GroupBy = Literal["owner", "category", "age"]


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


class ConstraintList(BaseModel):
    """The constraints a viewer may read, and how many the same filters find in all."""

    rows: list[ConstraintView]
    total: int


class ConstraintGroups(BaseModel):
    """The review groups, and whether more visible constraints exist than the groups cover."""

    groups: list[ConstraintGroup]
    truncated: bool


def _scope(project: str) -> str:
    return f"project:{project}"


def require_view(conn: Connection, scope: str, actor: str) -> None:
    """The entry check of every constraint read: ``actor`` holds ``core.constraint.view``.

    Copied from ``tl_cli.constraint_read.require_view`` (tl-mcp does not import tl-cli). A refusal
    is a ``ForbiddenError``, which ``guarded`` turns into the tool's normal access error.
    """
    require_word(
        conn,
        holder_for_actor(conn, actor),
        scope=scope,
        module=ACCESS_MODULE,
        word=normalise_word(VIEW_WORD),
        what=VIEW_WORD,
    )


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


def list_constraints_impl(
    ctx: McpContext,
    *,
    project: str,
    subject: str | None,
    state: str | None,
    category: str | None,
    phase: str | None,
    blocking: bool | None,
    owner: str | None,
) -> ConstraintList:
    """The project's constraints by key, with the total the same filters find. A subject key the
    viewer cannot see, or that does not exist, finds nothing (rows [], total 0)."""
    scope = _scope(project)
    with ctx.factory(True) as uow:
        conn = uow.conn()
        require_view(conn, scope, ctx.actor)
        subject_id: str | None = None
        if subject is not None:
            found = get_record(uow, scope, subject)
            if found is None:
                return ConstraintList(rows=[], total=0)
            subject_id = str(found["id"])
        filters = {
            "subject_id": subject_id,
            "state": state,
            "category": category,
            "phase": phase,
            "blocking": blocking,
            "owner": owner,
        }
        return ConstraintList(
            rows=list_constraints(conn, scope, **filters),
            total=count_constraints(conn, scope, **filters),
        )


def get_constraint_impl(ctx: McpContext, *, project: str, key: str) -> ConstraintView:
    """One constraint by key. A missing key and a hidden subject answer the same error."""
    scope = _scope(project)
    with ctx.factory(True) as uow:
        conn = uow.conn()
        require_view(conn, scope, ctx.actor)
        record = get_record(uow, scope, key)
        found = None
        if record is not None and record["type"] == RECORD_TYPE:
            found = get_constraint(conn, str(record["id"]))
    if found is None:
        raise RecordNotFoundError(f"no constraint {key!r} in project {project!r}")
    return found


def constraint_groups_impl(ctx: McpContext, *, project: str, by: GroupBy) -> ConstraintGroups:
    """The visible constraints of a project grouped by owner, category or age."""
    scope = _scope(project)
    with ctx.factory(True) as uow:
        conn = uow.conn()
        require_view(conn, scope, ctx.actor)
        views = list_constraints(conn, scope, limit=MAX_LIMIT)
        total = count_constraints(conn, scope)
    return ConstraintGroups(groups=review_groups(views, by), truncated=total > MAX_LIMIT)


def propose_constraint_impl(
    ctx: McpContext,
    *,
    project: str,
    subject: str,
    phase: str,
    severity: Severity,
    category: Category,
    owner: str | None,
    description: str | None,
    due_at: str | None,
    summary: str | None,
) -> ProposalResult:
    scope = _scope(project)
    with ctx.factory(True) as uow:
        subject_id = _resolve(uow, scope, subject)
    command = RaiseConstraint(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        subject=subject_id,
        phase=phase,
        severity=severity,
        category=category,
        owner=owner,
        description=description,
        due_at=due_at,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_constraint",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Raise a {severity} {category} constraint on {subject}",
    )
    return _result(view)


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
    """Add the seven read tools and the two proposing tools to ``server``."""

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

    @server.tool(annotations=READ_ONLY)
    def list_constraints(
        project: Project,
        subject: Annotated[
            str | None, Field(min_length=1, max_length=MAX_PART, description="The subject's key.")
        ] = None,
        state: Annotated[
            str | None, Field(min_length=1, max_length=MAX_PART, description="The state.")
        ] = None,
        category: Annotated[
            str | None, Field(min_length=1, max_length=MAX_PART, description="The category.")
        ] = None,
        phase: Annotated[
            str | None, Field(min_length=1, max_length=MAX_PART, description="The phase.")
        ] = None,
        blocking: Annotated[bool | None, Field(description="Blocking or advisory.")] = None,
        owner: Annotated[
            str | None, Field(min_length=1, max_length=MAX_PART, description="The owner.")
        ] = None,
    ) -> ConstraintList:
        """List a project's constraints by key, with the total the same filters find.

        A subject you may not see, or that does not exist, finds nothing.
        """
        with guarded(ctx, "list_constraints", resource_name("constraints", project)):
            return list_constraints_impl(
                ctx,
                project=project,
                subject=subject,
                state=state,
                category=category,
                phase=phase,
                blocking=blocking,
                owner=owner,
            )

    @server.tool(annotations=READ_ONLY)
    def get_constraint(project: Project, key: Key) -> ConstraintView:
        """Get one constraint by its key, with its state, subject and target.

        A constraint that does not exist, or whose subject you may not read, gives the same error.
        """
        with guarded(ctx, "get_constraint", resource_name("constraint", project, key)):
            return get_constraint_impl(ctx, project=project, key=key)

    @server.tool(annotations=READ_ONLY)
    def constraint_groups(
        project: Project,
        by: Annotated[GroupBy, Field(description="Group by `owner`, `category` or `age`.")],
    ) -> ConstraintGroups:
        """Group a project's visible constraints by owner, category or age (the review queue).

        Groups cover at most the first 500 visible constraints by key; `truncated` is true when
        more are visible.
        """
        with guarded(ctx, "constraint_groups", resource_name("constraints", project)):
            return constraint_groups_impl(ctx, project=project, by=by)

    @server.tool(annotations=PROPOSES)
    def propose_constraint(
        project: Project,
        subject: Annotated[Key, Field(description="The key of the record the constraint is on.")],
        phase: Annotated[
            Word, Field(description="The phase the constraint gates, for example `ready`.")
        ],
        severity: Annotated[Severity, Field(description="Blocking or advisory.")],
        category: Annotated[Category, Field(description="The constraint's category.")],
        owner: Annotated[
            str | None, Field(max_length=MAX_PART, description="The actor who owns it.")
        ] = None,
        description: Annotated[
            str | None, Field(max_length=MAX_PART, description="What the constraint is.")
        ] = None,
        due_at: Annotated[
            str | None, Field(max_length=MAX_PART, description="When it is due.")
        ] = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a manual constraint on a record.

        Nothing is raised now. The proposal is checked now, so an error means it could not be
        applied. A person who may act on constraints accepts it in the review queue.
        """
        with guarded(ctx, "propose_constraint", resource_name("constraints", project)):
            return propose_constraint_impl(
                ctx,
                project=project,
                subject=subject,
                phase=phase,
                severity=severity,
                category=category,
                owner=owner,
                description=description,
                due_at=due_at,
                summary=summary,
            )

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
