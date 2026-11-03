"""The CWA register on the web: ``GET /web/p/{project}/cwas`` (P2-WEB1-T09b).

The CWA register of the terminal, in the log standard of ``tl_web.log``: the columns, cells, panel
and summary come from ``tl_web.present`` (the terminal's own functions, ``tl_tui.cwa_text``). Every
area is listed, the retired ones too; the panel shows the area's location, its path position and
its CWPs. No actions are offered on this page.
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

    from tl_mod_awp.views import PathView

    from tl_web.log import WebAction

router = web_router()


class CwaWebLog(WebLog["present.cwa_text.CwaLine"]):
    LOG_NAME = "CWA register"
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.cwa_text.CWA_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.cwa_text.CWA_DROP

    def load_rows(self) -> list[present.cwa_text.CwaLine]:
        cwas = self.client.list_cwas(self.project)
        path = self._path()
        cwps = self.client.list_cwps(self.project)
        lines = present.cwa_text.cwa_lines(cwas, path, cwps)
        retired = sum(1 for line in lines if line.row.retired)
        self._summary = present.layout.join_facts(
            f"{len(lines)} CWAs", f"{retired} retired" if retired else ""
        )
        return lines

    def row_key(self, row: present.cwa_text.CwaLine) -> str:
        return row.row.id

    def row_record(self, row: present.cwa_text.CwaLine) -> tuple[str, str]:
        return (row.row.code, row.row.title)

    def row_cells(self, row: present.cwa_text.CwaLine) -> tuple[str, ...]:
        return present.cwa_text.cwa_cells(row)

    def panel_text(self, row: present.cwa_text.CwaLine | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        page = present.cwa_text.cwa_page(row, panel=True, technical=self.technical)
        return present.plain_lines(page)

    def actions_for(self, row: present.cwa_text.CwaLine) -> Sequence[WebAction]:
        return []  # the CWA commands have no ACTION_UI row; writes come with P2-I2

    def summary_text(self) -> str:
        return self._summary

    def _path(self) -> PathView | None:
        """The current path, or None when the project has no path yet. Only a ``record_not_found``
        means that; any other error is raised as it is."""
        try:
            return self.client.get_path(self.project)
        except Exception as exc:
            mapped = body_for(exc)
            if mapped is not None and mapped[1].error == "record_not_found":
                return None
            raise


register("cwas", CwaWebLog)


@router.get("/p/{project}/cwas")
def cwa_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return CwaWebLog.page(request, project, q=q, sel=sel, mode=mode)
