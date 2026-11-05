"""The external packages page: ``GET /web/p/{project}/packages`` (P2-WEB1-T11).

The package log of the terminal (``tl_tui.package_text``, P2-I1 T05f) in the log standard of
``tl_web.log``: the columns, cells, panel and summary come from ``tl_web.present``. ``?kind=EWP``
or ``?kind=PWP`` keeps one kind; ``?constraints=1`` keeps the constraint sources only. A bad value
means "absent". The panel reads nothing of its own: it is the row's own values. No actions are
offered on this page (no awp command has an ``ACTION_UI`` row).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_awp.views import PackageRow

    from tl_web.log import WebAction

router = web_router()

KINDS = ("EWP", "PWP")


def _kind(value: str) -> str | None:
    return value if value in KINDS else None


class PackageWebLog(WebLog["PackageRow"]):
    LOG_NAME = "Packages"
    _summary = ""

    def columns(self) -> tuple[str, ...]:
        return present.package_text.PACKAGE_COLUMNS

    def load_rows(self) -> list[PackageRow]:
        everything = self.client.list_packages(self.project)
        kind = _kind(self.request.query_params.get("kind", ""))
        constraints_only = self.request.query_params.get("constraints", "") == "1"
        rows = [
            row
            for row in everything
            if (kind is None or row.kind == kind)
            and (not constraints_only or row.constraint_source)
        ]
        self._summary = present.package_text.summary_line(
            len(rows),
            len(everything),
            kind=kind,
            constraints_only=constraints_only,
            text="",
        )
        return rows

    def row_key(self, row: PackageRow) -> str:
        return row.id

    def row_record(self, row: PackageRow) -> tuple[str, str]:
        return (row.package_no, row.title)

    def row_cells(self, row: PackageRow) -> tuple[str, ...]:
        return present.package_text.package_cells(row)

    def panel_page(self, row: PackageRow) -> present.Page:
        return present.package_text.package_page(row, panel=True, technical=self.technical)

    def actions_for(self, row: PackageRow) -> Sequence[WebAction]:
        return []  # no awp command has an ACTION_UI row (writes come with P2-I2)

    def summary_text(self) -> str:
        return self._summary


register("packages", PackageWebLog)


@router.get("/p/{project}/packages")
def package_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return PackageWebLog.page(request, project, q=q, sel=sel, mode=mode)
