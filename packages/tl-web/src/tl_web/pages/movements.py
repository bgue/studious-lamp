"""The stock movements log on the web: ``GET /web/p/{project}/movements`` (P2-WEB1-T12b).

The movement log of the terminal (``tl_tui.widgets.movement_screen``), in the log standard of
``tl_web.log``: the columns, cells, panel and summary come from ``tl_web.present.materials_text``
(the terminal's own functions). Three query strings narrow the list and never hide a row the
unfiltered list would not have: ``?lot=`` (a lot key), ``?kind=`` (one kind of the rows read, as a
``KIND_WORDS`` key) and ``?period=`` (a member of ``PERIODS``; anything else is ``all``). A bad
``?kind=`` means "absent". A movement has no record page, so the page offers no Open link and no
action. The panel shows the row itself and makes no read.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_materials.views import MovementView

    from tl_web.log import WebAction

router = web_router()

ROW_LIMIT = 500


def _period(request: Request) -> str:
    """``?period=`` when it is a member of ``PERIODS``; anything else is ``all``."""
    raw = request.query_params.get("period", "")
    return raw if raw in present.materials_text.PERIODS else "all"


def _lot(request: Request) -> str | None:
    """``?lot=`` as text; empty is no lot."""
    return request.query_params.get("lot", "").strip() or None


def _kind_word(row: MovementView) -> str:
    """The kind of a movement as its word (``Issue``, ``Receipt``), the terminal's cell."""
    return present.materials_text.movement_cells(row, ("Kind",))[0]


class MovementWebLog(WebLog["MovementView"]):
    LOG_NAME = "Movements"

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        super().__init__(request, project, technical=technical)
        self._summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.materials_text.MOVEMENT_COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.materials_text.MOVEMENT_DROP

    def keep_columns(self) -> Sequence[str]:
        """The movement log has no State column: Date and Kind always show (as the terminal)."""
        return list(self.columns())[:2]

    def load_rows(self) -> list[MovementView]:
        period = _period(self.request)
        lot = _lot(self.request)
        since, until = present.materials_text.period_range(period, date.today().isoformat())
        views = list(
            self.client.list_materials_movements(
                self.project, lot=lot, since=since, until=until, limit=ROW_LIMIT
            )
        )
        asked = self.request.query_params.get("kind", "")
        read_kinds = {view.kind for view in views}
        kind = asked if asked in present.materials_text.KIND_WORDS and asked in read_kinds else None
        rows = [view for view in views if kind is None or view.kind == kind]
        self._summary = present.materials_text.movement_summary(
            len(rows), len(views), kind=kind, period=period, lot=lot
        )
        return rows

    def row_key(self, row: MovementView) -> str:
        return str(row.seq)

    def row_open_key(self, row: MovementView) -> None:
        return None  # a movement has no record page: no Open link (D41)

    def row_cells(self, row: MovementView) -> tuple[str, ...]:
        return present.materials_text.movement_cells(
            row, self.columns(), self.labels, technical=self.technical
        )

    def row_record(self, row: MovementView) -> tuple[str, str]:
        return (f"#{row.seq}", _kind_word(row))

    def panel_text(self, row: MovementView | None) -> list[str]:
        if row is None:
            return ["No movements"]
        cells = present.materials_text.movement_cells(row, self.columns(), self.labels)
        props = [
            present.layout.prop(name, cell)
            for name, cell in zip(self.columns(), cells, strict=True)
        ]
        props.append(present.layout.prop("Reason", row.reason))
        props.append(present.layout.prop("Person", row.person))
        page = present.layout.Page(
            identity=present.layout.identity_line(f"#{row.seq}", _kind_word(row)),
            sections=(present.layout.Section("", tuple(props)),),
        )
        return present.plain_lines(page)

    def actions_for(self, row: MovementView) -> Sequence[WebAction]:
        return []  # read only: a movement has no command

    def summary_text(self) -> str:
        return self._summary


register("movements", MovementWebLog)


@router.get("/p/{project}/movements")
def movement_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return MovementWebLog.page(request, project, q=q, sel=sel, mode=mode)
