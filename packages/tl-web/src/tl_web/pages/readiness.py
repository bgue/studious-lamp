"""The readiness of one IWP on the web: ``GET /web/p/{project}/readiness?number=<IWP number>``
(P2-I2-TW3; the terminal's ``ReadinessScreen``).

One row per check (one per reference of a check), the summary, and the panel's page. The columns,
rows, summary, panel and the one "not evaluated" text come from ``tl_web.present`` (the terminal's
``tl_tui.readiness_text``). A reference is shown as text: the web has no Enter-to-open, and no
action is offered. A missing, hidden or unknown IWP answers the one 404 page; an IWP the reader may
see but that was never evaluated answers the "not evaluated" line, as the terminal does.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from fastapi import Request, Response
from tl_api.errors import body_for

from tl_web import present
from tl_web.app import PROJECT_ID
from tl_web.log import WebLog, register
from tl_web.webroute import not_found_page, web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_api.routes.awp import ReadinessBody

    from tl_web.log import WebAction

router = web_router()

RECORD_NOT_FOUND = "record_not_found"
DETAIL_COLUMN = present.readiness_text.READINESS_COLUMNS.index("Detail")
DETAIL_SECTION = "Detail"


@dataclass(frozen=True)
class CheckRow:
    """One row of the checks table: its place, its cells, and the reference it names, if any."""

    position: int
    cells: tuple[str, ...]
    record_id: str | None


def _not_found(exc: Exception) -> bool:
    """True for the table's ``record_not_found`` (the route's answer for a missing or hidden IWP,
    and for one that was never evaluated)."""
    mapped = body_for(exc)
    return mapped is not None and mapped[1].error == RECORD_NOT_FOUND


class ReadinessWebLog(WebLog[CheckRow]):
    LOG_NAME = "Readiness"
    number: str = ""  # the IWP number: the page's query, or the panel route's path
    view: ReadinessBody | None = None  # the last read; None when not evaluated

    def columns(self) -> Sequence[str]:
        return present.readiness_text.READINESS_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return present.readiness_text.READINESS_DROP

    def load_rows(self) -> Sequence[CheckRow]:
        self.view = None
        try:
            view = self.client.get_iwp_readiness(self.project, self.number)
        except Exception as exc:
            if not _not_found(exc):
                raise
            # Not evaluated, or missing or hidden: the read of the IWP itself tells them apart
            # (it answers the 404 page for a missing or hidden one, and raises out of here).
            self.client.get_iwp(self.project, self.number)
            return []
        self.view = view
        checks = present.readiness_text.readiness_rows(view)
        return [CheckRow(i, tuple(cells), rid) for i, (cells, rid) in enumerate(checks)]

    def row_key(self, row: CheckRow) -> str:
        return str(row.position)

    def row_open_key(self, row: CheckRow) -> str | None:
        return None  # no Enter-to-open on the web: a reference is text

    def row_cells(self, row: CheckRow) -> Sequence[str]:
        return row.cells

    def row_record(self, row: CheckRow) -> tuple[str, str]:
        return (self.number, "")

    def row_for(self, number: str) -> CheckRow | None:
        self.number = number  # the panel route has no query: its path is the IWP number
        return super().row_for(number)

    def panel_page(self, row: CheckRow | None) -> present.Page | None:
        """The IWP's readiness page; on a check with no reference, that check's detail too."""
        if self.view is None or row is None:
            return None
        page = present.readiness_text.readiness_page(
            self.number, self.view, technical=self.technical, panel=True
        )
        if row.record_id is None:
            detail = row.cells[DETAIL_COLUMN]
            section = present.layout.Section(DETAIL_SECTION, (detail,))
            page = replace(page, sections=(*page.sections, section))
        return page

    def actions_for(self, row: CheckRow) -> Sequence[WebAction]:
        return []  # no action on a readiness check: the release command is the writes' home

    def summary_text(self) -> str:
        if self.view is None:
            return present.readiness_text.not_evaluated_text(self.number)
        return present.readiness_text.readiness_summary(self.view)

    @classmethod
    def page_for(
        cls, request: Request, project: str, number: str, *, q: str, sel: str, mode: str
    ) -> Response:
        """The readiness page of IWP ``number``; no number, or a project id that is not one, is the
        one 404 page."""
        if not number or not PROJECT_ID.fullmatch(project):
            return not_found_page(request)
        log, notice = cls.for_request(request, project, mode)
        log.number = number
        return log._render_page(q, sel, notice)


register("readiness", ReadinessWebLog)


@router.get("/p/{project}/readiness")
def readiness_page(
    request: Request,
    project: str,
    number: str = "",
    q: str = "",
    sel: str = "",
    mode: str = "",
) -> Response:
    return ReadinessWebLog.page_for(request, project, number, q=q, sel=sel, mode=mode)
