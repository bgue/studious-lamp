"""The CWP register on the web: ``GET /web/p/{project}/cwps`` (P2-WEB1-T09).

The CWP log of the terminal, in the log standard of ``tl_web.log``: the columns, cells, panel and
summary come from ``tl_web.present`` (the terminal's own functions, ``tl_tui.awp_text``). The panel
is the CWP's page as plain lines. The register's ``d``, ``s`` and ``c`` keys (discipline, state,
group by CWA) are not on this page yet. No actions are offered on this page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_awp.views import CwpRow

    from tl_web.log import WebAction

router = web_router()


class CwpWebLog(WebLog["CwpRow"]):
    LOG_NAME = "CWPs"
    LABEL_TYPES = ("awp.CWP",)
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.awp_text.CWP_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.awp_text.CWP_DROP

    def load_rows(self) -> list[CwpRow]:
        rows = self.client.list_cwps(self.project)
        n = len(rows)
        self._summary = f"{n} CWP" + ("s" if n != 1 else "")
        return rows

    def row_key(self, row: CwpRow) -> str:
        return row.id

    def row_record(self, row: CwpRow) -> tuple[str, str]:
        return (row.number, row.title)

    def row_cells(self, row: CwpRow) -> tuple[str, ...]:
        return present.awp_text.cwp_cells(row, self.labels)

    def panel_text(self, row: CwpRow | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        full = self.client.get_cwp(self.project, row.number)
        page = present.awp_text.cwp_page(full, self.labels, technical=self.technical, panel=True)
        return present.plain_lines(page)

    def actions_for(self, row: CwpRow) -> Sequence[WebAction]:
        return []  # no awp command has an ACTION_UI row (writes come with P2-I2)

    def summary_text(self) -> str:
        return self._summary


register("cwps", CwpWebLog)


@router.get("/p/{project}/cwps")
def cwp_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return CwpWebLog.page(request, project, q=q, sel=sel, mode=mode)
