"""The path of construction page: ``GET /web/p/{project}/path`` (P2-WEB1-T16).

The path of construction of the terminal (``tl_tui.path_text``, the screen ``PathScreen``) in the
log standard of ``tl_web.log``: one version of the path (its steps: Number, Subject, Reason, CWPs,
Budget h) or its comparison with the version before it. Two query strings choose what is shown,
and a bad value means "absent": ``?version=N`` (ASCII digits, N >= 1; anything else is the current
version) and ``?compare=1`` (the comparison, when there is an earlier version to compare with). The
columns, cells, panel and summary come from ``tl_web.present.path_text``. No actions are offered on
this page in I1; the versions are reached by their URL and listed in the panel.

Case (f) of the twin recipe does not apply: the panel reads nothing of its own (it is the page's
``load_rows`` that reads, and the panel route runs the same ``load_rows``), so there is no panel
read that could fail on a listed row. An unknown number is the one 404 page.
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

    from tl_mod_awp.views import CwaRow, CwpRow, PathVersion, PathView

    from tl_web.log import WebAction

router = web_router()

PathRow = present.path_text.PathLine | present.path_text.Moved
NO_EARLIER = "No earlier version"
COMPARE = "1"


def _version(request: Request) -> int | None:
    """``?version=N`` for N >= 1 (ASCII digits only, at most nine); anything else is absent: the
    current one."""
    raw = request.query_params.get("version", "")
    if raw.isascii() and raw.isdigit() and len(raw) <= 9 and int(raw) >= 1:
        return int(raw)
    return None


def _is_not_found(exc: Exception) -> bool:
    """True when ``exc`` is the terminal's ``record_not_found`` (the path or version is not
    held)."""
    mapped = body_for(exc)
    return mapped is not None and mapped[1].error == "record_not_found"


class PathWebLog(WebLog["present.path_text.PathLine | present.path_text.Moved"]):
    LOG_NAME = "Path of construction"
    LABEL_TYPES = ("awp.CWP",)

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        super().__init__(request, project, technical=technical)
        self.wanted: int | None = None  # the version asked for; None is the current one
        self.compare_asked = False  # ``?compare=1``
        self.comparing = False  # the rows are a comparison (asked, and there is an earlier version)
        self.view: PathView | None = None  # the version shown, as read
        self.previous: PathView | None = None  # the version before it, when it is held
        self.versions: list[PathVersion] = []
        self.cwas: list[CwaRow] = []  # the names of the steps
        self.cwps: list[CwpRow] = []  # the counts and budgets of the steps
        self._ids: dict[str, str] = {}  # CWA code -> CWA id, from the listing
        self._count = 0  # the rows, as load_rows made them

    def columns(self) -> tuple[str, ...]:
        if self.comparing:
            return present.path_text.COMPARE_COLUMNS
        return present.path_text.PATH_COLUMNS

    def load_rows(self) -> Sequence[PathRow]:
        self.wanted = _version(self.request)
        self.compare_asked = self.request.query_params.get("compare") == COMPARE
        view = self._read_view()
        self.view = view
        self.previous = None if view is None else self._earlier(view)
        self.versions = list(self.client.list_path_versions(self.project))
        self.cwas = list(self.client.list_cwas(self.project))
        self.cwps = list(self.client.list_cwps(self.project))
        self._ids = {area.code: area.id for area in self.cwas}
        self.comparing = self.compare_asked and self.previous is not None
        rows = self._rows()
        self._count = len(rows)
        return rows

    def _read_view(self) -> PathView | None:
        """The version asked for. Only an absent ``?version=`` may find no path (a project with no
        path yet); a version that is not held is the one 404 page, so it is not caught here."""
        try:
            return self.client.get_path(self.project, version=self.wanted)
        except Exception as exc:
            if self.wanted is not None or not _is_not_found(exc):
                raise
            return None

    def _earlier(self, view: PathView) -> PathView | None:
        """The version before ``view``; none for version 1 or when that version is not held."""
        if view.version <= 1:
            return None
        try:
            return self.client.get_path(self.project, version=view.version - 1)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise

    def _rows(self) -> list[PathRow]:
        if self.view is None:
            return []
        if self.comparing and self.previous is not None:
            return list(present.path_text.compare_versions(self.previous, self.view))
        return list(present.path_text.path_lines(self.view, self.cwas, self.cwps))

    def row_key(self, row: PathRow) -> str:
        """The id of the CWA the row names (so Open leads to the area's record); else the number."""
        code = row.cwa if isinstance(row, present.path_text.Moved) else row.step.cwa
        if code is not None and code in self._ids:
            return self._ids[code]
        return self.row_record(row)[0]

    def row_record(self, row: PathRow) -> tuple[str, str]:
        if isinstance(row, present.path_text.Moved):
            code = row.cwa or present.text.EMPTY
            return (code, code)
        return (str(row.step.position), present.path_text.path_cells(row)[1])

    def row_cells(self, row: PathRow) -> tuple[str, ...]:
        if isinstance(row, present.path_text.Moved):
            return present.path_text.compare_cells(row)
        return present.path_text.path_cells(row, self.labels)

    def panel_page(self, row: PathRow) -> present.Page:
        if self.view is None:
            return present.layout.Page(sections=(present.layout.Section("", note="Nothing here."),))
        return present.path_text.path_page(
            self.view,
            self.versions,
            self._line_of(row),
            previous=self.previous,
            labels=self.labels,
            panel=True,
        )

    def _line_of(self, row: PathRow) -> present.path_text.PathLine | None:
        """The step the row is, or the step of the CWA a comparison row names (None when none)."""
        if isinstance(row, present.path_text.PathLine):
            return row
        if self.view is None:
            return None
        return next(
            (
                line
                for line in present.path_text.path_lines(self.view, self.cwas, self.cwps)
                if line.step.cwa == row.cwa
            ),
            None,
        )

    def _panel_url(self, number: str) -> str:
        """The panel of the row, of the same version and mode as this page."""
        base = super()._panel_url(number)
        if self.view is None:
            return base
        extra = f"version={self.view.version}" + ("&compare=1" if self.comparing else "")
        return f"{base}{'&' if '?' in base else '?'}{extra}"

    def actions_for(self, row: PathRow) -> Sequence[WebAction]:
        return []  # no actions in I1; the path writes come with P2-I2

    def summary_text(self) -> str:
        if self.view is None:
            return ""
        if self.compare_asked and self.previous is None:
            return NO_EARLIER
        count = self._count
        if self.comparing and self.previous is not None:
            return present.layout.join_facts(
                f"{count} row{'s' if count != 1 else ''}",
                f"against version {self.previous.version}",
            )
        return present.layout.join_facts(
            f"{count} step{'s' if count != 1 else ''}", f"version {self.view.version}"
        )


register("path", PathWebLog)


@router.get("/p/{project}/path")
def path_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return PathWebLog.page(request, project, q=q, sel=sel, mode=mode)
