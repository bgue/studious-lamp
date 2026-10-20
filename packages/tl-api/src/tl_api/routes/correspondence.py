"""Reads of the correspondence module: the register, items, threads, clocks, parties (P1-I5).

Thin, like the other read routes: one call into ``tl_mod_correspondence.views`` per route. Writes
are the module's commands (``POST /commands/ReceiveCorrespondence`` and the rest;
``tl_mod_correspondence.commands``, with their access levels). Every read needs the action
``correspondence.read``, which is open to agents because they only read.

**Who sees what is ADR-0016, not a route rule.** The API sets the viewer from the principal for
the whole request (``AuthenticationMiddleware``), and the module's registry filters every read by
it: an item the person may not read is not in a list and is a 404 ``correspondence_not_found``
(the same text as an item that does not exist). An agent reads ``internal`` items only.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from tl_mod_correspondence import views

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["correspondence"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("correspondence.read"))]
Direction = Literal["in", "out", "internal"]


@router.get("/projects/{project}/correspondence", operation_id="list_correspondence")
def list_correspondence(
    ctx: Ctx,
    actor: Reader,
    project: str,
    state: Annotated[str | None, Query(description="For example Received.")] = None,
    direction: Annotated[Direction | None, Query()] = None,
    domain: Annotated[str | None, Query(max_length=64)] = None,
    subtype: Annotated[str | None, Query(max_length=64)] = None,
    awaiting_response: Annotated[bool, Query(description="Items that want an answer.")] = False,
    include_void: Annotated[bool, Query(description="Include void items.")] = False,
    sources: Annotated[bool, Query(description="Add the lines of register sources.")] = True,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> list[views.RegisterLineView]:
    """The master register of a project: items plus the lines of the domains' register sources
    (the I2 transmittals as Document-control items). Newest first."""
    with ctx.backend(True) as uow:
        return views.register(
            uow.conn(),
            f"project:{project}",
            state=state,
            direction=direction,
            domain=domain,
            subtype=subtype,
            awaiting_response=awaiting_response,
            include_void=include_void,
            include_sources=sources,
            limit=limit,
            offset=offset,
        )


@router.get("/projects/{project}/correspondence/{number}", operation_id="get_correspondence")
def get_correspondence(ctx: Ctx, actor: Reader, project: str, number: str) -> views.ItemView:
    """One item with its clocks (and the accounts named on it if it is privileged).
    404 `correspondence_not_found` for an unknown item and for one the person may not read."""
    with ctx.backend(True) as uow:
        return views.item_view(uow.conn(), f"project:{project}", number)


@router.get(
    "/projects/{project}/correspondence/{number}/suggestion",
    operation_id="get_correspondence_suggestion",
)
def get_suggestion(ctx: Ctx, actor: Reader, project: str, number: str) -> views.SuggestionView:
    """The domain and subtype the suggestion engine proposes for an item. Only a proposal: a
    person confirms it (`ConfirmTriage`)."""
    with ctx.backend(True) as uow:
        return views.suggestion_for_item(uow.conn(), f"project:{project}", number)


@router.get("/projects/{project}/correspondence-threads", operation_id="list_threads")
def list_threads(
    ctx: Ctx, actor: Reader, project: str, state: Annotated[str | None, Query()] = None
) -> list[views.ThreadView]:
    """A project's threads, newest first, without items."""
    with ctx.backend(True) as uow:
        return views.thread_views(uow.conn(), f"project:{project}", state=state)


@router.get("/projects/{project}/correspondence-threads/{number}", operation_id="get_thread")
def get_thread(ctx: Ctx, actor: Reader, project: str, number: str) -> views.ThreadView:
    """One thread with the items the person may read. 404 `thread_not_found`."""
    with ctx.backend(True) as uow:
        return views.thread_view(uow.conn(), f"project:{project}", number)


@router.get("/projects/{project}/clocks", operation_id="list_clocks")
def list_clocks(
    ctx: Ctx,
    actor: Reader,
    project: str,
    open_only: Annotated[bool, Query(description="Only clocks still counting.")] = True,
    overdue_only: Annotated[bool, Query(description="Only clocks past their due date.")] = False,
    due_to: Annotated[date | None, Query(description="Due on or before this day.")] = None,
) -> list[views.ClockView]:
    """Response clocks, soonest due first, with days left as of today (the server's date)."""
    with ctx.backend(True) as uow:
        return views.clock_views(
            uow.conn(),
            f"project:{project}",
            open_only=open_only,
            overdue_only=overdue_only,
            due_to=due_to.isoformat() if due_to else None,
        )


@router.get("/projects/{project}/clocks/{clock_id}", operation_id="get_clock")
def get_clock(ctx: Ctx, actor: Reader, project: str, clock_id: str) -> views.ClockView:
    """One clock. 404 `correspondence_not_found` for an unknown clock and for one on an item the
    person may not read."""
    with ctx.backend(True) as uow:
        return views.clock_view_by_id(uow.conn(), f"project:{project}", clock_id)


@router.get("/projects/{project}/parties", operation_id="list_parties")
def list_parties(
    ctx: Ctx,
    actor: Reader,
    project: str,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[views.PartyView]:
    """A project's parties with their contacts, by code."""
    with ctx.backend(True) as uow:
        return views.party_views(
            uow.conn(), f"project:{project}", include_inactive=include_inactive
        )


@router.get("/projects/{project}/parties/{code}", operation_id="get_party")
def get_party(ctx: Ctx, actor: Reader, project: str, code: str) -> views.PartyView:
    """One party with its contacts. 404 `party_not_found`."""
    with ctx.backend(True) as uow:
        return views.party_view(uow.conn(), f"project:{project}", code)


@router.get("/projects/{project}/clauses", operation_id="list_clauses")
def list_clauses(
    ctx: Ctx,
    actor: Reader,
    project: str,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[views.ClauseView]:
    """A project's contract clauses."""
    with ctx.backend(True) as uow:
        return views.clause_views(
            uow.conn(), f"project:{project}", include_inactive=include_inactive
        )


@router.get(
    "/projects/{project}/correspondence-domains", operation_id="list_correspondence_domains"
)
def list_domains(ctx: Ctx, actor: Reader, project: str) -> list[views.DomainView]:
    """The domain definitions in force for a project: subtypes and the templates."""
    del ctx
    return views.domain_views(f"project:{project}")


@router.get("/projects/{project}/correspondence-suggestion", operation_id="suggest_domain")
def suggest_domain(
    ctx: Ctx,
    actor: Reader,
    project: str,
    subject: Annotated[str, Query(min_length=1, max_length=500)],
    body: Annotated[str | None, Query(max_length=4000)] = None,
) -> views.SuggestionView:
    """The domain and subtype the engine proposes for a text (a read; nothing is recorded)."""
    del ctx
    return views.suggestion_for_text(f"project:{project}", subject, body)
