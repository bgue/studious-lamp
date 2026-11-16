"""The read route of the ext_demo module (ADR-0029): one note, through the viewer's class filter.

A route that returns record text reads through the viewer's class filter
(`tl_core.confidentiality`), and a hidden record answers as a missing one: the same 404 and the
same text.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError

from . import MSG_NOT_FOUND
from .views import NoteView, get_note

router = APIRouter(tags=["ext_demo"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]


@router.get("/modules/ext_demo/notes/{key}")
def read_note(
    key: str,
    ctx: Ctx,
    scope: Annotated[str, Query(description="The project scope, `project:<id>`.")],
    _actor: Annotated[str, Depends(guard("document.read"))],
) -> NoteView:
    """One note. `document.read` is the read word agents hold; the route is a read."""
    with ctx.backend(True) as uow:
        found = get_note(uow.conn(), scope, key, viewer=current_viewer())
    if found is None:
        raise RecordNotFoundError(MSG_NOT_FOUND)
    return found
