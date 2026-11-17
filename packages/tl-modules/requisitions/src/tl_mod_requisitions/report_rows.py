"""The requisitions module's line-level reports (``tl report work-orders``, ``requisitions``).

Both page through the module's own list read as the viewer, with its ``offset``: ``work_order_list``
(a work order of a hidden requisition is not a row) and ``requisition_list`` (every kind merged by
key; V3-P0c). The lists take the module word ``requisitions.view``: each report checks it first with
the same ``require_word`` and refusal text as the API route. No record id is a column (the key names
the row). Hours are numbers (``Decimal``), not text.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.modules import Report

from tl_mod_requisitions import MODULE, views

#: The list word the work-order read checks (the API's ``requisitions.py`` ``VIEW_WORD``).
VIEW_WORD: Final = "requisitions.view"
#: The page size the list is read with (a monkeypatched value in the tests).
_PAGE: Final = 200
WORK_ORDER_COLUMNS: Final = (
    "key", "work_kind", "state", "assigned_to", "planned_start", "planned_finish",
    "actual_start", "actual_finish", "hours_planned", "hours_actual",
)  # fmt: skip
REQUISITION_COLUMNS: Final = (
    "key", "kind", "subject", "state", "requester", "priority", "need_by", "approved_by",
)  # fmt: skip


def _number(text: str | None) -> Decimal | None:
    """The stored hours (text) as a number; blank or not a number is no value."""
    if text is None or text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _check_view(conn: Connection, viewer: confidentiality.Viewer, scope: str) -> None:
    require_word(
        conn,
        holder_for_actor(conn, viewer.actor),
        scope=scope,
        module=MODULE,
        word=normalise_word(VIEW_WORD),
        what=VIEW_WORD,
    )


def work_order_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    _check_view(conn, viewer, scope)
    offset = 0
    while True:
        page = views.work_order_list(conn, scope, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page:
            yield {
                "key": row.key,
                "work_kind": row.work_kind,
                "state": row.state,
                "assigned_to": row.assigned_to,
                "planned_start": row.planned_start,
                "planned_finish": row.planned_finish,
                "actual_start": row.actual_start,
                "actual_finish": row.actual_finish,
                "hours_planned": _number(row.hours_planned),
                "hours_actual": _number(row.hours_actual),
            }
        offset += len(page)
        if len(page) < _PAGE:
            return


def requisition_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    _check_view(conn, viewer, scope)
    offset = 0
    while True:
        page = views.requisition_list(conn, scope, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page:
            yield {name: getattr(row, name) for name in REQUISITION_COLUMNS}
        offset += len(page)
        if len(page) < _PAGE:
            return


REPORTS: Final = (
    Report("requisitions", "Requisitions", REQUISITION_COLUMNS, requisition_rows),
    Report("work-orders", "Work orders", WORK_ORDER_COLUMNS, work_order_rows),
)
