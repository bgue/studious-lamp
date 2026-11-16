"""The scaffold read routes (P2-I4B-T09b1): the list, one scaffold, the due list and the export.

Thin: one call into ``tl_mod_scaffold.views`` per route, through the viewer's class filter (the
request's viewer, which the API middleware sets). Every route first checks the module word
``scaffold.view`` for the caller on the project, through ``guard`` (authentication and the agent
rules) and then ``require_word``, before any lookup. The reads take the request's viewer
(``current_viewer()``), not the views' LOWEST default. A hidden scaffold answers the same 404 as a
key that does not exist; no total counts it. No route writes. The export is a simple report: the
visible rows as CSV or JSON lines, with no ``id`` column.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold import MODULE
from tl_mod_scaffold import views as scaffold_views

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["scaffold"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
VIEW_WORD = "scaffold.view"
#: One text for a missing and a hidden scaffold: the key is not echoed.
MSG_NOT_FOUND = "no scaffold"
SCAFFOLD_LIMIT = scaffold_views.MAX_LIMIT
#: The export's media type and file extension, by ``format``.
EXPORT_TYPES = {"csv": ("text/csv", "csv"), "jsonl": ("application/x-ndjson", "jsonl")}


def _view_reader(
    project: str,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("document.read"))],
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    """Authentication and the agent rules (``guard``), then the module word ``scaffold.view`` the
    caller holds on the project, before any read. A refusal is the API's 403 ``forbidden``."""
    with ctx.backend(False) as uow:
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
Limit = Annotated[int, Query(ge=1, le=SCAFFOLD_LIMIT, description="At most this many rows.")]
StateQuery = Annotated[
    Literal[
        "Requested",
        "Designed",
        "Erecting",
        "Inspected",
        "In Use",
        "Modify",
        "Dismantle",
        "Removed",
    ]
    | None,
    Query(description="The workflow state."),
]
TagQuery = Annotated[Literal["green", "yellow", "red"] | None, Query(description="The tag colour.")]
OverdueQuery = Annotated[
    bool, Query(description="Only standing scaffolds past their next inspection day.")
]


@router.get("/projects/{project}/scaffolds", operation_id="list_scaffolds")
def list_scaffolds(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: StateQuery = None,
    tag: TagQuery = None,
    overdue: OverdueQuery = False,
    limit: Limit = 200,
) -> scaffold_views.ScaffoldPage:
    """A project's scaffolds by key, filtered by state, tag and overdue. ``total`` counts the
    visible matches. Hidden scaffolds are left out."""
    with ctx.backend(True) as uow:
        return scaffold_views.scaffold_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            tag=tag,
            overdue=overdue,
            today=date.today().isoformat(),
            limit=limit,
            viewer=current_viewer(),
        )


@router.get("/projects/{project}/scaffolds/{key}", operation_id="get_scaffold")
def get_scaffold(ctx: Ctx, actor: Reader, project: str, key: str) -> scaffold_views.ScaffoldDetail:
    """One scaffold with its inspections. 404 `record_not_found` when it is missing or hidden
    (one answer for both)."""
    with ctx.backend(True) as uow:
        detail = scaffold_views.scaffold_detail(
            uow.conn(), f"project:{project}", key, viewer=current_viewer()
        )
        if detail is None:
            raise RecordNotFoundError(MSG_NOT_FOUND)
        return detail


@router.get("/projects/{project}/scaffold-due", operation_id="list_scaffolds_due")
def list_scaffolds_due(
    ctx: Ctx, actor: Reader, project: str, limit: Limit = 200
) -> list[scaffold_views.ScaffoldRow]:
    """Standing scaffolds (Inspected, In Use, Modify) whose next inspection is due today or
    earlier, soonest due first. Hidden scaffolds are left out."""
    with ctx.backend(True) as uow:
        return scaffold_views.due_list(
            uow.conn(),
            f"project:{project}",
            date.today().isoformat(),
            limit=limit,
            viewer=current_viewer(),
        )


@router.get(
    "/projects/{project}/scaffold-export",
    operation_id="export_scaffolds",
    responses={
        200: {"content": {"text/csv": {}, "application/x-ndjson": {}}},
    },
)
def export_scaffolds(
    ctx: Ctx,
    actor: Reader,
    project: str,
    format_: Annotated[
        Literal["csv", "jsonl"],
        Query(alias="format", description="The file format: csv (the default) or jsonl."),
    ] = "csv",
    state: StateQuery = None,
    tag: TagQuery = None,
    overdue: OverdueQuery = False,
) -> Response:
    """The visible scaffolds matching the filters, as an attachment: CSV with a header line, or
    one JSON object per line. Hidden scaffolds are left out; there is no ``id`` column."""
    media_type, extension = EXPORT_TYPES[format_]
    with ctx.backend(True) as uow:
        page = scaffold_views.scaffold_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            tag=tag,
            overdue=overdue,
            today=date.today().isoformat(),
            limit=SCAFFOLD_LIMIT,
            viewer=current_viewer(),
        )
    body = scaffold_views.export_rows(page.rows, format_)
    return Response(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=scaffolds-{project}.{extension}",
        },
    )
