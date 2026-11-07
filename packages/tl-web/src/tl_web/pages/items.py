"""The company item library on the web: ``GET /web/p/{project}/items`` (P2-WEB1-T14).

The item library of the terminal (``tl_tui.widgets.item_library``), in the log standard of
``tl_web.log``: the columns, cells, panel and summary come from ``tl_web.present`` (the terminal's
own functions). The panel is the item page: its specification and the projects that use the item
with their quantities. The rows have no record page, so the page has no Open link (D41).
``?state=Active`` or ``?state=Retired`` narrows the list; any other value means absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_materials.views import MaterialItemView

    from tl_web.log import WebAction

router = web_router()

STATES = ("Active", "Retired")


class ItemWebLog(WebLog["MaterialItemView"]):
    LOG_NAME = "Item library"
    _all: list[MaterialItemView]
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.item_text.ITEM_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.item_text.ITEM_DROP

    def load_rows(self) -> list[MaterialItemView]:
        self._all = list(self.client.list_materials_items(project=self.project, limit=500))
        state = self.request.query_params.get("state")
        state = state if state in STATES else None
        rows = self._all
        if state is not None:
            retired = state == "Retired"
            rows = [view for view in rows if view.retired == retired]
        self._summary = present.item_text.summary_line(
            len(rows), len(self._all), state=state, project=self.project, text=""
        )
        return rows

    def row_key(self, row: MaterialItemView) -> str:
        return row.code

    def row_open_key(self, row: MaterialItemView) -> None:
        return None  # an item has no record page: no Open link (D41)

    def row_record(self, row: MaterialItemView) -> tuple[str, str]:
        return (row.code, row.title)

    def row_cells(self, row: MaterialItemView) -> tuple[str, ...]:
        return present.item_text.row_cells(
            row, present.item_text.ITEM_COLUMNS, self.labels, technical=self.technical
        )

    def panel_page(self, row: MaterialItemView) -> present.Page:
        projects = self.client.list_materials_item_projects(row.code)
        return present.item_text.item_page(row, projects, self.labels, technical=self.technical)

    def actions_for(self, row: MaterialItemView) -> Sequence[WebAction]:
        return []  # read only: the item library offers no action

    def summary_text(self) -> str:
        return self._summary


register("items", ItemWebLog)


@router.get("/p/{project}/items")
def item_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return ItemWebLog.page(request, project, q=q, sel=sel, mode=mode)
