"""The permits module's line-level reports (``tl report permits``, ``isolations``; V3-P0b).

Both page through the module's own list reads (``views.permit_list``, ``iso_views.isolation_list``)
as the viewer, with their ``offset``. Both take the module word ``permits.view``: the report checks
it first with the same ``require_word`` and refusal text the API's ``_view_reader`` gives. No
record id is a column; the key names the row.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.modules import Report
from tl_core.util import utcnow

from tl_mod_permits import MODULE, iso_views
from tl_mod_permits import views as permit_views

#: The list word both reads check (``routes.py``'s ``VIEW_WORD``).
VIEW_WORD: Final = "permits.view"
#: The page size the lists are read with (a monkeypatched value in the tests).
_PAGE: Final = 100
PERMIT_COLUMNS: Final = (
    "key", "subject", "permit_type", "state", "area", "holder", "issued_at", "valid_until",
    "revalidation_count", "closed_by", "for_key",
)  # fmt: skip
ISOLATION_COLUMNS: Final = (
    "key", "point_text", "energy", "method", "lock_number", "tag_number", "state", "applied_by",
    "applied_at", "verified_by", "verified_at", "depends",
)  # fmt: skip


def _check_view(conn: Connection, viewer: confidentiality.Viewer, scope: str) -> None:
    """The list read's own check (the API's ``_view_reader``): ``permits.view`` on the project."""
    require_word(
        conn,
        holder_for_actor(conn, viewer.actor),
        scope=scope,
        module=MODULE,
        word=normalise_word(VIEW_WORD),
        what=VIEW_WORD,
    )


def permit_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    _check_view(conn, viewer, scope)
    offset = 0
    while True:
        page = permit_views.permit_list(
            conn, scope, now=utcnow(), limit=_PAGE, offset=offset, viewer=viewer
        )
        for row in page.rows:
            yield {name: getattr(row, name) for name in PERMIT_COLUMNS}
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def isolation_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    _check_view(conn, viewer, scope)
    offset = 0
    while True:
        page = iso_views.isolation_list(conn, scope, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page.rows:
            yield {name: getattr(row, name) for name in ISOLATION_COLUMNS}
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


REPORTS: Final = (
    Report("permits", "Permits to work", PERMIT_COLUMNS, permit_rows),
    Report("isolations", "Isolations", ISOLATION_COLUMNS, isolation_rows),
)
