"""The IWP log on the web: ``GET /web/p/{project}/iwps`` (P2-I2-TW1).

The IWP log of the terminal, in the log standard of ``tl_web.log``: the columns, cells, panel and
summary come from ``tl_web.present`` (the terminal's own functions, ``tl_tui.iwp_text``). The panel
is the IWP's page as plain lines (``iwp_page``, panel form: the first 10 scope rows). The register's
``s``, ``d``, ``m`` and ``r`` filters (state, discipline, mine, Ready) are not on this page yet, so
the page has no filters. No actions are offered on this page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_awp.iwp_views import IwpRow

    from tl_web.log import WebAction

router = web_router()


class IwpWebLog(WebLog["IwpRow"]):
    LOG_NAME = "IWPs"
    LABEL_TYPES = ("awp.IWP",)
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.iwp_text.IWP_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.iwp_text.IWP_DROP

    def load_rows(self) -> list[IwpRow]:
        rows = self.client.list_iwps(self.project)
        self._summary = present.iwp_text.iwp_summary(len(rows), len(rows))
        return rows

    def row_key(self, row: IwpRow) -> str:
        return row.id

    def row_record(self, row: IwpRow) -> tuple[str, str]:
        return (row.number, row.title)

    def row_cells(self, row: IwpRow) -> Sequence[str]:
        return present.iwp_text.iwp_cells(row, self.labels)

    def panel_page(self, row: IwpRow) -> present.Page:
        full = self.client.get_iwp(self.project, row.number)
        scope = self.client.list_iwp_scope(self.project, row.number)
        return present.iwp_text.iwp_page(
            full, scope, self.labels, technical=self.technical, panel=True
        )

    def actions_for(self, row: IwpRow) -> Sequence[WebAction]:
        return []  # no awp command has an ACTION_UI row for IWPs (writes come later)

    def summary_text(self) -> str:
        return self._summary


register("iwps", IwpWebLog)


@router.get("/p/{project}/iwps")
def iwp_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return IwpWebLog.page(request, project, q=q, sel=sel, mode=mode)
