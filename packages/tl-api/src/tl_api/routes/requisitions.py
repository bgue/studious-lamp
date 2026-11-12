"""Reads of the requisitions module (P2-I4A-T04c1): the requisition list and detail, and the work
order list and detail.

Thin: one call into ``tl_mod_requisitions.views`` per route, through the request's viewer (the
API sets it from the principal; the views default to the lowest clearance, so a route passes it
explicitly). Every route first checks the access word ``requisitions.view`` (table word ``read``)
through ``guard`` and ``require_word``, before any lookup. A hidden requisition or work order
answers the same 404 as a missing one, and no list total counts a hidden row.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Connection, bindparam, text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.services.errors import RecordNotFoundError
from tl_mod_requisitions import views
from tl_mod_requisitions.api import RequisitionRow, WorkOrderRow

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["requisitions"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]

#: The access word every requisitions read checks (``schema/settings/access-words.yaml``).
VIEW_WORD: Final = "requisitions.view"
#: The module the role resolver is asked about for the word.
ACCESS_MODULE: Final = "requisitions"
#: The record types a ``for`` key may name: an IWP or a CWP.
FOR_TYPES: Final = ("awp.IWP", "awp.CWP")
#: The list limit ceiling (the view clamps to 1..500 as well).
LIST_LIMIT: Final = 500


def _view_reader(
    project: str,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard(VIEW_WORD))],
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    """Authentication and the agent rules (``guard``), then the access word, before any read. A
    refusal is the API's 403 ``forbidden``."""
    with ctx.backend(True) as uow:
        require_word(
            uow.conn(),
            holder_for_principal(principal),
            scope=f"project:{project}",
            module=ACCESS_MODULE,
            word=normalise_word(VIEW_WORD),
            what=VIEW_WORD,
        )
    return actor


Reader = Annotated[str, Depends(_view_reader)]


class RequisitionList(BaseModel):
    """The requisitions a viewer may read, and how many rows the list holds."""

    rows: list[RequisitionRow]
    total: int


class RequisitionDetailBody(BaseModel):
    """A requisition with its kind-specific fields as stored, and its work order or null."""

    row: RequisitionRow
    fields: dict[str, str | None]
    work_order: WorkOrderRow | None


class WorkOrderList(BaseModel):
    """The work orders a viewer may read, and how many rows the list holds."""

    rows: list[WorkOrderRow]
    total: int


class WorkOrderDetailBody(BaseModel):
    """A work order with the key of its requisition."""

    row: WorkOrderRow
    requisition_key: str


_FOR_KEY_SQL: Final = (
    "SELECT r.id FROM cur_core_record r WHERE r.scope = :scope AND r.key = :key "
    "AND r.voided = :no AND r.type IN :types AND {visible}"
)


def _for_record_ids(
    conn: Connection, scope: str, key: str, viewer: confidentiality.Viewer
) -> list[str]:
    """The ids of the visible IWPs and CWPs with this key (a key is unique per type, so there may
    be one per type). Empty for an unknown or a hidden key."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    statement = text(_FOR_KEY_SQL.format(visible=visible)).bindparams(
        bindparam("types", expanding=True)
    )
    params = {
        "scope": scope,
        "key": key,
        "no": False,
        "types": list(FOR_TYPES),
        **extra,
    }
    return [str(row.id) for row in conn.execute(statement, params)]


@router.get("/projects/{project}/requisitions", operation_id="list_requisitions")
def list_requisitions(
    ctx: Ctx,
    actor: Reader,
    project: str,
    kind: Annotated[
        Literal["labor", "material", "general", "scaffold"] | None,
        Query(description="The requisition kind."),
    ] = None,
    state: Annotated[str | None, Query(max_length=64, description="The state.")] = None,
    requester: Annotated[str | None, Query(max_length=200, description="The requester.")] = None,
    for_: Annotated[
        str | None,
        Query(alias="for", max_length=200, description="The IWP or CWP key it serves."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT, description="At most this many rows.")] = 200,
) -> RequisitionList:
    """A project's requisitions by key, filtered by kind, state, requester and the IWP or CWP
    they serve. A hidden or unknown ``for`` key gives an empty list, as a key with none does."""
    scope = f"project:{project}"
    viewer = confidentiality.current_viewer()
    with ctx.backend(True) as uow:
        conn = uow.conn()
        if for_ is None:
            rows = views.requisition_list(
                conn,
                scope,
                kind=kind,
                state=state,
                requester=requester,
                limit=limit,
                viewer=viewer,
            )
        else:
            found: list[RequisitionRow] = []
            for record_id in _for_record_ids(conn, scope, for_, viewer):
                found.extend(
                    views.requisition_list(
                        conn,
                        scope,
                        kind=kind,
                        state=state,
                        requester=requester,
                        for_record=record_id,
                        limit=limit,
                        viewer=viewer,
                    )
                )
            rows = sorted(found, key=lambda r: (r.key, r.id))[:limit]
    return RequisitionList(rows=rows, total=len(rows))


@router.get("/projects/{project}/requisitions/{key}", operation_id="get_requisition")
def get_requisition(ctx: Ctx, actor: Reader, project: str, key: str) -> RequisitionDetailBody:
    """One requisition with its kind-specific fields and its work order (or null). 404
    `record_not_found` when it is missing or hidden (one answer for both)."""
    viewer = confidentiality.current_viewer()
    with ctx.backend(True) as uow:
        detail = views.requisition_detail(uow.conn(), f"project:{project}", key, viewer=viewer)
    if detail is None:
        raise RecordNotFoundError(f"no requisition {key!r}")
    return RequisitionDetailBody(row=detail.row, fields=detail.fields, work_order=detail.work_order)


@router.get("/projects/{project}/work-orders", operation_id="list_work_orders")
def list_work_orders(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(max_length=64, description="The state.")] = None,
    assigned_to: Annotated[
        str | None, Query(max_length=200, description="Who the work order is assigned to.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT, description="At most this many rows.")] = 200,
) -> WorkOrderList:
    """A project's work orders by key, filtered by state and assignee. Work orders of hidden
    requisitions and hidden work orders are left out, and the total counts visible rows only."""
    viewer = confidentiality.current_viewer()
    with ctx.backend(True) as uow:
        rows = views.work_order_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            assigned_to=assigned_to,
            limit=limit,
            viewer=viewer,
        )
    return WorkOrderList(rows=rows, total=len(rows))


@router.get("/projects/{project}/work-orders/{key}", operation_id="get_work_order")
def get_work_order(ctx: Ctx, actor: Reader, project: str, key: str) -> WorkOrderDetailBody:
    """One work order with the key of its requisition. 404 `record_not_found` when it is missing
    or hidden (one answer for both)."""
    viewer = confidentiality.current_viewer()
    with ctx.backend(True) as uow:
        detail = views.work_order_detail(uow.conn(), f"project:{project}", key, viewer=viewer)
    if detail is None:
        raise RecordNotFoundError(f"no work order {key!r}")
    return WorkOrderDetailBody(row=detail.row, requisition_key=detail.requisition_key)
