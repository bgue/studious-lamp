"""Document control read tools: documents, revisions, stale links, reviews, transmittals (P1-I2).

Seven read-only tools. An agent that proposes a link to a document, or reports on what is overdue,
needs to know which revisions exist, what is current, which links went stale and what is waiting
for an answer; these answer from the register. Changing any of it stays a person's work (issuing,
superseding and voiding are an admin's acts, ADR-0011, and an agent only proposes): none of these
tools writes. The response models are the module's (``tl_mod_documents.views`` and ``reports``),
so an agent, the API and a screen see the same fields.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_mod_documents import reports, views

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Number = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The document number, `ISO-1234`."),
]


def list_documents_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    doc_type: str | None,
    discipline: str | None,
    include_void: bool,
) -> list[views.DocumentView]:
    """The project's documents by number, without revisions or links."""
    with ctx.factory(True) as uow:
        return views.document_views(
            uow.conn(),
            f"project:{project}",
            doc_type=doc_type,
            discipline=discipline,
            state=state,
            include_void=include_void,
            limit=500,
        )


def get_document_impl(ctx: McpContext, *, project: str, number: str) -> views.DocumentView:
    """One document with its revisions, renditions and the links to it."""
    with ctx.factory(True) as uow:
        return views.document_view(uow.conn(), f"project:{project}", number)


def get_document_diff_impl(
    ctx: McpContext, *, project: str, number: str, from_code: str, to_code: str
) -> views.RevisionDiffView:
    """What changed between two issued revisions of a document."""
    with ctx.factory(True) as uow:
        return views.revision_diff_view(
            uow.conn(), f"project:{project}", number, from_code, to_code
        )


def list_stale_links_impl(ctx: McpContext, *, project: str) -> list[reports.StalePinLine]:
    """Links to documents whose pin is behind or whose document was voided or superseded."""
    with ctx.factory(True) as uow:
        return views.stale_links(uow.conn(), f"project:{project}")


def list_overdue_reviews_impl(
    ctx: McpContext, *, project: str, on: str | None
) -> list[reports.OverdueLine]:
    """Open reviews with a reviewer who has not answered by their date."""
    day = date.fromisoformat(on) if on is not None else None
    with ctx.factory(True) as uow:
        return views.overdue_reviews(uow.conn(), f"project:{project}", on=day)


def list_transmittals_impl(
    ctx: McpContext, *, project: str, state: str | None, direction: str | None
) -> list[views.TransmittalView]:
    """The project's transmittals by number, without items."""
    with ctx.factory(True) as uow:
        return views.transmittal_views(
            uow.conn(), f"project:{project}", state=state, direction=direction, limit=500
        )


def get_transmittal_impl(ctx: McpContext, *, project: str, number: str) -> views.TransmittalView:
    """One transmittal with its items."""
    with ctx.factory(True) as uow:
        return views.transmittal_view(uow.conn(), f"project:{project}", number)


def register_document_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the seven read tools to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_documents(
        project: Project,
        state: Annotated[
            str | None, Field(max_length=MAX_PART, description="A document state, e.g. `Issued`.")
        ] = None,
        doc_type: Annotated[
            str | None, Field(max_length=MAX_PART, description="A document type code, e.g. `ISO`.")
        ] = None,
        discipline: Annotated[
            str | None, Field(max_length=MAX_PART, description="A discipline code, e.g. `PIP`.")
        ] = None,
        include_void: Annotated[bool, Field(description="Include void documents.")] = False,
    ) -> list[views.DocumentView]:
        """List a project's controlled documents (brief 9 M1) by number.

        Each row has the document's state and its current revision (code, issue status, class and
        date). A listing has no revisions or links: use `get_document` for those.
        """
        with guarded(ctx, "list_documents", resource_name("documents", project)):
            return list_documents_impl(
                ctx,
                project=project,
                state=state,
                doc_type=doc_type,
                discipline=discipline,
                include_void=include_void,
            )

    @server.tool(annotations=READ_ONLY)
    def get_document(project: Project, number: Number) -> views.DocumentView:
        """Get one document: its revisions with their renditions, and the links to it.

        A link has a `pin` (a revision code, or none when it floats) and a `pin_state`:
        `current`, `stale` (a later revision was issued), `floating`, `no_current` or `unknown`.
        """
        with guarded(ctx, "get_document", resource_name("document", project, number)):
            return get_document_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def get_document_diff(
        project: Project,
        number: Number,
        from_code: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The earlier revision.")
        ],
        to_code: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The later revision.")
        ],
    ) -> views.RevisionDiffView:
        """Say what changed between two issued revisions of a document.

        `summary` is the heading and then the facts: the status change, each revision issued in
        between and each rendition that was added, removed or replaced. Use it before proposing
        that a stale link be re-pinned.
        """
        with guarded(
            ctx, "get_document_diff", resource_name("document", project, number, from_code, to_code)
        ):
            return get_document_diff_impl(
                ctx, project=project, number=number, from_code=from_code, to_code=to_code
            )

    @server.tool(annotations=READ_ONLY)
    def list_stale_links(project: Project) -> list[reports.StalePinLine]:
        """List links to documents that are stale (brief 7.3).

        A link is stale when a revision was issued after the one it is pinned to, or its document
        was voided or superseded. Each row names the document, the pinned revision, the current
        one, the revisions in between and the record that links.
        """
        with guarded(ctx, "list_stale_links", resource_name("stale_links", project)):
            return list_stale_links_impl(ctx, project=project)

    @server.tool(annotations=READ_ONLY)
    def list_overdue_reviews(
        project: Project,
        on: Annotated[
            str | None,
            Field(max_length=10, description="Judge on this day (YYYY-MM-DD). Default today."),
        ] = None,
    ) -> list[reports.OverdueLine]:
        """List overdue review answers: the cycle is open and the reviewer has not replied."""
        with guarded(ctx, "list_overdue_reviews", resource_name("overdue_reviews", project)):
            return list_overdue_reviews_impl(ctx, project=project, on=on)

    @server.tool(annotations=READ_ONLY)
    def list_transmittals(
        project: Project,
        state: Annotated[
            str | None, Field(max_length=MAX_PART, description="A state, e.g. `Issued`.")
        ] = None,
        direction: Annotated[
            str | None, Field(max_length=MAX_PART, description="`outgoing` or `incoming`.")
        ] = None,
    ) -> list[views.TransmittalView]:
        """List a project's transmittals by number (void ones only with `state=Void`).

        A listing has no items: use `get_transmittal` for the revisions a transmittal carries.
        """
        with guarded(ctx, "list_transmittals", resource_name("transmittals", project)):
            return list_transmittals_impl(ctx, project=project, state=state, direction=direction)

    @server.tool(annotations=READ_ONLY)
    def get_transmittal(project: Project, number: Number) -> views.TransmittalView:
        """Get one transmittal by number: recipients, dates, the answer and its revisions."""
        with guarded(ctx, "get_transmittal", resource_name("transmittal", project, number)):
            return get_transmittal_impl(ctx, project=project, number=number)
