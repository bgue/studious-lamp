"""The quality module's line-level reports (``tl report punch``, ``inspections``; V3-P0b).

Both page through the module's own list reads (``views.punch_list``, ``insp_views.inspection_list``)
as the viewer, with the list's ``offset``. Both lists take the module word ``quality.view``, so the
report checks it first with the same ``require_word`` and the same refusal text the API route
gives (a viewer without it gets the refusal and no header). No record id is a column.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.modules import Report

from tl_mod_quality import MODULE, insp_views, views

#: The list word both reads check (the API's ``punch.py`` and ``insp.py`` routes).
VIEW_WORD: Final = "quality.view"
#: The page size the lists are read with (a monkeypatched value in the tests).
_PAGE: Final = 200
PUNCH_COLUMNS: Final = (
    "key", "subject", "state", "category", "area", "system", "due_on", "assignee", "raised_by",
    "source_key",
)  # fmt: skip
INSPECTION_COLUMNS: Final = (
    "key", "title", "subject_key", "for_key", "state", "point", "area", "planned_on",
    "scheduled_for", "inspector", "result", "done_on", "punch_count",
)  # fmt: skip


def _check_view(conn: Connection, viewer: confidentiality.Viewer, scope: str) -> None:
    """The list read's own check (the API route and the TUI): ``quality.view`` on the project."""
    require_word(
        conn,
        holder_for_actor(conn, viewer.actor),
        scope=scope,
        module=MODULE,
        word=normalise_word(VIEW_WORD),
        what=VIEW_WORD,
    )


def punch_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    _check_view(conn, viewer, scope)
    offset = 0
    while True:
        page = views.punch_list(conn, scope, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page.rows:
            yield {name: getattr(row, name) for name in PUNCH_COLUMNS}
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def inspection_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    _check_view(conn, viewer, scope)
    offset = 0
    while True:
        page = insp_views.inspection_list(conn, scope, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page.rows:
            yield {name: getattr(row, name) for name in INSPECTION_COLUMNS}
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


REPORTS: Final = (
    Report("punch", "Punch list", PUNCH_COLUMNS, punch_rows),
    Report("inspections", "Inspections", INSPECTION_COLUMNS, inspection_rows),
)
