"""The WBS tree page: ``GET /web/p/{project}/wbs`` (P2-WEB1-T10).

The WBS tree of the terminal, depth first, in the log standard of ``tl_web.log``: the columns,
cells, panel and summary come from ``tl_web.present.wbs_text`` (the terminal's own functions). Two
query strings narrow the list and never hide a row the unfiltered list would not have: ``?depth=N``
(an integer from 1 to 8) keeps the nodes above depth N, and ``?unallocated=1`` keeps the leaves that
carry no cost code. A bad value means "absent". No actions are offered on this page in i1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_awp.views import WbsRow

    from tl_web.log import WebAction

router = web_router()

UNALLOCATED = "1"


def _depth(request: Request) -> int | None:
    """``?depth=N`` as an integer from 1 to 8; anything else is absent."""
    raw = request.query_params.get("depth", "")
    if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 8:
        return int(raw)
    return None


class WbsWebLog(WebLog["WbsRow"]):
    LOG_NAME = "WBS tree"

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        super().__init__(request, project, technical=technical)
        self._tree: list[WbsRow] = []
        self._summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.wbs_text.WBS_COLUMNS

    def load_rows(self) -> list[WbsRow]:
        tree = list(self.client.wbs_tree(self.project))
        self._tree = tree
        rows = list(tree)
        asked = self.request.query_params.get("unallocated") == UNALLOCATED
        if asked:
            rows = present.wbs_text.unallocated_leaves(tree)
        depth = _depth(self.request)
        if depth is not None:
            rows = present.wbs_text.depth_limited(rows, depth)
        self._summary = present.layout.join_facts(
            f"{len(rows)} of {len(tree)} nodes",
            f"depth {depth}" if depth is not None else "",
            "unallocated leaves" if asked else "",
        )
        return rows

    def row_key(self, row: WbsRow) -> str:
        return row.id

    def row_record(self, row: WbsRow) -> tuple[str, str]:
        return (row.code, row.title)

    def row_cells(self, row: WbsRow) -> tuple[str, ...]:
        return present.wbs_text.wbs_cells(row, self._tree)

    def panel_text(self, row: WbsRow | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        full = self.client.get_wbs_node(self.project, row.code)
        return present.plain_lines(
            present.wbs_text.wbs_page(full, self._tree, panel=True, technical=self.technical)
        )

    def actions_for(self, row: WbsRow) -> Sequence[WebAction]:
        return []  # no awp command has an ACTION_UI row; writes come with P2-I2

    def summary_text(self) -> str:
        return self._summary


register("wbs", WbsWebLog)


@router.get("/p/{project}/wbs")
def wbs_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return WbsWebLog.page(request, project, q=q, sel=sel, mode=mode)
