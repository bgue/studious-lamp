"""The file bytes and page 1 for a cookie session: mirrors of two JSON routes (P2-WEB1-S3).

Each handler checks ``file.read`` through the same ``guard`` and then calls the JSON route's own
function with the same context, file, scope and actor, so there is one visibility path (open the
file under the viewer, then everything else). An error the function raises is answered by the
application's handlers, so its status and JSON body pass through unchanged. No page, no template.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_api.routes import files as file_routes

router = APIRouter(prefix="/web", include_in_schema=False)
Ctx = Annotated[ApiContext, Depends(get_ctx)]


@router.get("/files/{file_id}/content")
def content(
    ctx: Ctx,
    file_id: str,
    scope: file_routes.ScopeParam,
    actor: Annotated[str, Depends(guard("file.read"))],
) -> Response:
    """The file's bytes as an attachment: ``GET /files/{file_id}/content``."""
    return file_routes.download_file(ctx, file_id, scope, actor)


@router.get("/files/{file_id}/page1.png")
def page1(
    ctx: Ctx,
    file_id: str,
    scope: file_routes.ScopeParam,
    actor: Annotated[str, Depends(guard("file.read"))],
) -> Response:
    """Page 1 as a PNG: ``GET /files/{file_id}/page1.png``."""
    return file_routes.get_file_page1(ctx, file_id, scope, actor)
