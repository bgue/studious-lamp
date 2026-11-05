"""The receipts log on the web: ``GET /web/p/{project}/receipts`` (P2-WEB1-T13).

The receipts log of the terminal (``tl_tui.widgets.receipt_log``), in the log standard of
``tl_web.log``: the columns, cells, panel and summary come from ``tl_web.present`` (the terminal's
own functions). The panel is the receipt page: lines, delivery, inspection and files. The rows have
no record page, so the page has no Open link (D41). ``?open=1`` shows the receipts not yet decided
and ``?mtr=missing`` the receipts whose required MTR is missing; any other value means absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_materials.views import ReceiptView

    from tl_web.log import WebAction

router = web_router()


class ReceiptWebLog(WebLog["ReceiptView"]):
    LOG_NAME = "Receipts"
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.receipt_text.RECEIPT_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.receipt_text.RECEIPT_DROP

    def load_rows(self) -> list[ReceiptView]:
        query = self.request.query_params
        open_only = query.get("open") == "1"
        missing_mtr = query.get("mtr") == "missing"
        rows = self.client.list_materials_receipts(
            self.project, open_only=open_only, missing_mtr=missing_mtr, limit=500
        )
        self._summary = present.receipt_text.summary_line(
            len(rows), len(rows), open_only=open_only, missing_mtr=missing_mtr, text=""
        )
        return list(rows)

    def row_key(self, row: ReceiptView) -> str:
        return row.number

    def row_open_key(self, row: ReceiptView) -> None:
        return None  # a receipt has no record page: no Open link (D41)

    def row_record(self, row: ReceiptView) -> tuple[str, str]:
        return (row.number, row.title)

    def row_cells(self, row: ReceiptView) -> tuple[str, ...]:
        return present.receipt_text.row_cells(
            row, present.receipt_text.RECEIPT_COLUMNS, self.labels, technical=self.technical
        )

    def panel_page(self, row: ReceiptView) -> present.Page:
        detail = self.client.get_materials_receipt(self.project, row.number)
        return present.receipt_text.receipt_page(detail, self.labels, technical=self.technical)

    def actions_for(self, row: ReceiptView) -> Sequence[WebAction]:
        return []  # read only: the receipt commands have no ACTION_UI row yet (P2-I2)

    def summary_text(self) -> str:
        return self._summary


register("receipts", ReceiptWebLog)


@router.get("/p/{project}/receipts")
def receipt_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return ReceiptWebLog.page(request, project, q=q, sel=sel, mode=mode)
