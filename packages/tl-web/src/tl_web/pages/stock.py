"""The stock page: ``GET /web/p/{project}/stock`` (P2-WEB1-T12, the M4 twin of ``stock_screen.py``).

The balances by lot and location, in the log standard of ``tl_web.log``: the columns, cells, panel
and summary come from ``tl_web.present.materials_text`` (the terminal's own functions). Four text
query strings narrow the list on the server, as the terminal's keys do: ``?lot=``, ``?item=``,
``?heat=`` and ``?location=`` (1 to 200 characters; anything else means "absent"), and
``?subtree=1``, which only means something with ``location`` (the places below it as well). The
panel is the lot of the row: its quantities, reservations, last movements and traceability, with
the MTR file name of its receipt. A row has no record page, so the Open link is never shown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response
from tl_api.errors import body_for

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_materials.views import StockRowView

    from tl_web.log import WebAction

router = web_router()

TEXT_MAX = 200
SUBTREE = "1"
ROW_LIMIT = 500
MTR_SLOT = "mtr"  # tl_mod_materials.views.MTR_SLOT: the slot of a receipt's MTR file


def _text(request: Request, name: str) -> str | None:
    """A text query string of 1 to 200 characters; anything else is absent."""
    raw = request.query_params.get(name, "")
    return raw if 1 <= len(raw) <= TEXT_MAX else None


def _is_not_found(exc: Exception) -> bool:
    """True when ``exc`` is an expected failure the API answers with 404."""
    mapped = body_for(exc)
    return mapped is not None and mapped[0] == 404


class StockWebLog(WebLog["StockRowView"]):
    LOG_NAME = "Stock"

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        super().__init__(request, project, technical=technical)
        self._summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.materials_text.STOCK_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return present.materials_text.STOCK_DROP

    def load_rows(self) -> list[StockRowView]:
        lot = _text(self.request, "lot")
        item = _text(self.request, "item")
        heat = _text(self.request, "heat")
        location = _text(self.request, "location")
        subtree = location is not None and self.request.query_params.get("subtree") == SUBTREE
        rows = list(
            self.client.list_materials_stock(
                self.project,
                lot=lot,
                location=location,
                item=item,
                heat=heat,
                subtree=subtree,
                limit=ROW_LIMIT,
            )
        )
        self._summary = present.materials_text.stock_summary(
            len(rows),
            len(rows),
            item=item,
            location=location,
            heat=heat,
            lot=lot,
            subtree=subtree,
        )
        return rows

    def row_key(self, row: StockRowView) -> str:
        return f"{row.lot}@{row.location}"

    def row_open_key(self, row: StockRowView) -> None:
        return None  # a stock row has no record page (D41): no Open link, no data-open

    def row_record(self, row: StockRowView) -> tuple[str, str]:
        return (self.row_key(row), row.item_title)

    def row_cells(self, row: StockRowView) -> tuple[str, ...]:
        return present.materials_text.stock_cells(
            row, self.columns(), self.labels, technical=self.technical
        )

    def panel_text(self, row: StockRowView | None) -> list[str]:
        if row is None:
            return ["No stock on hand"]
        detail = self.client.get_materials_lot(self.project, row.lot)
        return present.plain_lines(
            present.materials_text.lot_page(
                detail,
                row,
                self.labels,
                mtr=self._mtr_of(detail.receipt),
                technical=self.technical,
            )
        )

    def actions_for(self, row: StockRowView) -> Sequence[WebAction]:
        return []  # read only

    def summary_text(self) -> str:
        return self._summary

    def _mtr_of(self, receipt: str | None) -> str | None:
        """The file name of the receipt's MTR; None when there is no receipt or it is not found."""
        if receipt is None:
            return None
        try:
            detail = self.client.get_materials_receipt(self.project, receipt)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        for file in detail.files:
            if file.slot == MTR_SLOT:
                return file.filename
        return None


register("stock", StockWebLog)


@router.get("/p/{project}/stock")
def stock_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return StockWebLog.page(request, project, q=q, sel=sel, mode=mode)
