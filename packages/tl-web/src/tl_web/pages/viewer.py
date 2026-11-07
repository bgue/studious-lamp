"""The full PDF viewer page: ``GET /web/p/{project}/files/{file_id}/view`` (P2-WEB1-T05).

The page reads the file's metadata through ``WebReadClient.file_info`` (``file.read``; a hidden or
unknown file raises the route's 404, which ``web_router`` answers with the one 404 page). A PDF of
at most ``MAX_VIEW_BYTES`` gets the pdf.js viewer; anything else gets the filename and a download
link only. The page holds no business logic: ``pdfview.js`` reads its data attributes.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Request, Response
from tl_api.auth import PRINCIPAL_KEY
from tl_core.auth.types import Principal

from tl_web.app import PROJECT_ID, render
from tl_web.reads import WebReadClient
from tl_web.webroute import not_found_page, web_router

router = web_router()

MAX_VIEW_BYTES = 50 * 1024 * 1024
WORKER_URL = "/web/static/vendor/pdfjs/pdf.worker.min.mjs"


def is_pdf(content_type: str, filename: str) -> bool:
    """A PDF by its declared type or by its ``.pdf`` name (case-insensitive)."""
    return content_type == "application/pdf" or filename.lower().endswith(".pdf")


@router.get("/p/{project}/files/{file_id}/view")
def viewer(request: Request, project: str, file_id: str) -> Response:
    """The file in full with pdf.js, or the filename and a download link when it cannot be drawn."""
    if not PROJECT_ID.fullmatch(project):
        return not_found_page(request)
    principal: Principal = request.scope[PRINCIPAL_KEY]
    client = WebReadClient(request.app.state.ctx, principal, path=request.url.path)
    scope = f"project:{project}"
    info = client.file_info(scope, file_id)
    download_url = f"/web/files/{file_id}/content?scope={quote(scope, safe='')}"
    viewable = is_pdf(info.content_type, info.filename) and info.size <= MAX_VIEW_BYTES
    return render(
        request,
        "viewer.html",
        filename=info.filename,
        viewable=viewable,
        download_url=download_url,
        worker_url=WORKER_URL,
    )
