"""The scaffold module's line-level report (``tl report scaffolds``; V3-P0).

Needs ``scaffold.view`` like the list read (same refusal). Pages through ``views.scaffold_list``
read as the viewer, so a hidden scaffold is not a row. The
columns are the existing export's (``views.EXPORT_COLUMNS``: no record id).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.modules import Report

from tl_mod_scaffold import MODULE, views
from tl_mod_scaffold.names import VIEW


def scaffold_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    # The list read's own check (API route and TUI): scaffold.view on the project, same text.
    require_word(
        conn,
        holder_for_actor(conn, viewer.actor),
        scope=scope,
        module=MODULE,
        word=normalise_word(VIEW),
        what=VIEW,
    )
    offset = 0
    while True:
        page = views.scaffold_list(conn, scope, limit=views.MAX_LIMIT, offset=offset, viewer=viewer)
        for row in page.rows:
            yield {name: getattr(row, name) for name in views.EXPORT_COLUMNS}
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


REPORTS: Final = (Report("scaffolds", "Scaffolds", views.EXPORT_COLUMNS, scaffold_rows),)
