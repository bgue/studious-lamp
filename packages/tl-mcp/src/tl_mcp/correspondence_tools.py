"""Correspondence tools: read the register, ask the suggestion engine, propose a triage (P1-I5).

``list_correspondence``, ``get_correspondence``, ``list_response_clocks``, ``list_parties`` and
``suggest_triage`` only read. ``propose_triage`` never changes anything: it builds the
``ConfirmTriage`` command the API would run, has the handler's own checks run when a person accepts
it, and files a pending proposal. An agent never triages, issues or classifies an item itself
(brief 9 M10: agents propose only).

**What an agent can read is ADR-0016:** an agent reads items of the class `internal` only; an item
of any other class does not exist for it, in a list or by number (the same "not found").
The response models are the module's (``tl_mod_correspondence.views``).
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_core.services import proposals
from tl_mod_correspondence import views
from tl_mod_correspondence.handlers.triage import ConfirmTriage

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Number = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The item number, `P123-COR-0001`."),
]


def list_correspondence_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    domain: str | None,
    awaiting_response: bool,
) -> list[views.RegisterLineView]:
    with ctx.factory(True) as uow:
        return views.register(
            uow.conn(),
            f"project:{project}",
            state=state,
            domain=domain,
            awaiting_response=awaiting_response,
            limit=500,
        )


def get_correspondence_impl(ctx: McpContext, *, project: str, number: str) -> views.ItemView:
    with ctx.factory(True) as uow:
        return views.item_view(uow.conn(), f"project:{project}", number)


def list_response_clocks_impl(
    ctx: McpContext, *, project: str, overdue_only: bool
) -> list[views.ClockView]:
    with ctx.factory(True) as uow:
        return views.clock_views(uow.conn(), f"project:{project}", overdue_only=overdue_only)


def list_parties_impl(ctx: McpContext, *, project: str) -> list[views.PartyView]:
    with ctx.factory(True) as uow:
        return views.party_views(uow.conn(), f"project:{project}")


def suggest_triage_impl(ctx: McpContext, *, project: str, number: str) -> views.SuggestionView:
    with ctx.factory(True) as uow:
        return views.suggestion_for_item(uow.conn(), f"project:{project}", number)


def propose_triage_impl(
    ctx: McpContext,
    *,
    project: str,
    number: str,
    domain: str,
    subtype: str,
    referenced_ids: list[str],
    summary: str | None,
) -> ProposalResult:
    scope = f"project:{project}"
    with ctx.factory(True) as uow:
        item = views.item_view(uow.conn(), scope, number)  # a hidden item is "not found" here
    command = ConfirmTriage(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        stream_id=item.id,
        domain=domain,
        subtype=subtype,
        referenced_ids=referenced_ids,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_triage",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Triage {item.number} as {domain}/{subtype}",
    )
    return _result(view)


def register_correspondence_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the five read tools and the triage proposal to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_correspondence(
        project: Project,
        state: Annotated[
            str | None, Field(max_length=MAX_PART, description="An item state, e.g. `Received`.")
        ] = None,
        domain: Annotated[
            str | None, Field(max_length=MAX_PART, description="A domain code, e.g. `general`.")
        ] = None,
        awaiting_response: Annotated[
            bool, Field(description="Only items that want an answer and have none.")
        ] = False,
    ) -> list[views.RegisterLineView]:
        """List a project's correspondence register (brief 9 M10), newest first.

        Each line is a letter, email or minutes item or a register source row (an I2 transmittal
        appears as a Document-control item).

        Confidentiality is enforced (ADR-0016): an agent reads `internal` items only; an item of
        any other class does not exist for it.
        """
        with guarded(ctx, "list_correspondence", resource_name("correspondence", project)):
            return list_correspondence_impl(
                ctx,
                project=project,
                state=state,
                domain=domain,
                awaiting_response=awaiting_response,
            )

    @server.tool(annotations=READ_ONLY)
    def get_correspondence(project: Project, number: Number) -> views.ItemView:
        """Get one correspondence item: its text, recipients, domain, thread and clocks.

        Confidentiality is enforced (ADR-0016): an agent reads `internal` items only; an item of
        any other class does not exist for it.
        """
        with guarded(ctx, "get_correspondence", resource_name("correspondence", project, number)):
            return get_correspondence_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def list_response_clocks(
        project: Project,
        overdue_only: Annotated[
            bool, Field(description="Only clocks past their due date.")
        ] = False,
    ) -> list[views.ClockView]:
        """List response clocks, soonest due first, with the days left as of today.

        A clock counts calendar or working days on the project's calendar. `effective_state` is
        `expired` for a running clock past its due date. Clocks of items an agent cannot read are
        not listed (ADR-0016).
        """
        with guarded(ctx, "list_response_clocks", resource_name("clocks", project)):
            return list_response_clocks_impl(ctx, project=project, overdue_only=overdue_only)

    @server.tool(annotations=READ_ONLY)
    def list_parties(project: Project) -> list[views.PartyView]:
        """List a project's parties (organisations we write to) with their contacts."""
        with guarded(ctx, "list_parties", resource_name("parties", project)):
            return list_parties_impl(ctx, project=project)

    @server.tool(annotations=READ_ONLY)
    def suggest_triage(project: Project, number: Number) -> views.SuggestionView:
        """Ask the suggestion engine which domain and subtype a received item probably belongs to.

        The answer lists the score of every domain and the keywords that matched. It is only a
        suggestion: use `propose_triage` to put it to a person, who decides.
        """
        with guarded(ctx, "suggest_triage", resource_name("correspondence", project, number)):
            return suggest_triage_impl(ctx, project=project, number=number)

    @server.tool(annotations=PROPOSES)
    def propose_triage(
        project: Project,
        number: Number,
        domain: Annotated[str, Field(min_length=1, max_length=MAX_PART)],
        subtype: Annotated[str, Field(min_length=1, max_length=MAX_PART)],
        referenced_ids: Annotated[
            list[Annotated[str, Field(min_length=1, max_length=MAX_PART)]],
            Field(
                max_length=50,
                description="Record ids the item refers to; each gets a `references` link.",
            ),
        ] = [],  # noqa: B006 - copied before use, never mutated
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose the domain and subtype of a received item. A person must accept it.

        Nothing changes until a person accepts the proposal in the review queue; accepting runs
        the triage as that person (the clocks the subtype starts on receipt start then).
        """
        with guarded(ctx, "propose_triage", resource_name("correspondence", project, number)):
            return propose_triage_impl(
                ctx,
                project=project,
                number=number,
                domain=domain,
                subtype=subtype,
                referenced_ids=list(referenced_ids),
                summary=summary,
            )
