"""The scan page: ``GET /web/q`` (a form), ``GET /web/q/{code}`` (the card), ``POST /web/q``.

A signed-out visitor never reaches these handlers: the authentication middleware bounces every
``GET`` under ``/web/`` to the sign-in page before any route runs, so no lookup and no statement
happens for a signed-out request (``tl_web.app`` adds the ``next`` of a well-formed scan path to
that bounce). A signed-in request first passes the miss counter (a limited session or address gets
the one 429 whether the code is a hit or not), then the resolver as the request's viewer. Every
miss is the web client's one 404 page. The code is never logged, never put in a query string and
never kept by the counter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from tl_api.auth import TOKEN_KEY, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.ratelimit import client_key
from tl_core.confidentiality import current_viewer
from tl_mod_qr.codes import normalise_code
from tl_mod_qr.resolve import resolve

from tl_web import csrf, scan_limit
from tl_web.app import render
from tl_web.webroute import not_found_page, web_router

router = web_router()
Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("qr.read"))]

#: The one text of the 429 answer, the same for a hit and a miss.
LIMITED_TEXT = "Too many lookups. Wait a few minutes and try again."


def counter_of(request: Request) -> scan_limit.MissCounter:
    """The app's miss counter (made on first use; tests may set ``app.state.scan_misses``)."""
    state = request.app.state
    found = getattr(state, "scan_misses", None)
    if found is None:
        found = scan_limit.MissCounter()
        state.scan_misses = found
    return found  # type: ignore[no-any-return]


def _who(request: Request, ctx: ApiContext) -> tuple[str, str]:
    token = request.scope.get(TOKEN_KEY)
    return (
        token if isinstance(token, str) else "",
        client_key(request.scope, ctx.settings.trusted_proxy_header),
    )


def _limited(wait: int, request: Request) -> Response:
    page = render(request, "scan.html", 429, limited=LIMITED_TEXT, card=None)
    page.headers["Retry-After"] = str(wait)
    return page


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M") + " UTC"


@router.get("/q")
def scan_form(request: Request, _actor: Reader) -> Response:
    return render(request, "scan.html", card=None)


@router.post("/q", dependencies=[Depends(csrf.verify_origin)])
def scan_typed(
    request: Request, ctx: Ctx, _actor: Reader, code: Annotated[str, Form(max_length=200)] = ""
) -> Response:
    token, address = _who(request, ctx)
    counter = counter_of(request)
    wait, stamp = counter.reserve(token, address)  # a typed code is a lookup: counted first
    if wait > 0:
        return _limited(wait, request)
    plain = normalise_code(code)
    if plain is None:
        return not_found_page(request)  # a malformed code is a miss: the count stays
    counter.refund(token, address, stamp)  # the redirect looks nothing up
    return RedirectResponse(f"/web/q/{plain}", status_code=303)


@router.get("/q/{code}")
def scan_card(request: Request, code: str, ctx: Ctx, _actor: Reader) -> Response:
    token, address = _who(request, ctx)
    counter = counter_of(request)
    wait, stamp = counter.reserve(token, address)  # counted before the resolver runs
    if wait > 0:
        return _limited(wait, request)
    card = None
    try:
        now = datetime.now(UTC)
        with ctx.backend(True) as uow:
            card = resolve(uow.conn(), code, current_viewer(), now)
    finally:
        if card is not None:
            counter.refund(token, address, stamp)  # a hit costs nothing
    if card is None:
        return not_found_page(request)
    valid = _utc(card.valid_until) if card.valid_until else None
    return render(request, "scan.html", card=card, as_of=_utc(card.as_of), valid_until=valid)
