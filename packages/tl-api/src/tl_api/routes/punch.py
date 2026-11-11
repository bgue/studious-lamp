"""Reads of the quality module's punch list (P2-PUNCH-T03): the list, one item and the counts.

Thin: one call into ``tl_mod_quality.views`` per route, through the viewer's class filter (the
request's viewer, which the API middleware sets). Every route first checks the module word
``quality.view`` for the caller on the project, through ``guard`` (authentication and the agent
rules) and then ``require_word``, before any lookup. The reads take the request's viewer
(``current_viewer()``, set by the API middleware), not the views' LOWEST default. A hidden item
answers the same 404 as a key that does not exist; no total counts it. The writes are the module's
commands under ``POST /commands/<Name>``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality import MODULE
from tl_mod_quality import views as punch_views

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["punch"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
VIEW_WORD = "quality.view"
#: One text for a missing and a hidden item: the key is not echoed.
MSG_NOT_FOUND = "no punch item"
PUNCH_LIMIT = punch_views.MAX_LIMIT


def _view_reader(
    project: str,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("document.read"))],
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    """Authentication and the agent rules (``guard``), then the module word ``quality.view`` the
    caller holds on the project, before any read. A refusal is the API's 403 ``forbidden``."""
    with ctx.backend(False) as uow:
        require_word(
            uow.conn(),
            holder_for_principal(principal),
            scope=f"project:{project}",
            module=MODULE,
            word=normalise_word(VIEW_WORD),
            what=VIEW_WORD,
        )
    return actor


Reader = Annotated[str, Depends(_view_reader)]
Limit = Annotated[int, Query(ge=1, le=PUNCH_LIMIT, description="At most this many rows.")]


@router.get("/projects/{project}/punch", operation_id="list_punch_items")
def list_punch_items(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[
        Literal["Open", "Cleared", "Verified", "Void"] | None,
        Query(description="The workflow state."),
    ] = None,
    area: Annotated[str | None, Query(max_length=64, description="The area.")] = None,
    system: Annotated[str | None, Query(max_length=64, description="The system.")] = None,
    assignee: Annotated[str | None, Query(max_length=120, description="The assignee.")] = None,
    category: Annotated[Literal["A", "B", "C"] | None, Query(description="The category.")] = None,
    from_: Annotated[
        str | None,
        Query(
            alias="from", max_length=200, description="The key of the record it was raised from."
        ),
    ] = None,
    overdue: Annotated[bool, Query(description="Only Open items past their due day.")] = False,
    limit: Limit = 200,
) -> punch_views.PunchPage:
    """A project's punch items by key, filtered by state, area, system, assignee, category, the
    record they were raised from and overdue. ``total`` counts the visible matches. Hidden items
    are left out; an unknown or hidden ``from`` key gives an empty page."""
    with ctx.backend(True) as uow:
        return punch_views.punch_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            area=area,
            system=system,
            assignee=assignee,
            category=category,
            source_key=from_,
            overdue=overdue,
            today=date.today().isoformat(),
            limit=limit,
            viewer=current_viewer(),
        )


@router.get("/projects/{project}/punch/{key}", operation_id="get_punch_item")
def get_punch_item(ctx: Ctx, actor: Reader, project: str, key: str) -> punch_views.PunchDetail:
    """One punch item with its fields and its source. 404 `record_not_found` when it is missing
    or hidden (one answer for both)."""
    with ctx.backend(True) as uow:
        detail = punch_views.punch_detail(
            uow.conn(), f"project:{project}", key, viewer=current_viewer()
        )
        if detail is None:
            raise RecordNotFoundError(MSG_NOT_FOUND)
        return detail


@router.get("/projects/{project}/punch-counts", operation_id="get_punch_counts")
def get_punch_counts(ctx: Ctx, actor: Reader, project: str) -> dict[str, int]:
    """The visible punch items of a project by state: Open, Cleared, Verified and Void."""
    with ctx.backend(True) as uow:
        return punch_views.punch_counts(uow.conn(), f"project:{project}", viewer=current_viewer())
