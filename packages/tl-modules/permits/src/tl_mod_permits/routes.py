"""The read routes of the permits module (P2-PTW-T07): the register, the board, the export and one
permit.

Thin: one call into ``tl_mod_permits.views`` per route, through the viewer's class filter (the
request's viewer, which the API middleware sets, not the views' LOWEST default). ``now`` is read
once per request and passed to the view. Every route first passes ``guard("document.read")``
(authentication and the agent rules), then the module word ``permits.view`` the caller holds on the
project, before any read. A hidden, missing or other-project key answers the one 404 text; the key
is not echoed. The fixed paths ``/permits/board`` and ``/permits/export`` are declared before
``/permits/{key}`` so they are not taken for keys. Nothing here writes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import utcnow

from tl_mod_permits import MODULE, iso_views
from tl_mod_permits import views as permit_views

router = APIRouter(tags=["permits"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
VIEW_WORD = "permits.view"
#: One text for a missing, hidden and other-project permit: the key is not echoed.
MSG_NOT_FOUND = "no permit"
#: One text for a missing, hidden and other-scope isolation (P2-PTW-T07b): the key is not echoed.
MSG_NO_ISOLATION = "no isolation"
PERMIT_LIMIT = permit_views.MAX_LIMIT

State = Literal[
    "Requested",
    "Approved",
    "Active",
    "Lapsed",
    "Suspended",
    "Handed back",
    "Closed",
    "Rejected",
    "Cancelled",
]
Project = Annotated[str, Query(max_length=120, description="The project.")]
Area = Annotated[str | None, Query(max_length=64, description="The area.")]
Holder = Annotated[str | None, Query(max_length=120, description="The holder.")]
IsolationState = Literal["Applied", "Verified", "Removed"]
Energy = Literal["electrical", "mechanical", "process", "other"]
PermitType = Annotated[
    str | None, Query(alias="type", max_length=64, description="The permit type.")
]


def _view_reader(
    project: Project,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("document.read"))],
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    """Authentication and the agent rules (``guard``), then the module word ``permits.view`` the
    caller holds on the project, before any read. A refusal is the API's 403 ``forbidden``."""
    with ctx.backend(True) as uow:
        require_word(
            uow.conn(),
            holder_for_principal(principal),
            scope=f"project:{project}",
            module=MODULE,
            word=normalise_word(VIEW_WORD),
            what=VIEW_WORD,
        )
    return actor


Reader = Annotated[str, Depends(_view_reader)]


@router.get("/permits/board", operation_id="get_permit_board")
def get_permit_board(
    ctx: Ctx,
    actor: Reader,
    project: Project,
    area: Area = None,
) -> permit_views.PermitBoard:
    """The live permits of a project (Lapsed, Suspended, Active) by area, Lapsed first, with the
    counts by shown state. Hidden permits are left out of the rows and the counts."""
    with ctx.backend(True) as uow:
        return permit_views.permit_board(
            uow.conn(), f"project:{project}", area, now=utcnow(), viewer=current_viewer()
        )


@router.get("/permits/export", operation_id="export_permits")
def export_permits(
    ctx: Ctx,
    actor: Reader,
    project: Project,
    fmt: Annotated[Literal["csv", "jsonl"], Query(alias="format", description="csv or jsonl.")],
    state: Annotated[State | None, Query(description="The shown state.")] = None,
    permit_type: PermitType = None,
    area: Area = None,
    holder: Holder = None,
) -> Response:
    """The rows of the list route as CSV (``text/csv``) or JSON lines (``application/x-ndjson``)."""
    with ctx.backend(True) as uow:
        page = permit_views.permit_list(
            uow.conn(),
            f"project:{project}",
            now=utcnow(),
            state=state,
            permit_type=permit_type,
            area=area,
            holder=holder,
            viewer=current_viewer(),
        )
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    return Response(content=permit_views.export_rows(page.rows, fmt), media_type=media)


@router.get("/permits", operation_id="list_permits")
def list_permits(
    ctx: Ctx,
    actor: Reader,
    project: Project,
    state: Annotated[State | None, Query(description="The shown state.")] = None,
    permit_type: PermitType = None,
    area: Area = None,
    holder: Holder = None,
    limit: Annotated[
        int, Query(ge=1, le=PERMIT_LIMIT, description="At most this many rows.")
    ] = 100,
    offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
) -> permit_views.PermitPage:
    """A project's permits by key, filtered by shown state, type, area and holder. ``total``
    counts the visible matches. Hidden permits are left out."""
    with ctx.backend(True) as uow:
        return permit_views.permit_list(
            uow.conn(),
            f"project:{project}",
            now=utcnow(),
            state=state,
            permit_type=permit_type,
            area=area,
            holder=holder,
            limit=limit,
            offset=offset,
            viewer=current_viewer(),
        )


@router.get("/permits/isolations", operation_id="list_isolations")
def list_isolations(
    ctx: Ctx,
    actor: Reader,
    project: Project,
    state: Annotated[IsolationState | None, Query(description="The isolation state.")] = None,
    energy: Annotated[Energy | None, Query(description="The energy kind.")] = None,
    limit: Annotated[
        int, Query(ge=1, le=iso_views.MAX_LIMIT, description="At most this many rows.")
    ] = 100,
) -> iso_views.IsolationPage:
    """The isolations of a project by key, filtered by state and energy. ``total`` counts the
    visible matches. Hidden isolations (and those on a hidden point) are left out."""
    with ctx.backend(True) as uow:
        return iso_views.isolation_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            energy=energy,
            limit=limit,
            viewer=current_viewer(),
        )


@router.get("/permits/isolations/export", operation_id="export_isolations")
def export_isolations(
    ctx: Ctx,
    actor: Reader,
    project: Project,
    fmt: Annotated[Literal["csv", "jsonl"], Query(alias="format", description="csv or jsonl.")],
    state: Annotated[IsolationState | None, Query(description="The isolation state.")] = None,
    energy: Annotated[Energy | None, Query(description="The energy kind.")] = None,
) -> Response:
    """The rows of the isolation list as CSV (``text/csv``) or JSON lines
    (``application/x-ndjson``)."""
    with ctx.backend(True) as uow:
        page = iso_views.isolation_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            energy=energy,
            limit=iso_views.MAX_LIMIT,
            viewer=current_viewer(),
        )
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    return Response(content=iso_views.isolation_export_rows(page.rows, fmt), media_type=media)


@router.get("/permits/isolations/{key}", operation_id="get_isolation")
def get_isolation(ctx: Ctx, actor: Reader, project: Project, key: str) -> iso_views.IsolationDetail:
    """One isolation with its trail and the keys of the permits it is read for. 404
    `record_not_found` when it is missing or hidden (one answer for both)."""
    with ctx.backend(True) as uow:
        detail = iso_views.isolation_detail(
            uow.conn(), f"project:{project}", key, viewer=current_viewer()
        )
        if detail is None:
            raise RecordNotFoundError(MSG_NO_ISOLATION)
        return detail


@router.get("/permits/{key}", operation_id="get_permit")
def get_permit(ctx: Ctx, actor: Reader, project: Project, key: str) -> permit_views.PermitDetail:
    """One permit with its fields. 404 `record_not_found` when it is missing or hidden (one answer
    for both)."""
    with ctx.backend(True) as uow:
        detail = permit_views.permit_detail(
            uow.conn(), f"project:{project}", key, now=utcnow(), viewer=current_viewer()
        )
        if detail is None:
            raise RecordNotFoundError(MSG_NOT_FOUND)
        return detail


@router.get("/permits/{key}/gas-tests", operation_id="list_gas_tests", response_model=None)
def list_gas_tests(
    ctx: Ctx,
    actor: Reader,
    project: Project,
    key: str,
    fmt: Annotated[
        Literal["csv", "jsonl"] | None, Query(alias="format", description="csv or jsonl.")
    ] = None,
) -> Response | list[iso_views.GasRow]:
    """The gas tests of one permit, newest first: a JSON list, or the export text with
    ``format``. The permit is read as ``get_permit`` reads it, so a hidden, unknown or other-project
    permit is the one 404 `no permit`; a visible permit with no tests is ``[]``."""
    with ctx.backend(True) as uow:
        viewer = current_viewer()
        permit = permit_views.permit_detail(
            uow.conn(), f"project:{project}", key, now=utcnow(), viewer=viewer
        )
        if permit is None:
            raise RecordNotFoundError(MSG_NOT_FOUND)
        rows = iso_views.gas_tests_for(uow.conn(), permit.row.id, viewer=viewer)
    if fmt is None:
        return rows
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    return Response(content=iso_views.gas_export_rows(rows, fmt), media_type=media)
