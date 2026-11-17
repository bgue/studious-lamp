"""The awp module's list reports for ``tl report`` (V3-P0b): the CWP and IWP registers.

Each row is the list read's own row (``views.cwp_list``, ``iwp_views.iwp_list``), read as the
viewer, so a hidden or voided record is not a row. The CWP list has no limit and is read once; the
IWP list is paged with its ``offset`` (its ``limit`` is clamped to 500). Neither list has a view
word, so there is no refusal to copy. No record id is a column: the number names the row.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report

from tl_mod_awp import iwp_views, views

#: The page size the IWP list is read with (its clamp is 500; a monkeypatched value in the tests).
_PAGE: Final = 500
CWP_COLUMNS: Final = (
    "number", "title", "state", "discipline", "cwa", "planned_start", "planned_finish",
    "budget_hours", "allocated",
)  # fmt: skip
IWP_COLUMNS: Final = (
    "number", "title", "state", "discipline", "planned_start", "planned_finish", "foreman",
    "estimated_hours", "cwp_number", "scope_count",
)  # fmt: skip


def cwp_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    for row in views.cwp_list(conn, scope):
        yield {name: getattr(row, name) for name in CWP_COLUMNS}


def iwp_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    offset = 0
    while True:
        page = iwp_views.iwp_list(conn, scope, limit=_PAGE, offset=offset)
        for row in page:
            yield {name: getattr(row, name) for name in IWP_COLUMNS}
        offset += len(page)
        if len(page) < _PAGE:
            return


REPORTS: Final = (
    Report("cwps", "Construction work packages (CWPs)", CWP_COLUMNS, cwp_rows),
    Report("iwps", "Installation work packages (IWPs)", IWP_COLUMNS, iwp_rows),
)
