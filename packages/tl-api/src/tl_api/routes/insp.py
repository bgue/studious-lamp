"""Reads of the quality module's checklists and inspections (P2-INSP-T06): five GET routes.

Thin: one call into ``tl_mod_quality.insp_views`` per route, through the viewer's class filter
(``current_viewer()``, set by the API middleware). The module word ``quality.view`` on the project
is checked first, through the same ``Reader`` dependency the punch routes use (``guard`` and then
``require_word``), before any lookup. A hidden or unknown key answers the same 404 body. The
inspection export is declared before the ``{key}`` route so that ``export`` is not
read as a key.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality import insp_views as views

from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError
from tl_api.routes.punch import Reader

router = APIRouter(tags=["quality"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Limit = Annotated[int, Query(ge=1, le=views.MAX_LIMIT, description="At most this many rows.")]
MSG_INSPECTION_NOT_FOUND = "no inspection"
MSG_CHECKLIST_NOT_FOUND = "no checklist"
EXPORT_MEDIA: dict[str, str] = {"csv": "text/csv", "jsonl": "application/x-ndjson"}


def _bad_argument(exc: ValueError) -> ApiError:
    """A bad state, point or format is a 422 (the view's own text)."""
    return ApiError(422, "invalid_argument", str(exc))


@router.get("/quality/inspections", operation_id="list_inspections")
def list_inspections(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(max_length=32, description="The inspection state.")] = None,
    point: Annotated[str | None, Query(max_length=64, description="The inspection point.")] = None,
    area: Annotated[str | None, Query(max_length=64, description="The area.")] = None,
    inspector: Annotated[str | None, Query(max_length=120, description="The inspector.")] = None,
    subject: Annotated[str | None, Query(max_length=200, description="The subject key.")] = None,
    for_: Annotated[
        str | None,
        Query(alias="for", max_length=200, description="The work package key."),
    ] = None,
    limit: Limit = 200,
) -> views.InspectionPage:
    """A project's inspections by key, filtered by state, point, area, inspector, subject and the
    work package. ``total`` counts the visible matches. Hidden inspections are left out."""
    with ctx.backend(True) as uow:
        try:
            return views.inspection_list(
                uow.conn(),
                f"project:{project}",
                state=state,
                point=point,
                area=area,
                inspector=inspector,
                subject_key=subject,
                for_key=for_,
                limit=limit,
                viewer=current_viewer(),
            )
        except ValueError as exc:
            raise _bad_argument(exc) from exc


@router.get("/quality/inspections/export", operation_id="export_inspections")
def export_inspections(
    ctx: Ctx,
    actor: Reader,
    project: str,
    format: Annotated[str, Query(description="csv or jsonl.")] = "csv",
    state: Annotated[str | None, Query(max_length=32, description="The inspection state.")] = None,
    point: Annotated[str | None, Query(max_length=64, description="The inspection point.")] = None,
    area: Annotated[str | None, Query(max_length=64, description="The area.")] = None,
    inspector: Annotated[str | None, Query(max_length=120, description="The inspector.")] = None,
    subject: Annotated[str | None, Query(max_length=200, description="The subject key.")] = None,
    for_: Annotated[
        str | None,
        Query(alias="for", max_length=200, description="The work package key."),
    ] = None,
    limit: Limit = 200,
) -> Response:
    """The rows of the inspection list, with the same filters, as csv or jsonl (a line per row)."""
    with ctx.backend(True) as uow:
        try:
            page = views.inspection_list(
                uow.conn(),
                f"project:{project}",
                state=state,
                point=point,
                area=area,
                inspector=inspector,
                subject_key=subject,
                for_key=for_,
                limit=limit,
                viewer=current_viewer(),
            )
            body = views.export_rows(page.rows, format)
        except ValueError as exc:
            raise _bad_argument(exc) from exc
    return Response(content=body, media_type=EXPORT_MEDIA[format])


@router.get("/quality/inspections/{key}", operation_id="get_inspection")
def get_inspection(ctx: Ctx, actor: Reader, project: str, key: str) -> views.InspectionDetail:
    """One inspection with its answers, its signatures and the punch items it raised. 404
    `record_not_found` when it is missing, in another project or hidden (one answer for all)."""
    with ctx.backend(True) as uow:
        detail = views.inspection_detail(
            uow.conn(), f"project:{project}", key, viewer=current_viewer()
        )
        if detail is None:
            raise RecordNotFoundError(MSG_INSPECTION_NOT_FOUND)
        return detail


@router.get("/quality/checklists", operation_id="list_checklists")
def list_checklists(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(max_length=32, description="The checklist state.")] = None,
    discipline: Annotated[str | None, Query(max_length=64, description="The discipline.")] = None,
    limit: Limit = 200,
) -> views.ChecklistPage:
    """A project's checklists by key, filtered by state and discipline. ``total`` counts them."""
    with ctx.backend(True) as uow:
        try:
            return views.checklist_list(
                uow.conn(),
                f"project:{project}",
                state=state,
                discipline=discipline,
                limit=limit,
                viewer=current_viewer(),
            )
        except ValueError as exc:
            raise _bad_argument(exc) from exc


@router.get("/quality/checklists/{key}", operation_id="get_checklist")
def get_checklist(ctx: Ctx, actor: Reader, project: str, key: str) -> views.ChecklistDetail:
    """One checklist with its questions. 404 `record_not_found` when it is missing or hidden."""
    with ctx.backend(True) as uow:
        detail = views.checklist_detail(
            uow.conn(), f"project:{project}", key, viewer=current_viewer()
        )
        if detail is None:
            raise RecordNotFoundError(MSG_CHECKLIST_NOT_FOUND)
        return detail
