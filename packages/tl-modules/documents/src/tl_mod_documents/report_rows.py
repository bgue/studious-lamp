"""The documents module's line-level report (``tl report documents``; V3-P0): the register.

Reads through ``reports.document_register`` as the ambient viewer (``tl_core.report_out`` sets it),
so a document the viewer may not read is not a row. The register has no offset, so it is read in
one call with a bound far above any project's count. No internal id is a column.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report

from tl_mod_documents import reports

_BOUND: Final = 1_000_000
DOCUMENT_COLUMNS: Final = (
    "number", "state", "doc_type", "discipline", "current_revision", "current_status",
    "current_class", "current_issued_on", "revisions", "open_revision", "stale_links", "title",
)  # fmt: skip


def document_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    for line in reports.document_register(conn, scope, limit=_BOUND):
        yield {
            "number": line.number,
            "state": line.state,
            "doc_type": line.doc_type,
            "discipline": line.discipline,
            "current_revision": line.current_code,
            "current_status": line.current_status,
            "current_class": line.current_class,
            "current_issued_on": line.current_issued_on,
            "revisions": line.revisions,
            "open_revision": line.open_code,
            "stale_links": line.stale_links,
            "title": line.title,
        }


REPORTS: Final = (Report("documents", "Document register", DOCUMENT_COLUMNS, document_rows),)
