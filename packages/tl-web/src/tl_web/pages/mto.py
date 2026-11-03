"""The take-off lines page: ``GET /web/p/{project}/mto`` (P2-WEB1-T13b).

The MTO lines log of the terminal, in the log standard of ``tl_web.log``: the columns, cells,
panel and summary come from ``tl_web.present.mto_text`` (the terminal's own functions). Two query
strings narrow the list: ``?short=1`` (the short lines only) and ``?wp=<work package number>``.
A take-off line has no record page, so the page offers no Open link (D41). Read only: no action
is offered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_materials.views import MtoLineView

    from tl_web.log import WebAction

router = web_router()


class MtoWebLog(WebLog["MtoLineView"]):
    LOG_NAME = "Take-off lines"
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.mto_text.MTO_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.mto_text.MTO_DROP

    def load_rows(self) -> list[MtoLineView]:
        params = self.request.query_params
        short_only = params.get("short") == "1"
        work_package = params.get("wp", "").strip() or None
        rows = self.client.list_materials_mto_lines(
            self.project, work_package=work_package, short_only=short_only, limit=500
        )
        self._summary = present.mto_text.summary_line(
            len(rows),
            len(rows),
            short_only=short_only,
            work_package=work_package,
            text="",
        )
        return rows

    def row_key(self, row: MtoLineView) -> str:
        return row.key

    def row_open_key(self, row: MtoLineView) -> None:
        return None  # a take-off line has no record page: no Open link (D41)

    def row_record(self, row: MtoLineView) -> tuple[str, str]:
        return (row.key, row.item_title)

    def row_cells(self, row: MtoLineView) -> tuple[str, ...]:
        return present.mto_text.row_cells(row, self.columns(), technical=self.technical)

    def panel_text(self, row: MtoLineView | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        detail = self.client.get_materials_mto_line(self.project, row.key)
        page = present.mto_text.mto_page(detail, self.labels, technical=self.technical)
        return present.plain_lines(page)

    def actions_for(self, row: MtoLineView) -> Sequence[WebAction]:
        return []  # read only: the take-off lines have no ACTION_UI row

    def summary_text(self) -> str:
        return self._summary


register("mto", MtoWebLog)


@router.get("/p/{project}/mto")
def mto_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return MtoWebLog.page(request, project, q=q, sel=sel, mode=mode)
