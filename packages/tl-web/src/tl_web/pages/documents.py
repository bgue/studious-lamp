"""The document register on the web: ``GET /web/p/{project}/documents`` (P2-WEB1-T02).

The document log of the terminal, in the log standard of ``tl_web.log``: the columns, cells, panel
and summary come from ``tl_web.present`` (the terminal's own functions). The panel shows page 1 of
the current revision's PDF at the top, then the text lines and the files of that revision. No
actions are offered on this page in i1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import Request, Response

from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tl_mod_documents.views import DocumentView

    from tl_web.log import WebAction

router = web_router()


def _is_pdf(info: Any) -> bool:
    return info.content_type == "application/pdf" or info.filename.lower().endswith(".pdf")


class DocumentWebLog(WebLog["DocumentView"]):
    LOG_NAME = "Documents"
    LABEL_TYPES = ("documents.Document",)
    _summary = ""

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        super().__init__(request, project, technical=technical)
        self._read_cache: dict[str, tuple[Any, Any]] = {}

    def columns(self) -> tuple[str, ...]:
        return present.document_text.COLUMNS

    def drop_order(self) -> tuple[str, ...]:
        return present.document_text.DROP

    def load_rows(self) -> list[DocumentView]:
        rows = self.client.list_documents(self.project, limit=500)
        self._summary = present.document_text.summary_line(
            len(rows),
            len(rows),
            state=None,
            doc_type=None,
            include_void=False,
            text="",
            labels=self.labels,
        )
        return rows

    def row_key(self, row: DocumentView) -> str:
        return row.id

    def row_record(self, row: DocumentView) -> tuple[str, str]:
        return (row.number, row.title)

    def row_cells(self, row: DocumentView) -> tuple[str, ...]:
        return present.document_text.row_cells(row, self.labels, technical=self.technical)

    def panel_text(self, row: DocumentView | None) -> list[str]:
        if row is None:
            return ["Nothing here."]
        full, files = self._read(row)
        lines = present.document_text.detail_lines(full, self.labels, technical=self.technical)
        if not files:
            return lines
        listed = [present.file_text.file_line(f.filename, f.content_type, f.size) for f in files]
        return [*lines, "", "Files", *listed]

    def panel_image(self, row: DocumentView) -> str:
        _, files = self._read(row)
        for info in files:
            if _is_pdf(info):
                return f"/web/files/{info.file_id}/page1.png?scope={quote(info.scope, safe='')}"
        return ""

    def actions_for(self, row: DocumentView) -> Sequence[WebAction]:
        return []  # the document commands have no ACTION_UI row (the terminal builds them itself)

    def summary_text(self) -> str:
        return self._summary

    def _read(self, row: DocumentView) -> tuple[Any, Any]:
        """The document in full and the files of its file revision, read once per request."""
        cached = self._read_cache.get(row.number)
        if cached is not None:
            return cached
        full = self.client.get_document(self.project, row.number)
        rev = present.document_text.file_revision(full)
        files = self.client.list_record_files(rev.id) if rev is not None else []
        self._read_cache[row.number] = (full, files)
        return full, files


register("documents", DocumentWebLog)


@router.get("/p/{project}/documents")
def document_log(
    request: Request, project: str, q: str = "", sel: str = "", mode: str = ""
) -> Response:
    return DocumentWebLog.page(request, project, q=q, sel=sel, mode=mode)
