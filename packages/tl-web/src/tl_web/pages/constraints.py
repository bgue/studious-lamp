"""The constraint log on the web: ``GET /web/p/{project}/constraints`` (P2-I2-TW2).

The constraint review of the terminal (``ConstraintScreen``), in the log standard of ``tl_web.log``:
the columns, cells, summary and panel come from ``tl_web.present`` (the terminal's own functions,
``tl_tui.constraint_text``). ``?subject=<key>`` keeps one subject's constraints, as
``ConstraintScreen(client, project, subject_key)`` does. The rows are one ``list_constraints`` read
(up to ``MAX_LIMIT``) held in memory; no review-group read is made. The group keys (``o t a s b``)
are not on this page yet. No actions are offered on this page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_api.routes.constraints import ConstraintRow

    from tl_web.log import WebAction

router = web_router()

BLOCKING = "blocking"  # the severity word the terminal's summary counts
# the terminal's read limit, tl_core.constraints.queries.MAX_LIMIT (pinned by a test)
MAX_ROWS = 500


class ConstraintWebLog(WebLog["ConstraintRow"]):
    LOG_NAME = "Constraints"
    LABEL_TYPES = ()  # the constraint cells take no code list (``constraint_cells``)
    _summary = ""

    def columns(self) -> Sequence[str]:
        return present.constraint_text.CONSTRAINT_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return present.constraint_text.CONSTRAINT_DROP

    def subject(self) -> str | None:
        """The subject key of ``?subject=``, or ``None`` for the whole project's constraints."""
        return self.request.query_params.get("subject", "").strip() or None

    def load_rows(self) -> list[ConstraintRow]:
        subject = self.subject()
        found = self.client.list_constraints(self.project, subject=subject, limit=MAX_ROWS)
        rows = list(found.rows)
        blocking = sum(1 for row in rows if row.severity == BLOCKING)
        aging = sum(1 for row in rows if row.aging)
        text = present.constraint_text.constraint_summary(
            found.total,
            len(rows),
            blocking=blocking,
            aging=aging,
            truncated=found.total > len(rows),
        )
        self._summary = f"Constraints on {subject} · {text}" if subject is not None else text
        return rows

    def row_key(self, row: ConstraintRow) -> str:
        return row.id

    def row_record(self, row: ConstraintRow) -> tuple[str, str]:
        return (row.key, row.description or row.subject_key)

    def row_cells(self, row: ConstraintRow) -> Sequence[str]:
        return present.constraint_text.constraint_cells(row)

    def panel_page(self, row: ConstraintRow) -> present.Page:
        full = self.client.get_constraint(self.project, row.key)
        return present.constraint_text.constraint_page(full, technical=self.technical, panel=True)

    def actions_for(self, row: ConstraintRow) -> Sequence[WebAction]:
        return []  # no constraint action is in this increment (the writes come later)

    def summary_text(self) -> str:
        return self._summary


register("constraints", ConstraintWebLog)


@router.get("/p/{project}/constraints")
def constraint_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return ConstraintWebLog.page(request, project, q=q, sel=sel, mode=mode)
