"""The RFI log page: ``GET /web/p/{project}/rfis`` (spec web-client-i1, section 7).

The log standard of ``tl_web.log``: the terminal's RFI columns, cells, panel and summary
(``rfi_text``), the offered actions, and the one 404 page for a hidden or unknown record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from tl_mod_correspondence.reports_technical import RfiLogLine

router = web_router()


class RfiWebLog(WebLog["RfiLogLine"]):
    LOG_NAME = "RFI log"
    LABEL_TYPES = ("correspondence.TechnicalItem",)
    _summary = ""

    def columns(self):
        return present.rfi_text.RFI_COLUMNS

    def drop_order(self):
        return present.rfi_text.RFI_DROP

    def load_rows(self):
        log = self.client.list_rfis(self.project, limit=500)
        self._summary = present.rfi_text.rfi_summary(log)
        return log.lines

    def row_key(self, row: RfiLogLine) -> str:
        return row.id

    def row_record(self, row: RfiLogLine) -> tuple[str, str]:
        return (row.number, row.subject)

    def row_cells(self, row: RfiLogLine):
        return present.rfi_text.rfi_cells(row, self.labels, technical=self.technical)

    def panel_text(self, row: RfiLogLine | None) -> list[str]:
        if row is None:
            return []
        view = self.client.get_rfi(self.project, row.number)
        page = present.rfi_text.rfi_page(
            view,
            self.labels,
            technical=self.technical,
            client=present.as_client(self.client),
            project=self.project,
        )
        return present.plain_lines(page)

    def summary_text(self) -> str:
        return self._summary


register("rfis", RfiWebLog)


@router.get("/p/{project}/rfis")
def rfi_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return RfiWebLog.page(request, project, q=q, sel=sel, mode=mode)
