"""The locations page: ``GET /web/p/{project}/locations`` (P2-WEB1-T14b).

The storage locations of the terminal (``tl_tui.widgets.location_screen``) as a tree, in the log
standard of ``tl_web.log``: the columns, cells, panel and summary come from
``tl_web.present.location_text`` (the terminal's own functions). Subject is indented by tree depth
in the cells; the rows come in the order the read gives (the tree order). The panel is the location
page: the stock held there and the child locations. The rows have no record page, so the page has
no Open link (D41). Read only: no action is offered and there is no filter query string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_materials.views import LocationView

    from tl_web.log import WebAction

router = web_router()

ROW_LIMIT = 500


class LocationWebLog(WebLog["LocationView"]):
    LOG_NAME = "Locations"

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        super().__init__(request, project, technical=technical)
        self._all: list[LocationView] = []
        self._summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.location_text.LOCATION_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.location_text.LOCATION_DROP

    def load_rows(self) -> list[LocationView]:
        self._all = list(self.client.list_materials_locations(self.project, limit=ROW_LIMIT))
        rows = list(self._all)
        self._summary = present.location_text.summary_line(len(rows), len(self._all), text="")
        return rows

    def row_key(self, row: LocationView) -> str:
        return row.code

    def row_open_key(self, row: LocationView) -> None:
        return None  # a location has no record page: no Open link (D41)

    def row_record(self, row: LocationView) -> tuple[str, str]:
        return (row.code, row.title)

    def row_cells(self, row: LocationView) -> tuple[str, ...]:
        return present.location_text.row_cells(
            row, present.location_text.LOCATION_COLUMNS, technical=self.technical
        )

    def panel_text(self, row: LocationView | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        stock = self.client.list_materials_stock(self.project, location=row.code, limit=ROW_LIMIT)
        page = present.location_text.location_page(
            row, self._all, stock, self.labels, technical=self.technical
        )
        return present.plain_lines(page)

    def actions_for(self, row: LocationView) -> Sequence[WebAction]:
        return []  # read only: the location screen offers no action

    def summary_text(self) -> str:
        return self._summary


register("locations", LocationWebLog)


@router.get("/p/{project}/locations")
def location_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return LocationWebLog.page(request, project, q=q, sel=sel, mode=mode)
