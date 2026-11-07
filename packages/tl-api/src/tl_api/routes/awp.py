"""Reads of the awp module (P2-I1 T03a): the CWPs, the CWAs, the WBS, the path of construction and
the EWP/PWP packages, for the web, the TUI and the MCP clients.

Thin: one call into ``tl_mod_awp.views`` per route, through the viewer's class filter. Every route
needs the action ``document.read``. A missing, hidden or voided record answers one 404
``record_not_found`` with the same text. The detail of a CWP adds its link count, file count and
timeline (the ledger events of the CWP, oldest first).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core.files.queries import list_files
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.link_queries import links_of
from tl_core.services.queries import record_history
from tl_mod_awp import reports, views
from tl_mod_awp.reports import CostFigure
from tl_mod_cost.views import cost_codes

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["awp"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]

#: The timeline note is cut to this many characters.
NOTE_LIMIT = 200


class TimelineRow(BaseModel):
    """One ledger event of a CWP: its date, who did it, what it was and a short note."""

    date: str  # ``recorded_at`` as YYYY-MM-DD
    who: str  # the actor
    event: str  # the event type
    note: str  # the payload's reason or note, cut to 200 characters; "" when none


class CwpDetailView(views.CwpDetail):
    """A CWP detail with the number of links and files it has, and its timeline."""

    link_count: int
    file_count: int
    timeline: list[TimelineRow]


def _note(payload: dict) -> str:
    note = payload.get("reason") or payload.get("note")
    return note[:NOTE_LIMIT] if isinstance(note, str) else ""


@router.get("/projects/{project}/awp/cwps", operation_id="list_cwps")
def list_cwps(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(max_length=64, description="The CWP state.")] = None,
    discipline: Annotated[
        str | None, Query(max_length=64, description="The discipline code.")
    ] = None,
    cwa: Annotated[str | None, Query(max_length=64, description="The CWA code.")] = None,
) -> list[views.CwpRow]:
    """A project's CWPs by number, filtered by state, discipline and CWA."""
    with ctx.backend(True) as uow:
        return views.cwp_list(
            uow.conn(), f"project:{project}", state=state, discipline=discipline, cwa=cwa
        )


@router.get("/projects/{project}/awp/cwps/{number}", operation_id="get_cwp")
def get_cwp(ctx: Ctx, actor: Reader, project: str, number: str) -> CwpDetailView:
    """One CWP with its fields, allocation, packages, activities, link count, file count and
    timeline. 404 `record_not_found` when it is missing, hidden or voided."""
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        detail = views.cwp_detail(uow.conn(), scope, number)
        if detail is None:
            raise RecordNotFoundError(f"no CWP {number!r}")
        links = len(links_of(uow, detail.id))
        files = len(list_files(uow, scope, detail.id))
        timeline = [
            TimelineRow(
                date=event.recorded_at.date().isoformat(),
                who=event.actor,
                event=event.event_type,
                note=_note(event.payload),
            )
            for event in record_history(uow, detail.id)
        ]
        return CwpDetailView(
            **detail.model_dump(),
            link_count=links,
            file_count=files,
            timeline=timeline,
        )


@router.get("/projects/{project}/awp/cwas", operation_id="list_cwas")
def list_cwas(ctx: Ctx, actor: Reader, project: str) -> list[views.CwaRow]:
    """A project's construction work areas by code, retired ones included (flagged)."""
    with ctx.backend(True) as uow:
        return views.cwa_list(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/awp/wbs", operation_id="wbs_tree")
def wbs_tree(
    ctx: Ctx,
    actor: Reader,
    project: str,
    depth: Annotated[
        int | None, Query(ge=1, le=20, description="Keep the nodes above this depth.")
    ] = None,
) -> list[views.WbsRow]:
    """The WBS nodes of a project depth-first, each with its rollup."""
    with ctx.backend(True) as uow:
        return views.wbs_tree(uow.conn(), f"project:{project}", depth=depth)


@router.get("/projects/{project}/awp/wbs/{code:path}", operation_id="get_wbs_node")
def get_wbs_node(ctx: Ctx, actor: Reader, project: str, code: str) -> views.WbsRow:
    """One WBS node by its code, with its rollup. 404 `record_not_found` when missing or hidden."""
    with ctx.backend(True) as uow:
        node = views.wbs_detail(uow.conn(), f"project:{project}", code)
        if node is None:
            raise RecordNotFoundError(f"no WBS node {code!r}")
        return node


@router.get("/projects/{project}/awp/path", operation_id="get_path")
def get_path(
    ctx: Ctx,
    actor: Reader,
    project: str,
    version: Annotated[int | None, Query(ge=1, description="The path version.")] = None,
) -> views.PathView:
    """The path of construction of a project at a version (the current one by default).
    404 `record_not_found` when there is no such path or version."""
    with ctx.backend(True) as uow:
        found = views.path(uow.conn(), f"project:{project}", version=version)
        if found is None:
            raise RecordNotFoundError(f"no path {project!r} at version {version!r}")
        return found


@router.get("/projects/{project}/awp/path/versions", operation_id="list_path_versions")
def list_path_versions(ctx: Ctx, actor: Reader, project: str) -> list[views.PathVersion]:
    """The versions of a project's path, newest first."""
    with ctx.backend(True) as uow:
        return views.path_versions(uow.conn(), f"project:{project}")


@router.get("/projects/{project}/awp/packages", operation_id="list_packages")
def list_packages(
    ctx: Ctx,
    actor: Reader,
    project: str,
    kind: Annotated[Literal["EWP", "PWP"] | None, Query(description="EWP or PWP.")] = None,
) -> list[views.PackageRow]:
    """A project's EWP and PWP references by package number."""
    with ctx.backend(True) as uow:
        return views.package_list(uow.conn(), f"project:{project}", kind=kind)


#: The row model of each awp report: its field names are the report's columns.
REPORT_MODELS: dict[str, type[BaseModel]] = {
    "cwp_status": reports.StatusRow,
    "wbs_vs_cost_code": reports.CostRow,
    "cwa_sequence": reports.SequenceRow,
}


class ReportView(BaseModel):
    """An awp report as a table: its name, its column names and its cells as text."""

    name: str
    columns: list[str]
    rows: list[list[str]]  # each cell is ``reports.format_value`` of the field


def _cost_figures(conn: Connection, project: str) -> dict[str, CostFigure]:
    """The project's cost codes by code: the title and the stated ``hours_budget`` (or None)."""
    figures: dict[str, CostFigure] = {}
    for view in cost_codes(conn, f"project:{project}", limit=20000):
        hours = view.figures.get("hours_budget")
        figures[view.code] = CostFigure(
            title=view.title, hours_budget=None if hours is None else Decimal(str(hours))
        )
    return figures


@router.get(
    "/projects/{project}/awp/reports/{name}",
    operation_id="awp_report",
    response_model=None,
    responses={200: {"content": {"text/csv": {}, "application/json": {}}}},
)
def awp_report(
    ctx: Ctx,
    actor: Reader,
    project: str,
    name: str,
    format: Annotated[Literal["json", "csv"], Query()] = "json",
) -> ReportView | Response:
    """One awp report of a project: `cwp_status`, `wbs_vs_cost_code` or `cwa_sequence`, as a
    table in JSON, or as CSV with `format=csv`. 404 `record_not_found` for any other name."""
    if name not in REPORT_MODELS:
        raise RecordNotFoundError(f"no report {name!r}")
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        conn = uow.conn()
        if name == "cwp_status":
            rows: list[BaseModel] = list(reports.cwp_status(conn, scope))
        elif name == "wbs_vs_cost_code":
            rows = list(reports.wbs_vs_cost_code(conn, scope, _cost_figures(conn, project)))
        else:
            rows = list(reports.cwa_sequence(conn, scope))
    if format == "csv":
        return Response(reports.to_csv(rows), media_type="text/csv; charset=utf-8")
    columns = list(REPORT_MODELS[name].model_fields)
    cells = [[reports.format_value(getattr(row, column)) for column in columns] for row in rows]
    return ReportView(name=name, columns=columns, rows=cells)
