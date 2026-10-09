"""The application factory (O5): ``create_app(backend, ...)`` builds the FastAPI app.

The app holds no state of its own beyond ``app.state.ctx`` (an :class:`ApiContext`): the storage
backend, the token store, the authorisation hook, the change-feed hub and the file service. Tests
and ``tl_api.main`` build it; ``tl_api.openapi`` builds one over a backend that is never used.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from tl_core.files.service import FileService

from tl_api import commands
from tl_api.auth import Authorizer, Forbidden, Unauthorized, authorize
from tl_api.backend import Backend
from tl_api.context import ApiContext
from tl_api.errors import ApiError, ErrorBody, body_for
from tl_api.feed import FeedHub
from tl_api.routes import events, files, health, links, records, reference
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore

log = logging.getLogger("tl_api")

API_TITLE = "Throughline API"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "Records, links, workflow, files and the change feed over HTTP. Phase 0 is a development "
    "server: identity is a static bearer token and every authenticated actor may do everything "
    "(ADR-0005). Errors are `{error, message, ...}` bodies; the `error` codes are stable."
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorBody, "description": text}
    for code, text in {
        401: "Missing or unknown bearer token.",
        403: "Refused by the authorisation hook or by a quarantine rule.",
        404: "No such resource.",
        409: "Version conflict, state conflict or failed workflow guard.",
        422: "The request is well formed but cannot be applied.",
    }.items()
}


def _json(status: int, body: ErrorBody, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True), status_code=status, headers=headers
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Unauthorized)
    async def _unauthorized(_: Request, exc: Unauthorized) -> JSONResponse:
        return _json(
            401,
            ErrorBody(error="unauthorized", message=str(exc)),
            {"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(Forbidden)
    async def _forbidden(_: Request, exc: Forbidden) -> JSONResponse:
        return _json(403, ErrorBody(error="forbidden", message=str(exc) or "not allowed"))

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _json(exc.status, ErrorBody(error=exc.error, message=exc.message))

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        message = "; ".join(f"{'.'.join(i['loc'])}: {i['msg']}" for i in issues)
        return _json(422, ErrorBody(error="validation_error", message=message, issues=issues))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        names = {404: "not_found", 405: "method_not_allowed"}
        code = names.get(exc.status_code, "http_error")
        return _json(exc.status_code, ErrorBody(error=code, message=str(exc.detail)))

    @app.exception_handler(Exception)
    async def _expected_or_internal(_: Request, exc: Exception) -> JSONResponse:
        mapped = body_for(exc)
        if mapped is not None:
            status, body = mapped
            return _json(status, body)
        log.exception("unhandled error")
        return _json(500, ErrorBody(error="internal_error", message="internal server error"))


def create_app(
    backend: Backend,
    *,
    settings: ApiSettings | None = None,
    tokens: TokenStore | None = None,
    files_service: FileService | None = None,
    authorize_hook: Authorizer = authorize,
) -> FastAPI:
    """Build the application over ``backend``.

    ``tokens`` defaults to the file named in ``settings``. ``files_service`` may be ``None``: the
    file routes then answer 503. The change-feed poller starts and stops with the app's lifespan
    (it does not run under a ``TestClient`` that is not used as a context manager; in-process
    writes still reach the stream through the bus).
    """
    cfg = settings if settings is not None else ApiSettings()
    feed = FeedHub(
        backend,
        poll_interval_s=cfg.poll_interval_s,
        keepalive_s=cfg.sse_keepalive_s,
        wait_s=cfg.sse_wait_s,
        max_streams=cfg.max_streams,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        feed.start()
        try:
            yield
        finally:
            feed.stop()

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        responses=_ERROR_RESPONSES,
        generate_unique_id_function=lambda route: route.name,
    )
    app.state.ctx = ApiContext(
        backend=backend,
        tokens=tokens if tokens is not None else TokenStore(cfg.tokens_path),
        authorize=authorize_hook,
        feed=feed,
        settings=cfg,
        files=files_service,
    )
    install_error_handlers(app)

    if cfg.insecure_dev:

        @app.middleware("http")
        async def _warn(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            log.warning(
                "INSECURE DEV SERVER: %s %s (no real authentication; ADR-0005)",
                request.method,
                request.url.path,
            )
            return await call_next(request)

    for module in (health, records, links, reference, events, files):
        app.include_router(module.router)
    app.include_router(commands.router)
    return app
