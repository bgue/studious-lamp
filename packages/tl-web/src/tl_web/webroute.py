"""``WebRoute``: a failure the API maps to JSON becomes HTML on a page route (spec section 5, 7).

Every page module builds its router with ``web_router()``. A failure the error table knows
(``tl_api.errors.body_for``) is answered here: 404 is the one ``not_found.html`` (the same status,
text and bytes for a hidden record and one that never existed), any other status is the status line
fragment ``! <message>`` that htmx puts into ``#log-status``. An exception the table does not know
is not caught: it reaches the app's handlers as before (a 403 ``csrf_refused`` stays JSON).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from tl_api.errors import body_for

from tl_web.app import render


def status_fragment(
    request: Request, text: str, status: int = 200, *, error: bool = True
) -> Response:
    """The status line as a fragment: ``! text`` for a refusal, plain ``text`` otherwise.

    The ``HX-Retarget`` and ``HX-Reswap`` headers send it to ``#log-status`` whatever element asked,
    so a refusal never lands in the panel.
    """
    page = render(request, "status.html", status, text=("! " if error else "") + text)
    page.headers["HX-Retarget"] = "#log-status"
    page.headers["HX-Reswap"] = "outerHTML"
    return page


def not_found_page(request: Request) -> HTMLResponse:
    """The one 404 page, for a hidden record and an unknown one alike."""
    return render(request, "not_found.html", 404)


class WebRoute(APIRoute):
    """An ``APIRoute`` whose mapped failures are HTML (see the module docstring)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except Exception as exc:
                mapped = body_for(exc)
                if mapped is None:
                    raise
                status, body = mapped
                if status == 404:
                    return not_found_page(request)
                return status_fragment(request, body.message, status)

        return handler


def web_router() -> APIRouter:
    """The router of a page module: prefix ``/web``, out of the OpenAPI schema, HTML failures."""
    return APIRouter(prefix="/web", include_in_schema=False, route_class=WebRoute)
