"""Punch tools (P2-PUNCH-T05): two reads and one proposal.

The reads answer from ``tl_mod_quality.views`` under ``confidentiality.current_viewer()``, the
viewer ``guarded`` sets (the lowest clearance for an agent), so a hidden item answers as a missing
one. ``get_punch_item`` answers one error for a missing, hidden and other-project key.

``propose_punch_item`` files a pending proposal of ``RaisePunchItem`` (``proposals.submit``);
nothing changes until a person with the ``user`` word accepts it (ADR-0014 section 8, ADR-0027).
``from_key`` is resolved to an id under the agent's viewer; an unknown or hidden key answers one
text. There is no tool that clears, verifies, reopens or voids a punch item.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field
from tl_core import confidentiality
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_quality import views as punch_views
from tl_mod_quality.commands import (
    MAX_ASSIGNEE,
    MAX_DESCRIPTION,
    MAX_SHORT,
    MAX_SUBJECT,
    RaisePunchItem,
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

#: The three ``mcp.<tool>`` actions this module's tools ask the authorizer about. ``identity.py``
#: ORs them into ``MCP_ACTIONS``; a tool not listed there is refused.
PUNCH_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_punch_items",
        "mcp.get_punch_item",
        "mcp.propose_punch_item",
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
        description="A punch item's key, for example `P123-PUN-0001`.",
    ),
]
Category = Annotated[
    Literal["A", "B", "C"] | None,
    Field(description="The category: A, B or C (default B when proposing)."),
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


def list_punch_items_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    area: str | None,
    system: str | None,
    assignee: str | None,
    category: str | None,
    overdue: bool,
) -> punch_views.PunchPage:
    """The project's visible punch items by key, with the total of the matches."""
    with ctx.factory(True) as uow:
        return punch_views.punch_list(
            uow.conn(),
            _scope(project),
            state=state,
            area=area,
            system=system,
            assignee=assignee,
            category=category,
            overdue=overdue,
            today=date.today().isoformat(),
            viewer=confidentiality.current_viewer(),
        )


def get_punch_item_impl(ctx: McpContext, *, project: str, key: str) -> punch_views.PunchDetail:
    """One punch item. A missing, hidden or other-project item answers the same error."""
    with ctx.factory(True) as uow:
        found = punch_views.punch_detail(
            uow.conn(), _scope(project), key, viewer=confidentiality.current_viewer()
        )
    if found is None:
        raise RecordNotFoundError(f"no punch item {key}")
    return found


def propose_punch_item_impl(
    ctx: McpContext,
    *,
    project: str,
    subject: str,
    fields: dict[str, Any],
    from_key: str | None,
    summary: str | None,
    intent: Intent | None = None,
) -> ProposalResult:
    scope = _scope(project)
    from_id: str | None = None
    if from_key is not None:
        with ctx.factory(True) as uow:
            from_id = _resolve(uow, scope, from_key)
    command = RaisePunchItem(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        subject=subject,
        from_record_id=from_id,
        intent=intent,
        **{name: value for name, value in fields.items() if value is not None},
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_punch_item",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Raise punch item: {subject}",
    )
    return _result(view)


def register_punch_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the two punch read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_punch_items(
        project: Project,
        state: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only items in this state: Open, Cleared, Verified or Void.",
            ),
        ] = None,
        area: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only items in this area."),
        ] = None,
        system: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only items in this system."),
        ] = None,
        assignee: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="Only items of this assignee."),
        ] = None,
        category: Category = None,
        overdue: Annotated[
            bool, Field(description="Only Open items whose due date is before today.")
        ] = False,
    ) -> punch_views.PunchPage:
        """List a project's punch items by key, with the total number of matches.

        Use `get_punch_item` for one item's fields and history. Items you may not read are left out.
        """
        with guarded(ctx, "list_punch_items", resource_name("punch", project)):
            return list_punch_items_impl(
                ctx,
                project=project,
                state=state,
                area=area,
                system=system,
                assignee=assignee,
                category=category,
                overdue=overdue,
            )

    @server.tool(annotations=READ_ONLY)
    def get_punch_item(project: Project, key: Key) -> punch_views.PunchDetail:
        """Get one punch item with its fields, clearing, verification and reopen history.

        An item that does not exist, that you may not read, or that is in another project gives
        the same error.
        """
        with guarded(ctx, "get_punch_item", resource_name("punch", project, key)):
            return get_punch_item_impl(ctx, project=project, key=key)

    @server.tool(annotations=PROPOSES)
    def propose_punch_item(
        project: Project,
        subject: Annotated[
            str,
            Field(min_length=1, max_length=MAX_SUBJECT, description="The punch item's subject."),
        ],
        description: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_DESCRIPTION, description="What is wrong."),
        ] = None,
        area: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_SHORT, description="The area it is in."),
        ] = None,
        system: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_SHORT, description="The system it belongs to."),
        ] = None,
        due_on: Annotated[
            str | None,
            Field(max_length=10, description="The due date, YYYY-MM-DD."),
        ] = None,
        category: Category = None,
        assignee: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_ASSIGNEE, description="Who clears the item."),
        ] = None,
        from_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="The key of the record it was raised from, for example an IWP.",
            ),
        ] = None,
        summary: Summary = None,
        intent: IntentParam = None,
    ) -> ProposalResult:
        """Propose a new punch item.

        Nothing is raised now. A person who may raise punch items accepts it in the review queue.
        """
        fields: dict[str, Any] = {
            "description": description,
            "area": area,
            "system": system,
            "due_on": due_on,
            "category": category,
            "assignee": assignee,
        }
        with guarded(ctx, "propose_punch_item", resource_name("punch", project)):
            return propose_punch_item_impl(
                ctx,
                project=project,
                subject=subject,
                fields=fields,
                from_key=from_key,
                summary=summary,
                intent=intent,
            )
