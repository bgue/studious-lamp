"""Reads of the documents module: documents, revisions, links, transmittals, reports (P1-I2).

Thin, like the other read routes: one call into ``tl_mod_documents.views`` per route. Writes are
the module's commands (``POST /commands/RegisterDocument``, ``IssueRevision`` and the rest;
``tl_mod_documents.commands``, with their access levels). Every read needs the action
``document.read``, which is open to agents because they only read. Phase 1 has no per-record
access lists, so a person who can read one document of a project can read them all.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from tl_mod_documents import reports, views

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["documents"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]
Direction = Literal["outgoing", "incoming"]


@router.get("/projects/{project}/documents", operation_id="list_documents")
def list_documents(
    ctx: Ctx,
    actor: Reader,
    project: str,
    doc_type: Annotated[str | None, Query(alias="type")] = None,
    discipline: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query(description="For example Issued.")] = None,
    include_void: Annotated[bool, Query(description="Include void documents.")] = False,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[views.DocumentView]:
    """A project's documents by number, without revisions or links."""
    with ctx.backend(True) as uow:
        return views.document_views(
            uow.conn(),
            f"project:{project}",
            doc_type=doc_type,
            discipline=discipline,
            state=state,
            include_void=include_void,
            limit=limit,
        )


@router.get("/projects/{project}/document-diffs/{number:path}", operation_id="get_document_diff")
def get_document_diff(
    ctx: Ctx,
    actor: Reader,
    project: str,
    number: str,
    from_code: Annotated[str, Query(alias="from", min_length=1, max_length=128)],
    to_code: Annotated[str, Query(alias="to", min_length=1, max_length=128)],
) -> views.RevisionDiffView:
    """What changed between two issued revisions. 422 `invalid_pin` for a code that is not one.

    A separate prefix, not `.../documents/{number}/diff`: a number may hold `/`, so a document
    numbered `X/diff` must stay reachable at `.../documents/X/diff`.
    """
    with ctx.backend(True) as uow:
        return views.revision_diff_view(
            uow.conn(), f"project:{project}", number, from_code, to_code
        )


@router.get("/projects/{project}/documents/{number:path}", operation_id="get_document")
def get_document(ctx: Ctx, actor: Reader, project: str, number: str) -> views.DocumentView:
    """One document with its revisions, renditions and links. 404 `document_not_found`.

    The number may hold `/`.
    """
    with ctx.backend(True) as uow:
        return views.document_view(uow.conn(), f"project:{project}", number)


@router.get("/projects/{project}/stale-links", operation_id="list_stale_links")
def list_stale_links(ctx: Ctx, actor: Reader, project: str) -> list[reports.StalePinLine]:
    """Links to documents that are stale: the pin is behind, or the document was voided."""
    with ctx.backend(True) as uow:
        return views.stale_links(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/overdue-reviews", operation_id="list_overdue_reviews")
def list_overdue_reviews(
    ctx: Ctx,
    actor: Reader,
    project: str,
    on: Annotated[date | None, Query(description="Judge on this day. Default today.")] = None,
) -> list[reports.OverdueLine]:
    """Open reviews with a reviewer who has not answered by their date."""
    with ctx.backend(True) as uow:
        return views.overdue_reviews(uow.conn(), f"project:{project}", on=on)


@router.get("/projects/{project}/transmittals", operation_id="list_transmittals")
def list_transmittals(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(description="For example Issued.")] = None,
    direction: Annotated[Direction | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[views.TransmittalView]:
    """A project's transmittals by number, without items. Void ones only with `state=Void`."""
    with ctx.backend(True) as uow:
        return views.transmittal_views(
            uow.conn(), f"project:{project}", state=state, direction=direction, limit=limit
        )


@router.get("/projects/{project}/transmittals/{number:path}", operation_id="get_transmittal")
def get_transmittal(ctx: Ctx, actor: Reader, project: str, number: str) -> views.TransmittalView:
    """One transmittal with its items. 404 `transmittal_not_found`."""
    with ctx.backend(True) as uow:
        return views.transmittal_view(uow.conn(), f"project:{project}", number)
