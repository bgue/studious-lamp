"""Correspondence tools: read the register, ask the suggestion engine, propose a triage (P1-I5).

``list_correspondence``, ``get_correspondence``, ``list_response_clocks``, ``list_parties``,
``suggest_triage`` and, from P1-I6, ``list_rfis``, ``get_rfi``, ``list_commercial_items``,
``get_commercial_item`` and ``get_evidence_trail`` only read. ``propose_triage`` never changes
anything: it builds the ``ConfirmTriage`` command the API would run, has the handler's own checks
run when a person accepts it, and files a pending proposal. An agent never triages, issues or
classifies an item itself (brief 9 M10: agents propose only).

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
from tl_mod_correspondence import (
    evidence,
    reports_commercial,
    reports_technical,
    views,
    views_domain,
)
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


def list_rfis_impl(
    ctx: McpContext, *, project: str, state: str | None, only_open: bool, only_overdue: bool
) -> reports_technical.RfiLog:
    with ctx.factory(True) as uow:
        return reports_technical.rfi_log(
            uow.conn(),
            f"project:{project}",
            state=state,
            only_open=only_open,
            only_overdue=only_overdue,
            limit=500,
        )


def get_rfi_impl(ctx: McpContext, *, project: str, number: str) -> views_domain.TechnicalView:
    with ctx.factory(True) as uow:
        return views_domain.technical_view(uow.conn(), f"project:{project}", number)


def list_commercial_items_impl(
    ctx: McpContext, *, project: str, state: str | None, time_bars_only: bool
) -> reports_commercial.CommercialRegister:
    with ctx.factory(True) as uow:
        return reports_commercial.commercial_register(
            uow.conn(),
            f"project:{project}",
            state=state,
            time_bars_only=time_bars_only,
            limit=500,
        )


def get_commercial_item_impl(
    ctx: McpContext, *, project: str, number: str
) -> views_domain.CommercialView:
    with ctx.factory(True) as uow:
        return views_domain.commercial_view(uow.conn(), f"project:{project}", number)


def get_evidence_trail_impl(
    ctx: McpContext, *, project: str, number: str, as_of: str | None, depth: int
) -> evidence.EvidenceTrail:
    with ctx.factory(True) as uow:
        return evidence.evidence_trail(
            uow.conn(), f"project:{project}", number, as_of, depth=depth, max_nodes=100
        )


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
    """Add the ten read tools and the triage proposal to ``server``."""

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

    @server.tool(annotations=READ_ONLY)
    def list_rfis(
        project: Project,
        state: Annotated[
            str | None, Field(max_length=MAX_PART, description="A state, e.g. `Awaiting response`.")
        ] = None,
        only_open: Annotated[bool, Field(description="Not answered and not closed.")] = False,
        only_overdue: Annotated[
            bool, Field(description="Awaiting a response past the day it was needed.")
        ] = False,
    ) -> reports_technical.RfiLog:
        """The RFI log (brief 9 M10): requests for information, technical queries and deviation
        requests with their response times, overdue flags and impact flags (what the raiser
        expected and what the answer said about cost and schedule), newest first.

        Confidentiality is enforced (ADR-0016): an agent reads `internal` items only.
        """
        with guarded(ctx, "list_rfis", resource_name("rfis", project)):
            return list_rfis_impl(
                ctx, project=project, state=state, only_open=only_open, only_overdue=only_overdue
            )

    @server.tool(annotations=READ_ONLY)
    def get_rfi(project: Project, number: Number) -> views_domain.TechnicalView:
        """Get one RFI, technical query or deviation request: the question, the answer, the
        impact statements, the clocks and the commercial items raised from it.

        Confidentiality is enforced (ADR-0016): an agent reads `internal` items only.
        """
        with guarded(ctx, "get_rfi", resource_name("rfis", project, number)):
            return get_rfi_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def list_commercial_items(
        project: Project,
        state: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="A state, e.g. `Awaiting assessment`."),
        ] = None,
        time_bars_only: Annotated[
            bool, Field(description="Only items whose time bar is running or was late.")
        ] = False,
    ) -> reports_commercial.CommercialRegister:
        """The Commercial register: notices and claims with their values (estimated against
        assessed, totalled per currency) and time bars.

        Commercial items are `restricted` (ADR-0016): an agent reads none of them, so its register
        is empty.
        """
        with guarded(ctx, "list_commercial_items", resource_name("commercial", project)):
            return list_commercial_items_impl(
                ctx, project=project, state=state, time_bars_only=time_bars_only
            )

    @server.tool(annotations=READ_ONLY)
    def get_commercial_item(project: Project, number: Number) -> views_domain.CommercialView:
        """Get one Commercial item: values, clause, awareness day, time bar clocks, assessment.

        Commercial items are `restricted` (ADR-0016): an agent gets "not found".
        """
        with guarded(ctx, "get_commercial_item", resource_name("commercial", project, number)):
            return get_commercial_item_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def get_evidence_trail(
        project: Project,
        number: Number,
        as_of: Annotated[
            str | None,
            Field(
                max_length=10,
                description="A day, YYYY-MM-DD (default today): the ledger is replayed to its end.",
            ),
        ] = None,
        depth: Annotated[int, Field(ge=0, le=3, description="Links to follow.")] = 2,
    ) -> evidence.EvidenceTrail:
        """The chain of records linked to an item as it stood at the end of a day: correspondence,
        RFIs, documents at the pinned revision, schedule activities, cost codes, each with its
        state then and the status of the link then.

        A record or link an agent cannot read today is left out, whatever its class was then.
        """
        with guarded(ctx, "get_evidence_trail", resource_name("correspondence", project, number)):
            return get_evidence_trail_impl(
                ctx, project=project, number=number, as_of=as_of, depth=depth
            )

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
