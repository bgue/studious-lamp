"""Requisition tools (P2-I4A-T08b): four reads and one proposal.

The reads answer from ``tl_mod_requisitions.views`` under the agent's viewer
(``confidentiality.current_viewer()``). Every read names its resource for the authorizer
(``guarded``) and reads as the lowest clearance, so a hidden record answers as a missing one.

``propose_requisition`` files a pending proposal (``proposals.submit``); nothing changes until a
person with the ``user`` word accepts it, and the accepting person is the requester (ADR-0014
section 8, ADR-0027). The IWP or CWP it serves and any material item are named by key and resolved
under the agent's viewer; an unknown or hidden key answers one text. There is no ``requester``
argument: the requester is whoever accepts.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field
from tl_core import confidentiality
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_requisitions import views
from tl_mod_requisitions.api import RequisitionRow, WorkOrderRow
from tl_mod_requisitions.commands import (
    MAX_CRAFT,
    MAX_LINES,
    MAX_PURPOSE,
    MAX_SUBJECT,
    Priority,
    RaiseRequisition,
)

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
REQUISITION_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_requisitions",
        "mcp.get_requisition",
        "mcp.list_work_orders",
        "mcp.get_work_order",
        "mcp.propose_requisition",
    }
)

#: The kinds of requisition an agent may propose (the ``kind`` of ``RaiseRequisition``).
Kind = Literal["labor", "material", "general", "scaffold"]

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Key = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="A record's key, for example `P123-REQ-LAB-0001`.",
    ),
]


class LineArg(BaseModel):
    """One material line: a project item by its key, a quantity and its unit."""

    model_config = ConfigDict(extra="forbid")

    item: Annotated[
        str,
        Field(min_length=1, max_length=MAX_PART, description="The item's record key."),
    ]
    qty: Annotated[
        str,
        Field(min_length=1, max_length=20, description="The quantity, for example `4` or `2.5`."),
    ]
    uom: Annotated[
        str,
        Field(min_length=1, max_length=8, description="The unit of measure, for example `EA`."),
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


def list_requisitions_impl(
    ctx: McpContext,
    *,
    project: str,
    kind: str | None,
    state: str | None,
    requester: str | None,
    for_key: str | None,
) -> list[RequisitionRow]:
    """The project's requisitions by key, hidden ones left out, optionally filtered."""
    scope = _scope(project)
    with ctx.factory(True) as uow:
        for_id = None if for_key is None else _resolve(uow, scope, for_key)
        return views.requisition_list(
            uow.conn(),
            scope,
            kind=kind,
            state=state,
            requester=requester,
            for_record=for_id,
            viewer=confidentiality.current_viewer(),
        )


def get_requisition_impl(ctx: McpContext, *, project: str, key: str) -> views.RequisitionDetail:
    """One requisition with its kind's fields and its work order. A missing, hidden or
    other-project key answers the same error."""
    with ctx.factory(True) as uow:
        found = views.requisition_detail(
            uow.conn(), _scope(project), key, viewer=confidentiality.current_viewer()
        )
    if found is None:
        raise RecordNotFoundError(f"no requisition {key!r} in project {project!r}")
    return found


def list_work_orders_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    assigned_to: str | None,
) -> list[WorkOrderRow]:
    """The project's work orders by key, those of hidden requisitions left out."""
    with ctx.factory(True) as uow:
        return views.work_order_list(
            uow.conn(),
            _scope(project),
            state=state,
            assigned_to=assigned_to,
            viewer=confidentiality.current_viewer(),
        )


def get_work_order_impl(ctx: McpContext, *, project: str, key: str) -> views.WorkOrderDetail:
    """One work order with the key of its requisition. A missing, hidden or other-project key
    answers the same error."""
    with ctx.factory(True) as uow:
        found = views.work_order_detail(
            uow.conn(), _scope(project), key, viewer=confidentiality.current_viewer()
        )
    if found is None:
        raise RecordNotFoundError(f"no work order {key!r} in project {project!r}")
    return found


def _requisition_body(
    kind: Kind,
    *,
    subject: str,
    need_by: str | None,
    priority: Priority | None,
    craft: str | None,
    headcount: int | None,
    start_date: str | None,
    end_date: str | None,
    lines: list[dict[str, Any]] | None,
    general_type: str | None,
    purpose: str | None,
    duration_days: int | None,
) -> dict[str, Any]:
    """The ``requisition`` body of ``RaiseRequisition``: only the fields given. A field the kind
    does not take is left in, and the command model refuses it (``extra`` is forbidden)."""
    fields: dict[str, Any] = {
        "kind": kind,
        "subject": subject,
        "need_by": need_by,
        "priority": priority,
        "craft": craft,
        "headcount": headcount,
        "start_date": start_date,
        "end_date": end_date,
        "lines": lines,
        "general_type": general_type,
        "purpose": purpose,
        "duration_days": duration_days,
    }
    return {name: value for name, value in fields.items() if value is not None}


def propose_requisition_impl(
    ctx: McpContext,
    *,
    project: str,
    kind: Kind,
    subject: str,
    need_by: str | None,
    priority: Priority | None,
    for_key: str | None,
    craft: str | None,
    headcount: int | None,
    start_date: str | None,
    end_date: str | None,
    lines: list[LineArg] | None,
    general_type: str | None,
    purpose: str | None,
    duration_days: int | None,
    summary: str | None,
    intent: Intent | None = None,
) -> ProposalResult:
    scope = _scope(project)
    with ctx.factory(True) as uow:
        for_id = None if for_key is None else _resolve(uow, scope, for_key)
        line_bodies: list[dict[str, Any]] | None = (
            None
            if lines is None
            else [
                {"item_id": _resolve(uow, scope, line.item), "qty": line.qty, "uom": line.uom}
                for line in lines
            ]
        )
    body = _requisition_body(
        kind,
        subject=subject,
        need_by=need_by,
        priority=priority,
        craft=craft,
        headcount=headcount,
        start_date=start_date,
        end_date=end_date,
        lines=line_bodies,
        general_type=general_type,
        purpose=purpose,
        duration_days=duration_days,
    )
    # ``model_validate`` runs the command model's own checks: a missing kind field, a field of
    # another kind, or a bad value is a ``ValueError`` with the model's text.
    command = RaiseRequisition.model_validate(
        {
            "actor": ctx.actor,
            "source": proposals.source_for(ctx.actor),
            "scope": scope,
            "requisition": body,
            "for_record_id": for_id,
            "intent": intent,
        }
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_requisition",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Raise a {kind} requisition: {subject}",
    )
    return _result(view)


def register_requisition_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the four requisition read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_requisitions(
        project: Project,
        kind: Annotated[
            Kind | None,
            Field(description="Only requisitions of this kind."),
        ] = None,
        state: Annotated[
            str | None,
            Field(
                min_length=1, max_length=MAX_PART, description="Only requisitions in this state."
            ),
        ] = None,
        requester: Annotated[
            str | None,
            Field(
                min_length=1, max_length=MAX_PART, description="Only requisitions by this person."
            ),
        ] = None,
        for_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only those serving this IWP or CWP key.",
            ),
        ] = None,
    ) -> list[RequisitionRow]:
        """List a project's requisitions by key (labour, material, general and scaffold).

        Hidden requisitions are left out. Use `get_requisition` for one requisition's fields.
        """
        with guarded(ctx, "list_requisitions", resource_name("requisitions", project)):
            return list_requisitions_impl(
                ctx,
                project=project,
                kind=kind,
                state=state,
                requester=requester,
                for_key=for_key,
            )

    @server.tool(annotations=READ_ONLY)
    def get_requisition(project: Project, key: Key) -> views.RequisitionDetail:
        """Get one requisition with its kind's fields and its work order, if it has one.

        A requisition that does not exist, or that you may not read, gives the same error.
        """
        with guarded(ctx, "get_requisition", resource_name("requisition", project, key)):
            return get_requisition_impl(ctx, project=project, key=key)

    @server.tool(annotations=READ_ONLY)
    def list_work_orders(
        project: Project,
        state: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only work orders in this state."),
        ] = None,
        assigned_to: Annotated[
            str | None,
            Field(
                min_length=1, max_length=MAX_PART, description="Only work orders of this person."
            ),
        ] = None,
    ) -> list[WorkOrderRow]:
        """List a project's work orders by key. Work orders of hidden requisitions are left out."""
        with guarded(ctx, "list_work_orders", resource_name("work_orders", project)):
            return list_work_orders_impl(ctx, project=project, state=state, assigned_to=assigned_to)

    @server.tool(annotations=READ_ONLY)
    def get_work_order(project: Project, key: Key) -> views.WorkOrderDetail:
        """Get one work order with the key of the requisition it belongs to.

        A work order that does not exist, or that you may not read, gives the same error.
        """
        with guarded(ctx, "get_work_order", resource_name("work_order", project, key)):
            return get_work_order_impl(ctx, project=project, key=key)

    @server.tool(annotations=PROPOSES)
    def propose_requisition(
        project: Project,
        kind: Annotated[Kind, Field(description="labor, material, general or scaffold.")],
        subject: Annotated[
            str,
            Field(min_length=1, max_length=MAX_SUBJECT, description="What is needed, in one line."),
        ],
        need_by: Annotated[
            str | None,
            Field(max_length=10, description="The date it is needed, `YYYY-MM-DD`."),
        ] = None,
        priority: Annotated[
            Priority | None,
            Field(description="low, normal (the default), high or urgent."),
        ] = None,
        for_key: Annotated[
            str | None,
            Field(
                min_length=1, max_length=MAX_PART, description="The key of the IWP or CWP served."
            ),
        ] = None,
        craft: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_CRAFT, description="labor: the craft."),
        ] = None,
        headcount: Annotated[
            int | None,
            Field(ge=1, le=500, description="labor: how many people."),
        ] = None,
        start_date: Annotated[
            str | None,
            Field(max_length=10, description="labor: the first day, `YYYY-MM-DD`."),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(max_length=10, description="labor: the last day, `YYYY-MM-DD`."),
        ] = None,
        lines: Annotated[
            list[LineArg],
            Field(min_length=1, max_length=MAX_LINES, description="material: the lines."),
        ]
        | None = None,
        general_type: Annotated[
            str | None,
            Field(
                min_length=1, max_length=MAX_PART, description="general: the requisition type code."
            ),
        ] = None,
        purpose: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PURPOSE, description="scaffold: what it is for."),
        ] = None,
        duration_days: Annotated[
            int | None,
            Field(ge=1, le=1000, description="scaffold: how many days it is needed."),
        ] = None,
        intent: IntentParam = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a new requisition (labor, material, general or scaffold).

        Nothing is raised now. A person who may raise requisitions accepts it in the review queue,
        and that person becomes its requester.
        """
        with guarded(ctx, "propose_requisition", resource_name("requisition", project)):
            return propose_requisition_impl(
                ctx,
                project=project,
                kind=kind,
                subject=subject,
                need_by=need_by,
                priority=priority,
                for_key=for_key,
                craft=craft,
                headcount=headcount,
                start_date=start_date,
                end_date=end_date,
                lines=lines,
                general_type=general_type,
                purpose=purpose,
                duration_days=duration_days,
                summary=summary,
                intent=intent,
            )
