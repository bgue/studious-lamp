"""``mount(app)``: the ``/web`` routes, static files and security headers (spec web-client-i1).

Every answer under ``/web`` carries the same headers (CSP without inline script or style,
``nosniff``, ``Referrer-Policy``, ``Cache-Control: no-store`` unless a handler set its own). The
middleware is pure ASGI and outermost, so a 303 or 401 from the authentication middleware, a 413
from the body limit and a 404 from the router are covered too.
"""

from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from tl_api.auth import TOKEN_KEY, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import body_for
from tl_api.routes import auth as auth_routes
from tl_core.auth import sessions
from tl_core.auth.env import current_env
from tl_core.auth.errors import AuthBusyError

from tl_web import csrf, session

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"

#: Exactly the policy of the spec (section 5): no inline script, no inline style, no framing.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", CSP.encode("ascii")),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
)
PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

# the platform's table may not know module scripts; the worker and pdf.js are .mjs
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")

_templates = Environment(
    loader=FileSystemLoader(HERE / "templates"), autoescape=True, trim_blocks=False
)


def is_web_path(path: str) -> bool:
    return path == "/web" or path.startswith("/web/")


class WebHeadersMiddleware:
    """Adds the security headers to every HTTP answer under ``/web``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_web_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                names = {name for name, _ in SECURITY_HEADERS}
                headers = [(n, v) for n, v in message["headers"] if n.lower() not in names]
                headers.extend(SECURITY_HEADERS)
                if not any(n.lower() == b"cache-control" for n, _ in headers):
                    headers.append((b"cache-control", b"no-store"))  # a handler's own is kept
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, with_headers)


def render(request: Request, name: str, status: int = 200, **values: Any) -> HTMLResponse:
    """An HTML page; the CSRF token is offered only to a request that holds a session."""
    token = request.scope.get(TOKEN_KEY)
    token_value = (
        csrf.csrf_token(token, request.app.state.web_secret) if isinstance(token, str) else None
    )
    html = _templates.get_template(name).render(csrf=token_value, **values)
    return HTMLResponse(html, status_code=status)


router = APIRouter(prefix="/web", include_in_schema=False)
Ctx = Annotated[ApiContext, Depends(get_ctx)]


@router.get("/sign-in")
def sign_in_form(request: Request) -> Response:
    return render(request, "sign_in.html", username="", error=None)


@router.post("/sign-in")
def sign_in_submit(
    request: Request,
    ctx: Ctx,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """The JSON route's own handler does the work: lockout, audit, timing and error text are its."""
    try:
        out = auth_routes.sign_in(auth_routes.SignInBody(username=username, password=password), ctx)
    except Exception as exc:
        mapped = body_for(exc)
        if mapped is None:
            raise
        status, error = mapped
        page = render(request, "sign_in.html", status, username=username, error=error.message)
        if isinstance(exc, AuthBusyError):
            page.headers["Retry-After"] = "2"
        return page
    host = request.url.hostname or ""
    response = RedirectResponse("/web/", status_code=303)
    response.headers.append("set-cookie", session.session_cookie(out.token, host, current_env()))
    return response


@router.post("/sign-out", dependencies=[Depends(csrf.verify)])
def sign_out(
    request: Request, ctx: Ctx, actor: Annotated[str, Depends(guard("auth.sign_out"))]
) -> Response:
    """End the cookie's session (the service call of ``POST /auth/sign-out``) and the cookie."""
    token = request.scope.get(TOKEN_KEY)
    if isinstance(token, str):
        sessions.sign_out(ctx.backend, token=token)
    response = RedirectResponse("/web/sign-in", status_code=303)
    host = request.url.hostname or ""
    response.headers.append("set-cookie", session.expired_cookie(host, current_env()))
    return response


@router.get("/")
def home(request: Request) -> Response:
    """To the RFI log of ``TL_PROJECT``; the log page itself arrives with a later piece."""
    project = os.environ.get("TL_PROJECT", "")
    if not PROJECT_ID.fullmatch(project):
        return not_found(request)
    return RedirectResponse(f"/web/p/{project}/rfis", status_code=303)


@router.api_route(
    "/{rest:path}", methods=["POST", "PUT", "PATCH", "DELETE"], dependencies=[Depends(csrf.verify)]
)
@router.api_route("/{rest:path}", methods=["GET", "HEAD"])
def not_found(request: Request, rest: str = "") -> Response:
    """The one 404 page: the same text for a path that never existed and one that is hidden."""
    return render(request, "not_found.html", 404)


def mount(app: FastAPI) -> None:
    """Add the web client to ``app``. Call it after every other router and middleware.

    Raises ``tl_web.csrf.WebConfigError`` when ``TL_WEB_SECRET`` is short, or missing outside dev,
    test and ci.
    """
    app.state.web_secret = csrf.load_secret(os.environ)
    app.add_middleware(WebHeadersMiddleware)
    app.mount("/web/static", StaticFiles(directory=STATIC), name="web-static")
    app.include_router(router)  # last: its catch-all answers every unknown /web path
