"""Reads of the materials module: the library, locations, PO lines, stock, lots, movements, receipts
and take-off lines (P2-I3-T04a).

Thin: one call into ``tl_mod_materials.views`` per route. Every read needs the action
``document.read``, which agents hold because they only read (the fine word ``materials.view`` is
the read role). The API sets the viewer from the principal for the whole request, and the views
filter by it (ADR-0016), so a route passes no viewer: a hidden record answers 404 as one that never
existed. Every list has a ``limit`` no larger than ``MAX_VIEW_ROWS``. The writes are the
module's commands under ``POST /commands/<Name>``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_mod_materials import views
from tl_mod_materials.limits import MAX_VIEW_ROWS

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["materials"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]
Limit = Annotated[int, Query(ge=1, le=MAX_VIEW_ROWS, description="At most this many rows.")]


@router.get("/projects/{project}/materials/stock", operation_id="list_materials_stock")
def list_materials_stock(
    ctx: Ctx,
    actor: Reader,
    project: str,
    lot: Annotated[str | None, Query(max_length=200, description="A lot key.")] = None,
    location: Annotated[str | None, Query(max_length=200, description="A location code.")] = None,
    item: Annotated[str | None, Query(max_length=200, description="An item code.")] = None,
    heat: Annotated[str | None, Query(max_length=200, description="A heat number.")] = None,
    subtree: Annotated[bool, Query(description="With location: it and all below it.")] = False,
    limit: Limit = MAX_VIEW_ROWS,
) -> list[views.StockRowView]:
    """The balances of a project by lot and location; rows at zero are not listed."""
    with ctx.backend(True) as uow:
        return views.stock(
            uow.conn(),
            f"project:{project}",
            lot=lot,
            location=location,
            item=item,
            heat=heat,
            subtree=subtree,
            limit=limit,
        )


@router.get("/projects/{project}/materials/movements", operation_id="list_materials_movements")
def list_materials_movements(
    ctx: Ctx,
    actor: Reader,
    project: str,
    lot: Annotated[str | None, Query(max_length=200, description="A lot key.")] = None,
    since: Annotated[
        str | None, Query(max_length=200, description="ISO date or timestamp.")
    ] = None,
    until: Annotated[
        str | None, Query(max_length=200, description="ISO date or timestamp.")
    ] = None,
    kind: Annotated[str | None, Query(max_length=200, description="A movement kind.")] = None,
    limit: Limit = MAX_VIEW_ROWS,
) -> list[views.MovementView]:
    """The movement log of a project in ledger order."""
    with ctx.backend(True) as uow:
        return views.movements(
            uow.conn(),
            f"project:{project}",
            lot=lot,
            since=since,
            until=until,
            kind=kind,
            limit=limit,
        )


@router.get("/projects/{project}/materials/receipts", operation_id="list_materials_receipts")
def list_materials_receipts(
    ctx: Ctx,
    actor: Reader,
    project: str,
    open_only: Annotated[bool, Query(description="Only receipts not yet closed.")] = False,
    missing_mtr: Annotated[
        bool, Query(description="Only receipts without a mill test report.")
    ] = False,
    limit: Limit = MAX_VIEW_ROWS,
) -> list[views.ReceiptView]:
    """A project's goods receipts, newest first."""
    with ctx.backend(True) as uow:
        return views.receipts(
            uow.conn(),
            f"project:{project}",
            open_only=open_only,
            missing_mtr=missing_mtr,
            limit=limit,
        )


@router.get("/projects/{project}/materials/locations", operation_id="list_materials_locations")
def list_materials_locations(
    ctx: Ctx, actor: Reader, project: str, limit: Limit = MAX_VIEW_ROWS
) -> list[views.LocationView]:
    """A project's storage locations in tree order."""
    with ctx.backend(True) as uow:
        return views.locations_tree(uow.conn(), f"project:{project}", limit=limit)


@router.get("/projects/{project}/materials/po-lines", operation_id="list_materials_po_lines")
def list_materials_po_lines(
    ctx: Ctx,
    actor: Reader,
    project: str,
    q: Annotated[
        str | None, Query(max_length=200, description="In the key, the item or the supplier.")
    ] = None,
    limit: Limit = MAX_VIEW_ROWS,
) -> list[views.PoLineView]:
    """A project's purchase-order lines by key."""
    with ctx.backend(True) as uow:
        return views.po_lines(uow.conn(), f"project:{project}", q, limit=limit)


@router.get("/projects/{project}/materials/mto-lines", operation_id="list_materials_mto_lines")
def list_materials_mto_lines(
    ctx: Ctx,
    actor: Reader,
    project: str,
    work_package: Annotated[
        str | None, Query(max_length=64, description="A work package code.")
    ] = None,
    short_only: Annotated[bool, Query(description="Only lines with a shortage.")] = False,
    limit: Limit = MAX_VIEW_ROWS,
) -> list[views.MtoLineView]:
    """A project's take-off lines, by work package when named."""
    with ctx.backend(True) as uow:
        return views.mto_lines(
            uow.conn(),
            f"project:{project}",
            work_package=work_package,
            short_only=short_only,
            limit=limit,
        )


@router.get("/companies/materials/items", operation_id="list_materials_items")
def list_materials_items(
    ctx: Ctx,
    actor: Reader,
    project: Annotated[
        str | None, Query(max_length=200, description="Keep the items this project adopted.")
    ] = None,
    limit: Limit = MAX_VIEW_ROWS,
) -> list[views.MaterialItemView]:
    """The company library of items by code; with ``project``, the items that project adopted."""
    with ctx.backend(True) as uow:
        return views.items(
            uow.conn(), project=f"project:{project}" if project else None, limit=limit
        )


@router.get("/projects/{project}/materials/lots/{key:path}", operation_id="get_materials_lot")
def get_materials_lot(ctx: Ctx, actor: Reader, project: str, key: str) -> views.LotDetailView:
    """One lot with its balances, reservations and last ten movements.

    404 `materials_lot_not_found` when there is no such lot (or the reader may not see it).
    """
    with ctx.backend(True) as uow:
        return views.lot_detail(uow.conn(), f"project:{project}", key)


@router.get("/projects/{project}/materials/receipts/{number}", operation_id="get_materials_receipt")
def get_materials_receipt(
    ctx: Ctx, actor: Reader, project: str, number: str
) -> views.ReceiptDetailView:
    """One goods receipt with its lines and files. 404 `materials_receipt_not_found`."""
    with ctx.backend(True) as uow:
        return views.receipt_detail(uow.conn(), f"project:{project}", number)
