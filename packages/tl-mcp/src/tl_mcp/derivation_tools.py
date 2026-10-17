"""Derivation tools: find and check derived documents, propose to extract and to import.

``list_derived_documents``, ``get_derived_document`` and ``validate_against_schema`` only read:
the last computes a report from stored rows and stores nothing. ``start_extraction`` and
``propose_import`` never change anything: each builds the command the API would run, has it
checked by the handler's own rules and files a pending proposal. A person accepts it in the review
queue, and accepting runs the command as that person, so it needs the access the command needs
(ADR-0014 section 8): publishing into tags the admin role, into documents the document controller
or admin role. An agent never starts a job or writes a record itself.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_core.services import proposals
from tl_mod_documents.derivation import rows, views
from tl_mod_documents.derivation.derived import StartExtraction
from tl_mod_documents.derivation.publish import PublishDerivedDocuments, PublishDerivedTags
from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.errors import DerivedStateError
from tl_mod_documents.names import TARGET_DOCUMENTS, TARGET_TAGS

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
Derived = Annotated[
    str,
    Field(
        min_length=1,
        max_length=300,
        description="A derived document's id or key, `ISD-001@A/instrument-index`.",
    ),
]


def list_derived_documents_impl(
    ctx: McpContext, *, project: str, state: str | None, document: str | None
) -> list[views.DerivedSummary]:
    with ctx.factory(True) as uow:
        return views.derived_summaries(
            uow.conn(), f"project:{project}", state=state, document=document, limit=200
        )


def get_derived_document_impl(ctx: McpContext, *, project: str, derived: str) -> views.DerivedView:
    with ctx.factory(True) as uow:
        return views.derived_view(uow.conn(), f"project:{project}", derived)


def validate_against_schema_impl(
    ctx: McpContext, *, project: str, derived: str, schema: str | None, content_rev: int | None
) -> ValidationReport:
    with ctx.factory(True) as uow:
        return views.validate_stored(
            uow, f"project:{project}", derived, schema_ref=schema, content_rev=content_rev
        )


def start_extraction_impl(
    ctx: McpContext,
    *,
    project: str,
    derived: str | None,
    revision_id: str | None,
    schema_code: str | None,
    extractor: str | None,
    summary: str | None,
) -> ProposalResult:
    scope = f"project:{project}"
    derived_id: str | None = None
    if derived is not None:
        with ctx.factory(True) as uow:
            derived_id = views.find_derived(uow.conn(), scope, derived).id
    command = StartExtraction(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        derived_id=derived_id,
        revision_id=None if derived is not None else revision_id,
        schema_code=None if derived is not None else schema_code,
        extractor=extractor,
    )
    target = derived or f"{revision_id} / {schema_code}"
    view = proposals.submit(
        ctx.factory,
        tool="start_extraction",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Extract and validate {target} in {scope}",
    )
    return _result(view)


def propose_import_impl(
    ctx: McpContext,
    *,
    project: str,
    derived: str,
    expected_content_rev: int | None,
    skip_existing: bool,
    summary: str | None,
) -> ProposalResult:
    scope = f"project:{project}"
    with ctx.factory(True) as uow:
        found = views.find_derived(uow.conn(), scope, derived)
        schema = rows.get_schema(uow.conn(), found.schema_id)
    if schema is None or schema.target_kind not in (TARGET_TAGS, TARGET_DOCUMENTS):
        raise DerivedStateError(f"{found.key}: its schema has no publish mapping to import with")
    fields = {
        "actor": ctx.actor,
        "source": proposals.source_for(ctx.actor),
        "scope": scope,
        "derived_id": found.id,
        "expected_content_rev": expected_content_rev or max(found.content_rev, 1),
        "skip_existing": skip_existing,
    }
    tags = schema.target_kind == TARGET_TAGS
    view = proposals.submit(
        ctx.factory,
        tool="propose_import_tags" if tags else "propose_import_documents",
        agent=ctx.actor,
        command=PublishDerivedTags(**fields) if tags else PublishDerivedDocuments(**fields),
        summary=summary
        or f"Create the {schema.target_kind} of {found.key} ({found.row_count or 0} rows)",
    )
    return _result(view)


def register_derivation_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the five derivation tools to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_derived_documents(
        project: Project,
        state: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Pending, Processing, Invalid, Valid, ..."),
        ] = None,
        document: Annotated[
            str | None, Field(max_length=MAX_PART, description="The source document number.")
        ] = None,
    ) -> list[views.DerivedSummary]:
        """List a project's derived documents: data read from a document and checked by a schema.

        Each has a state (`Valid` can be imported), the row and error counts of its latest pass
        and its key. Use `get_derived_document` for its passes and running job.
        """
        with guarded(ctx, "list_derived_documents", resource_name("derived", project)):
            return list_derived_documents_impl(ctx, project=project, state=state, document=document)

    @server.tool(annotations=READ_ONLY)
    def get_derived_document(project: Project, derived: Derived) -> views.DerivedView:
        """Get one derived document with its content revisions and its queued or running job."""
        with guarded(ctx, "get_derived_document", resource_name("derived", project, derived)):
            return get_derived_document_impl(ctx, project=project, derived=derived)

    @server.tool(annotations=READ_ONLY)
    def validate_against_schema(
        project: Project,
        derived: Derived,
        schema: Annotated[
            str | None,
            Field(
                max_length=MAX_PART,
                description="A schema `code` or `code@semver`; default: the document's own.",
            ),
        ] = None,
        content_rev: Annotated[
            int | None, Field(ge=1, description="The pass to check; default: the latest.")
        ] = None,
    ) -> ValidationReport:
        """Check the stored rows of a derived document against a schema and return the report.

        Nothing is stored and no job runs: use it to see whether rows would pass, or which issues
        another schema version would raise, before you propose anything.
        """
        with guarded(ctx, "validate_against_schema", resource_name("derived", project, derived)):
            return validate_against_schema_impl(
                ctx, project=project, derived=derived, schema=schema, content_rev=content_rev
            )

    @server.tool(annotations=PROPOSES)
    def start_extraction(
        project: Project,
        derived: Annotated[
            str | None,
            Field(max_length=300, description="The derived document's id or key, if it exists."),
        ] = None,
        revision_id: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="With `schema_code`: open it from a revision."),
        ] = None,
        schema_code: Annotated[str | None, Field(max_length=MAX_PART)] = None,
        extractor: Annotated[
            str | None, Field(max_length=MAX_PART, description="An extractor name; default: auto.")
        ] = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose reading a document's file and checking the rows against its schema.

        Name the derived document, or a revision with a schema code. A person must accept the
        proposal before any job is queued; then a worker reads the file and validates the rows.
        """
        with guarded(
            ctx,
            "start_extraction",
            resource_name("derived", project, derived or revision_id or ""),
        ):
            return start_extraction_impl(
                ctx,
                project=project,
                derived=derived,
                revision_id=revision_id,
                schema_code=schema_code,
                extractor=extractor,
                summary=summary,
            )

    @server.tool(annotations=PROPOSES)
    def propose_import(
        project: Project,
        derived: Derived,
        expected_content_rev: Annotated[
            int | None,
            Field(
                ge=1,
                description="The pass you looked at; default: the latest. A newer pass fails it.",
            ),
        ] = None,
        skip_existing: Annotated[
            bool, Field(description="Leave rows whose key exists alone instead of stopping.")
        ] = False,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose creating the tags or documents of a valid derived document.

        Which one follows the schema's target. It creates records and never changes existing ones.
        Accepting needs the admin role (tags) or the document controller role (documents). The
        proposal is checked now, so an error means it could not be applied (not `Valid`, a newer
        pass, rows that exist).
        """
        with guarded(ctx, "propose_import", resource_name("derived", project, derived)):
            return propose_import_impl(
                ctx,
                project=project,
                derived=derived,
                expected_content_rev=expected_content_rev,
                skip_existing=skip_existing,
                summary=summary,
            )
