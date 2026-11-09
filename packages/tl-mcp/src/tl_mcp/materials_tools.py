"""Materials tools: nine reads of stock, lots, movements, receipts, locations, PO lines, take-off
lines and the item library, and ``propose_reservation`` (P2-I3-T07, M4).

The reads answer from ``tl_mod_materials.views``, so an agent, the API and a screen see the same
fields; every one names its resource for the authorizer (``guarded``) and reads as the lowest
clearance. None of them writes. ``propose_reservation`` files a pending proposal that a person
with ``materials.reserve`` accepts; the proposal is checked now by ``proposals.submit``, and
nothing changes until it is accepted. ``MATERIALS_MCP_ACTIONS`` names the ten ``mcp.<tool>``
actions for the registry (``server.py`` and ``identity.py`` add them when P2-I1 has merged).
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import Connection
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_mod_materials import views
from tl_mod_materials.errors import MtoLineNotFoundError
from tl_mod_materials.handlers.movements import Movement, ReserveStock
from tl_mod_materials.limits import MAX_VIEW_ROWS

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.intent_param import IntentParam
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

MATERIALS_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_material_stock",
        "mcp.get_material_lot",
        "mcp.list_material_movements",
        "mcp.list_material_receipts",
        "mcp.get_material_receipt",
        "mcp.list_material_locations",
        "mcp.list_po_lines",
        "mcp.list_mto_lines",
        "mcp.list_material_items",
        "mcp.propose_reservation",
    }
)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Limit = Annotated[int, Field(ge=1, le=1000, description="Rows to return.")]


def _scope(project: str) -> str:
    return f"project:{project}"


def stock_impl(
    ctx: McpContext,
    *,
    project: str,
    lot: str | None,
    location: str | None,
    item: str | None,
    heat: str | None,
    subtree: bool,
    limit: int,
) -> list[views.StockRowView]:
    """The balance rows of the project's lots by lot, location and item."""
    with ctx.factory(True) as uow:
        return views.stock(
            uow.conn(),
            _scope(project),
            lot=lot,
            location=location,
            item=item,
            heat=heat,
            subtree=subtree,
            limit=limit,
        )


def lot_impl(ctx: McpContext, *, project: str, lot: str) -> views.LotDetailView:
    """One lot with its balances, reservations and last ten movements."""
    with ctx.factory(True) as uow:
        return views.lot_detail(uow.conn(), _scope(project), lot)


def movements_impl(
    ctx: McpContext,
    *,
    project: str,
    lot: str | None,
    since: str | None,
    until: str | None,
    kind: str | None,
    limit: int,
) -> list[views.MovementView]:
    """The project's stock movements by sequence number."""
    with ctx.factory(True) as uow:
        return views.movements(
            uow.conn(),
            _scope(project),
            lot=lot,
            since=since,
            until=until,
            kind=kind,
            limit=limit,
        )


def receipts_impl(
    ctx: McpContext, *, project: str, open_only: bool, missing_mtr: bool, limit: int
) -> list[views.ReceiptView]:
    """The project's receipts by number."""
    with ctx.factory(True) as uow:
        return views.receipts(
            uow.conn(), _scope(project), open_only=open_only, missing_mtr=missing_mtr, limit=limit
        )


def receipt_impl(ctx: McpContext, *, project: str, number: str) -> views.ReceiptDetailView:
    """One receipt with its lines and files."""
    with ctx.factory(True) as uow:
        return views.receipt_detail(uow.conn(), _scope(project), number)


def locations_impl(ctx: McpContext, *, project: str, limit: int) -> list[views.LocationView]:
    """The project's storage locations in tree order."""
    with ctx.factory(True) as uow:
        return views.locations_tree(uow.conn(), _scope(project), limit=limit)


def po_lines_impl(
    ctx: McpContext, *, project: str, q: str | None, limit: int
) -> list[views.PoLineView]:
    """The project's purchase-order lines by key."""
    with ctx.factory(True) as uow:
        return views.po_lines(uow.conn(), _scope(project), q, limit=limit)


def mto_lines_impl(
    ctx: McpContext, *, project: str, work_package: str | None, short_only: bool, limit: int
) -> list[views.MtoLineView]:
    """The project's take-off lines by key."""
    with ctx.factory(True) as uow:
        return views.mto_lines(
            uow.conn(),
            _scope(project),
            work_package=work_package,
            short_only=short_only,
            limit=limit,
        )


def items_impl(ctx: McpContext, *, project: str | None, limit: int) -> list[views.MaterialItemView]:
    """The item library by code (or the items one project adopted)."""
    with ctx.factory(True) as uow:
        return views.items(
            uow.conn(), project=_scope(project) if project is not None else None, limit=limit
        )


def _mto_line(conn: Connection, scope: str, key: str) -> views.MtoLineView:
    """The take-off line with this key. The views list lines by key, so the key is found there."""
    for line in views.mto_lines(conn, scope, limit=MAX_VIEW_ROWS):
        if line.key == key:
            return line
    raise MtoLineNotFoundError("there is no such take-off line")


def propose_reservation_impl(
    ctx: McpContext,
    *,
    project: str,
    lot: str,
    location: str,
    mto_line: str,
    qty: str,
    summary: str | None,
    intent: Intent | None = None,
) -> ProposalResult:
    scope = _scope(project)
    with ctx.factory(True) as uow:
        detail = views.lot_detail(uow.conn(), scope, lot)
        line = _mto_line(uow.conn(), scope, mto_line)
    command = ReserveStock(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        movements=[
            Movement(
                lot_key=lot,
                qty=qty,
                uom=detail.uom,
                from_location=location,
                mto_line_id=line.id,
            )
        ],
        intent=intent,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_reservation",
        agent=ctx.actor,
        command=command,
        summary=summary or f"Reserve {qty} {detail.uom} of lot {lot} for {line.key} at {location}",
    )
    return _result(view)


def register_materials_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the nine read tools and the proposing tool to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_material_stock(
        project: Project,
        lot: Annotated[
            str | None, Field(max_length=MAX_PART, description="Only this lot key.")
        ] = None,
        location: Annotated[
            str | None, Field(max_length=MAX_PART, description="Only this location code.")
        ] = None,
        item: Annotated[
            str | None, Field(max_length=MAX_PART, description="Only this item code.")
        ] = None,
        heat: Annotated[
            str | None, Field(max_length=MAX_PART, description="Only this heat number.")
        ] = None,
        subtree: Annotated[
            bool,
            Field(description="With `location`: include the locations below it."),
        ] = False,
        limit: Limit = 200,
    ) -> list[views.StockRowView]:
        """List stock balances: one row per lot and location.

        Each row has the lot key, heat number, item, location, `on_hand`, `reserved` and
        `available`, all in the lot's unit. Filters narrow the rows: `lot`, `location` (a location
        code; `subtree` adds its children), `item` (an item code) and `heat`. Use `get_material_lot`
        for one lot's history.
        """
        with guarded(
            ctx,
            "list_material_stock",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return stock_impl(
                ctx,
                project=project,
                lot=lot,
                location=location,
                item=item,
                heat=heat,
                subtree=subtree,
                limit=limit,
            )

    @server.tool(annotations=READ_ONLY)
    def get_material_lot(
        project: Project,
        lot: Annotated[str, Field(min_length=1, max_length=MAX_PART, description="The lot key.")],
    ) -> views.LotDetailView:
        """Get one stock lot: its item, heat, receipt, balances by location, reservations and its
        last ten movements, newest first. `uom` is the unit every quantity of the lot is in.
        """
        with guarded(
            ctx,
            "get_material_lot",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return lot_impl(ctx, project=project, lot=lot)

    @server.tool(annotations=READ_ONLY)
    def list_material_movements(
        project: Project,
        lot: Annotated[
            str | None, Field(max_length=MAX_PART, description="Only this lot key.")
        ] = None,
        since: Annotated[
            str | None, Field(max_length=MAX_PART, description="Recorded on or after `YYYY-MM-DD`.")
        ] = None,
        until: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Recorded on or before `YYYY-MM-DD`."),
        ] = None,
        kind: Annotated[
            str | None,
            Field(
                max_length=MAX_PART, description="Only this movement kind, such as `IssueStock`."
            ),
        ] = None,
        limit: Limit = 200,
    ) -> list[views.MovementView]:
        """List stock movements, oldest first: receipts, issues, transfers, returns and
        reservations, each with its lot, quantity, unit, locations and the take-off line it named.
        Filter by `lot`, by date range (`since`, `until`) and by `kind`.
        """
        with guarded(
            ctx,
            "list_material_movements",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return movements_impl(
                ctx,
                project=project,
                lot=lot,
                since=since,
                until=until,
                kind=kind,
                limit=limit,
            )

    @server.tool(annotations=READ_ONLY)
    def list_material_receipts(
        project: Project,
        open_only: Annotated[
            bool, Field(description="Only receipts not yet decided (Received or Inspected).")
        ] = False,
        missing_mtr: Annotated[
            bool,
            Field(description="Only receipts that still lack a required material test report."),
        ] = False,
        limit: Limit = 200,
    ) -> list[views.ReceiptView]:
        """List goods receipts by number, with state, date, location, supplier, line count and
        whether a material test report (`mtr`) is required and in.
        Use `get_material_receipt` for the lines and files of one receipt.
        """
        with guarded(
            ctx,
            "list_material_receipts",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return receipts_impl(
                ctx,
                project=project,
                open_only=open_only,
                missing_mtr=missing_mtr,
                limit=limit,
            )

    @server.tool(annotations=READ_ONLY)
    def get_material_receipt(
        project: Project,
        number: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The receipt number.")
        ],
    ) -> views.ReceiptDetailView:
        """Get one goods receipt with its lines (item, quantity, lot), its inspection and decision
        dates and people, any rejection reason, and its files.
        """
        with guarded(
            ctx,
            "get_material_receipt",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return receipt_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def list_material_locations(project: Project, limit: Limit = 200) -> list[views.LocationView]:
        """List the project's storage locations in tree order (a parent, then its children by code).

        Each row has its code, title, kind, parent code and depth, whether it is retired, and how
        many lots and balance rows it holds.
        """
        with guarded(
            ctx,
            "list_material_locations",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return locations_impl(ctx, project=project, limit=limit)

    @server.tool(annotations=READ_ONLY)
    def list_po_lines(
        project: Project,
        q: Annotated[
            str | None,
            Field(
                max_length=MAX_PART,
                description="Text in the line key, the item or the supplier.",
            ),
        ] = None,
        limit: Limit = 200,
    ) -> list[views.PoLineView]:
        """List purchase-order lines by key: the item, quantity ordered and received, unit, promised
        date and supplier. `q` keeps the lines whose key, item or supplier contains that text.
        """
        with guarded(
            ctx, "list_po_lines", resource_name("materials", project), parts=(("project", project),)
        ):
            return po_lines_impl(ctx, project=project, q=q, limit=limit)

    @server.tool(annotations=READ_ONLY)
    def list_mto_lines(
        project: Project,
        work_package: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Only the lines of this work package number."),
        ] = None,
        short_only: Annotated[
            bool,
            Field(description="Only lines not yet covered by reservations and issues."),
        ] = False,
        limit: Limit = 200,
    ) -> list[views.MtoLineView]:
        """List take-off (material take-off) lines by key, such as `ISO-1234@A/MTO/001`.

        Each row has the quantity `required`, `reserved`, `issued` and `short` (never below zero),
        the item, the unit and its work package. `short_only` keeps the lines still short. Use the
        line key as `mto_line` in `propose_reservation`.
        """
        with guarded(
            ctx,
            "list_mto_lines",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return mto_lines_impl(
                ctx,
                project=project,
                work_package=work_package,
                short_only=short_only,
                limit=limit,
            )

    @server.tool(annotations=READ_ONLY)
    def list_material_items(
        project: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="Only the items this project adopted, for example `P123`.",
            ),
        ] = None,
        limit: Limit = 200,
    ) -> list[views.MaterialItemView]:
        """List the item library by code: category, base unit, size, rating, material code,
        whether it is consumable or retired, and how many projects hold a copy of it.
        Without `project` it lists the whole company library.
        """
        parts: tuple[tuple[str, str], ...] = () if project is None else (("project", project),)
        with guarded(
            ctx, "list_material_items", resource_name("materials", "company"), parts=parts
        ):
            return items_impl(ctx, project=project, limit=limit)

    @server.tool(annotations=PROPOSES)
    def propose_reservation(
        project: Project,
        lot: Annotated[
            str,
            Field(
                min_length=1, max_length=MAX_PART, description="The lot key, `P123-RCPT-0001@1`."
            ),
        ],
        location: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="The location code the stock is held at.",
            ),
        ],
        mto_line: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_PART,
                description="The take-off line key, `ISO-1234@A/MTO/001`.",
            ),
        ],
        qty: Annotated[
            str,
            Field(
                min_length=1,
                max_length=32,
                description="The quantity to hold, in the lot's unit, as a decimal string.",
            ),
        ],
        intent: IntentParam = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose holding some of a lot's available stock for a take-off line.

        Nothing is reserved now. The proposal is checked now, so an error means it could not be
        applied (an unknown lot or line, or more than the lot has available at that location). A
        person with the materials reserve role accepts or rejects it in the review queue. The unit
        is the lot's own unit; `qty` is in that unit.
        """
        with guarded(
            ctx,
            "propose_reservation",
            resource_name("materials", project),
            parts=(("project", project),),
        ):
            return propose_reservation_impl(
                ctx,
                project=project,
                lot=lot,
                location=location,
                mto_line=mto_line,
                qty=qty,
                summary=summary,
                intent=intent,
            )
