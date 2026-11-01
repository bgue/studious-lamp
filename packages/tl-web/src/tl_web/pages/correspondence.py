"""The correspondence register on the web: ``GET /web/p/{project}/correspondence`` (P2-WEB1-T01).

The register mode of the terminal's correspondence screen, in the log standard of ``tl_web.log``:
the columns, cells, panel and summary come from ``tl_web.present`` (the terminal's own functions).
The triage inbox and the clocks are not on the web yet; ``?mode=technical`` is for an admin only and
is handled by ``WebLog.for_request``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from tl_mod_correspondence.views import RegisterLineView

router = web_router()

TRANSMITTAL_NOTE = "Transmittal. Open it in the terminal for the full list."


class CorrespondenceWebLog(WebLog["RegisterLineView"]):
    LOG_NAME = "Correspondence register"
    LABEL_TYPES = ("correspondence.Correspondence",)
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.correspondence_text.REGISTER_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.correspondence_text.REGISTER_DROP

    def load_rows(self) -> list[RegisterLineView]:
        rows = self.client.list_correspondence(self.project, state=None, sources=True, limit=500)
        self._summary = present.correspondence_text.summary_line("register", len(rows))
        return rows

    def row_key(self, row: RegisterLineView) -> str:
        return row.id

    def row_record(self, row: RegisterLineView) -> tuple[str, str]:
        return (row.number, row.subject)

    def row_cells(self, row: RegisterLineView) -> tuple[str, ...]:
        return present.correspondence_text.register_cells(row, self.labels)

    def panel_text(self, row: RegisterLineView | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        if row.kind != "item":
            return [f"{row.number}  {row.subject}", TRANSMITTAL_NOTE]
        item = self.client.get_correspondence(self.project, row.number)
        page = present.correspondence_text.item_page(
            item,
            None,
            self.labels,
            technical=self.technical,
            client=present.as_client(self.client),
            project=self.project,
        )
        return present.plain_lines(page)

    def summary_text(self) -> str:
        return self._summary


register("correspondence", CorrespondenceWebLog)


@router.get("/p/{project}/correspondence")
def correspondence_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return CorrespondenceWebLog.page(request, project, q=q, sel=sel, mode=mode)
