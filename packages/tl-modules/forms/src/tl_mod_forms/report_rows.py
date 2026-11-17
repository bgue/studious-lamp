"""The forms module's line-level reports (``tl report``; V3-P0): submissions and templates.

Both page through the module's own list views (``views.submission_list``, ``views.template_list``)
read as the viewer, so a hidden record is not a row and not in any count. No internal id is a
column: a submission names its template by title and its subject by key.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection, bindparam, text
from tl_core import confidentiality
from tl_core.modules import Report

from tl_mod_forms import views

_PAGE: Final = 100
SUBMISSION_COLUMNS: Final = (
    "key", "state", "template", "template_version", "subject", "answer_class", "author",
    "submitted_on", "reviewed_by", "reviewed_on",
)  # fmt: skip
TEMPLATE_COLUMNS: Final = (
    "key", "title", "version", "state", "intake", "purpose", "answer_class", "bound_record_type",
    "field_count", "published_on", "retired_on",
)  # fmt: skip


def _templates(conn: Connection, viewer: confidentiality.Viewer) -> dict[str, str]:
    """Template id to title, for the templates the viewer may read."""
    titles: dict[str, str] = {}
    offset = 0
    while True:
        page = views.template_list(conn, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page.rows:
            titles[row.id] = row.title or row.key or ""
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return titles


def _subject_keys(
    conn: Connection, ids: list[str], viewer: confidentiality.Viewer
) -> dict[str, str]:
    """Record id to key for the subjects among ``ids`` the viewer may read."""
    if not ids:
        return {}
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    stmt = text(f"SELECT r.id, r.key FROM cur_core_record r WHERE r.id IN :ids AND {visible}")
    stmt = stmt.bindparams(bindparam("ids", expanding=True))
    return {str(r.id): str(r.key) for r in conn.execute(stmt, {"ids": ids, **extra}) if r.key}


def submission_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    titles = _templates(conn, viewer)
    offset = 0
    while True:
        page = views.submission_list(conn, scope, limit=_PAGE, offset=offset, viewer=viewer)
        subjects = _subject_keys(
            conn, [r.subject_id for r in page.rows if r.subject_id is not None], viewer
        )
        for row in page.rows:
            yield {
                "key": row.key,
                "state": row.state,
                "template": titles.get(row.template_id or ""),
                "template_version": row.template_version,
                "subject": subjects.get(row.subject_id or ""),
                "answer_class": row.answer_class,
                "author": row.author,
                "submitted_on": row.submitted_on,
                "reviewed_by": row.reviewed_by,
                "reviewed_on": row.reviewed_on,
            }
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def template_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    offset = 0
    while True:
        page = views.template_list(conn, limit=_PAGE, offset=offset, viewer=viewer)
        for row in page.rows:
            yield {name: getattr(row, name) for name in TEMPLATE_COLUMNS}
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


REPORTS: Final = (
    Report("form-submissions", "Form submissions", SUBMISSION_COLUMNS, submission_rows),
    Report("form-templates", "Form templates (company-wide)", TEMPLATE_COLUMNS, template_rows),
)
