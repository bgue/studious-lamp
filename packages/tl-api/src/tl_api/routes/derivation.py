"""Reads of the derivation pipeline: schemas, derived documents, jobs, rows, reports (P1-I3).

Thin, like the document reads: one call into ``tl_mod_documents.derivation.views`` per route.
Writes are the module's commands (``POST /commands/StartExtraction``, ``ValidateDerived``,
``PublishDerivedTags`` and the rest; ``tl_mod_documents.commands`` has their access levels). Every
read needs the action ``document.read``, which agents hold because they only read. No route runs
a JSON Schema on a request (FANOUT D10): a report is the one a job stored. A derived
document's key holds ``/`` (``ISD-001@A/instrument-index``), so the routes that take one use a
path parameter and a distinct prefix, as ``document-diffs`` does.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.diff import DerivedDiff
from tl_mod_documents.derivation.publish import CompensationPlan, PublishPlan
from tl_mod_documents.derivation.validation import ValidationReport

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["derivation"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]
Rev = Annotated[int | None, Query(ge=1, description="A content revision; the latest if omitted.")]


@router.get("/projects/{project}/document-schemas", operation_id="list_document_schemas")
def list_document_schemas(
    ctx: Ctx,
    actor: Reader,
    project: str,
    code: Annotated[str | None, Query(max_length=128)] = None,
    include_retired: Annotated[bool, Query()] = False,
) -> list[views.SchemaSummary]:
    """The schemas a project sees (its own and the company's) by code and version."""
    with ctx.backend(True) as uow:
        return views.schema_summaries(
            uow.conn(), f"project:{project}", code=code, active_only=not include_retired
        )


@router.get("/projects/{project}/document-schemas/{ref:path}", operation_id="get_document_schema")
def get_document_schema(ctx: Ctx, actor: Reader, project: str, ref: str) -> views.SchemaView:
    """One schema by `code` (newest active) or `code@semver`. 404 `schema_not_found`."""
    with ctx.backend(True) as uow:
        return views.schema_view(uow.conn(), f"project:{project}", ref)


@router.get("/projects/{project}/processing-jobs", operation_id="list_processing_jobs")
def list_processing_jobs(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(description="queued, running, succeeded, ...")] = None,
    derived: Annotated[str | None, Query(max_length=300, description="Id or key.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[views.JobView]:
    """A project's processing jobs, newest first."""
    with ctx.backend(True) as uow:
        return views.job_views(
            uow.conn(), f"project:{project}", state=state, derived=derived, limit=limit
        )


@router.get("/projects/{project}/processing-jobs/{job_id}", operation_id="get_processing_job")
def get_processing_job(ctx: Ctx, actor: Reader, project: str, job_id: str) -> views.JobView:
    """One job. 404 `job_not_found`."""
    with ctx.backend(True) as uow:
        return views.job_view(uow.conn(), f"project:{project}", job_id)


@router.get("/projects/{project}/derived-documents", operation_id="list_derived_documents")
def list_derived_documents(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(description="For example Valid.")] = None,
    document: Annotated[str | None, Query(max_length=300, description="Source number.")] = None,
    schema: Annotated[str | None, Query(max_length=128, description="Schema code.")] = None,
    include_void: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[views.DerivedSummary]:
    """A project's derived documents, newest first, without content revisions."""
    with ctx.backend(True) as uow:
        return views.derived_summaries(
            uow.conn(),
            f"project:{project}",
            state=state,
            document=document,
            schema_code=schema,
            include_void=include_void,
            limit=limit,
        )


@router.get("/projects/{project}/derived-rows/{ref:path}", operation_id="get_derived_rows")
def get_derived_rows(
    ctx: Ctx,
    actor: Reader,
    project: str,
    ref: str,
    content_rev: Rev = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=views.MAX_PAGE)] = 100,
) -> views.RowsPage:
    """A page of the extracted rows of a content revision, as read (all text)."""
    with ctx.backend(True) as uow:
        return views.derived_rows(
            uow, f"project:{project}", ref, content_rev=content_rev, offset=offset, limit=limit
        )


@router.get("/projects/{project}/derived-reports/{ref:path}", operation_id="get_derived_report")
def get_derived_report(
    ctx: Ctx, actor: Reader, project: str, ref: str, content_rev: Rev = None
) -> ValidationReport:
    """The stored validation report of a content revision. 409 `derived_state` before one."""
    with ctx.backend(True) as uow:
        return views.derived_report(uow, f"project:{project}", ref, content_rev=content_rev)


@router.get("/projects/{project}/derived-diffs/{ref:path}", operation_id="get_derived_diff")
def get_derived_diff(
    ctx: Ctx,
    actor: Reader,
    project: str,
    ref: str,
    against: Annotated[
        str, Query(pattern="^(previous_pass|previous_revision)$", description="What to compare.")
    ] = "previous_pass",
    content_rev: Rev = None,
) -> DerivedDiff:
    """What changed against the previous pass, or the previous revision of the document."""
    with ctx.backend(True) as uow:
        return views.derived_diff(
            uow, f"project:{project}", ref, against=against, content_rev=content_rev
        )


@router.get(
    "/projects/{project}/derived-publish-previews/{ref:path}",
    operation_id="get_derived_publish_preview",
)
def get_derived_publish_preview(
    ctx: Ctx,
    actor: Reader,
    project: str,
    ref: str,
    target: Annotated[str | None, Query(pattern="^(tags|documents)$")] = None,
) -> PublishPlan:
    """What publishing would do with each row now. Writes nothing."""
    with ctx.backend(True) as uow:
        return views.publish_preview(uow, f"project:{project}", ref, target=target)


@router.get(
    "/projects/{project}/derived-compensation-previews/{ref:path}",
    operation_id="get_derived_compensation_preview",
)
def get_derived_compensation_preview(
    ctx: Ctx, actor: Reader, project: str, ref: str
) -> CompensationPlan:
    """What compensating the publication in force would reverse. Writes nothing."""
    with ctx.backend(True) as uow:
        return views.compensation_preview(uow, f"project:{project}", ref)


@router.get("/projects/{project}/derived-documents/{ref:path}", operation_id="get_derived_document")
def get_derived_document(ctx: Ctx, actor: Reader, project: str, ref: str) -> views.DerivedView:
    """One derived document by id or key, with its content revisions and running job."""
    with ctx.backend(True) as uow:
        return views.derived_view(uow.conn(), f"project:{project}", ref)
