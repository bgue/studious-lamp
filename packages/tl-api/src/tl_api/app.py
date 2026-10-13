"""The application factory (O5): ``create_app(backend, ...)`` builds the FastAPI app.

The app holds no state of its own beyond ``app.state.ctx`` (an :class:`ApiContext`): the storage
backend, the token store, the authorisation hook, the change-feed hub and the file service. Tests
and ``tl_api.main`` build it; ``tl_api.openapi`` builds one over a backend that is never used.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from tl_core.auth.env import dev_tokens_allowed
from tl_core.auth.errors import AuthBusyError
from tl_core.auth.provider import PasswordIdentityProvider, RoleAuthorizer
from tl_core.auth.types import Authorizer as CoreAuthorizer
from tl_core.auth.types import IdentityProvider
from tl_core.extypes.provider import attach as attach_extension_types
from tl_core.files.service import FileService
from tl_core.files.types import ObjectStore

from tl_api import commands
from tl_api.auth import (
    BODY_LIMITS,
    AuthenticationMiddleware,
    Authorizer,
    BodyLimitMiddleware,
    Forbidden,
    Resolver,
    Unauthorized,
    authorize,
    guard,
)
from tl_api.backend import Backend
from tl_api.context import ApiContext
from tl_api.errors import ERROR_TABLE, ApiError, ErrorBody, body_for
from tl_api.feed import FeedHub
from tl_api.ratelimit import RateLimitMiddleware, SourceLimiter
from tl_api.routes import (
    admin,
    auth,
    documents,
    engineering,
    events,
    extypes,
    files,
    health,
    links,
    proposals,
    records,
    reference,
)
from tl_api.routes import feed as feed_routes
from tl_api.routes import settings as settings_routes
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore

log = logging.getLogger("tl_api")

API_TITLE = "Throughline API"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "Records, links, workflow, files and the change feed over HTTP. Callers sign in with a "
    "username and password and send the session token as a bearer token; agents send an "
    "admin-issued token (ADR-0009). The `admin` role may do everything, `user` everything but "
    "`admin.*`. Errors are `{error, message, ...}` bodies; the `error` codes are stable."
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorBody, "description": text}
    for code, text in {
        401: "Missing or unknown bearer token.",
        403: "Refused by the authorizer, the agent propose-only rule or a quarantine rule.",
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
        names = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}
        code = names.get(exc.status_code, "http_error")
        return _json(exc.status_code, ErrorBody(error=code, message=str(exc.detail)))

    async def _mapped(_: Request, exc: Exception) -> JSONResponse:
        mapped = body_for(exc)
        assert mapped is not None  # registered only for classes the table knows
        status, body = mapped
        retry = {"Retry-After": "2"} if isinstance(exc, AuthBusyError) else None
        return _json(status, body, retry)

    # One handler per mapped class, so expected errors are answered by ExceptionMiddleware. A
    # catch-all ``Exception`` handler would send the same response from ServerErrorMiddleware, which
    # then re-raises: uvicorn logs a traceback and closes the keep-alive connection.
    for spec in ERROR_TABLE:
        app.add_exception_handler(spec.exc, _mapped)
    app.add_exception_handler(ValidationError, _mapped)

    @app.exception_handler(Exception)
    async def _internal(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", exc_info=exc)
        return _json(500, ErrorBody(error="internal_error", message="internal server error"))


def create_app(
    backend: Backend,
    *,
    settings: ApiSettings | None = None,
    tokens: TokenStore | None = None,
    files_service: FileService | None = None,
    authorize_hook: Authorizer = authorize,
    object_store: ObjectStore | None = None,
    identity: IdentityProvider | None = None,
    authorizer: CoreAuthorizer | None = None,
    dev_tokens: bool | None = None,
    source_limiter: SourceLimiter | None = None,
) -> FastAPI:
    """Build the application over ``backend``.

    ``tokens`` defaults to the file named in ``settings``. ``files_service`` may be ``None``: the
    file routes then answer 503. The change-feed poller starts and stops with the app's lifespan
    (it does not run under a ``TestClient`` that is not used as a context manager; in-process
    writes still reach the stream through the bus). ``object_store`` holds the bodies of
    object-backed extension records; ``None`` makes the body routes answer 503. The registered
    extension types of ``backend``'s ledger join the effective schema (``extypes.provider.attach``).

    ``identity`` and ``authorizer`` default to the password provider and the role authorizer over
    ``backend``. The dev token file is honoured only when ``dev_tokens`` is true; by default that is
    when ``TL_ENV`` is ``dev``, ``test`` or ``ci`` (ADR-0009 section 9). ``authorize_hook`` is the
    legacy 3-argument hook and runs after the authorizer. ``source_limiter`` counts failed sign-ins
    per client address (``tl_api.ratelimit``); the default is 20 in 10 minutes.
    """
    cfg = settings if settings is not None else ApiSettings()
    attach_extension_types(backend, prime=True)
    feed = FeedHub(
        backend,
        poll_interval_s=cfg.poll_interval_s,
        keepalive_s=cfg.sse_keepalive_s,
        wait_s=cfg.sse_wait_s,
        recheck_s=cfg.sse_recheck_s,
        max_age_s=cfg.sse_max_age_s,
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
        openapi_url=None,  # served below, behind the token; docs/reference/openapi.json is public
        responses=_ERROR_RESPONSES,
        generate_unique_id_function=lambda route: route.name,
    )
    token_store = tokens if tokens is not None else TokenStore(cfg.tokens_path)
    provider = identity if identity is not None else PasswordIdentityProvider(backend)
    use_dev_tokens = dev_tokens_allowed() if dev_tokens is None else dev_tokens
    resolver = Resolver(provider, token_store, dev_tokens=use_dev_tokens)
    app.state.ctx = ApiContext(
        backend=backend,
        tokens=token_store,
        authorize=authorize_hook,
        feed=feed,
        settings=cfg,
        identity=provider,
        authorizer=authorizer if authorizer is not None else RoleAuthorizer(),
        resolver=resolver,
        files=files_service,
        objects=object_store,
    )
    install_error_handlers(app)
    app.add_middleware(AuthenticationMiddleware, resolver=resolver)
    app.add_middleware(  # the limit applies before anything reads
        BodyLimitMiddleware,
        limits=(*BODY_LIMITS, ("/commands/", cfg.max_command_bytes)),
    )
    app.add_middleware(  # outermost: a limited source costs no hash, no body read, no query
        RateLimitMiddleware,
        limiter=source_limiter
        if source_limiter is not None
        else SourceLimiter(cfg.rate_limit_failures, cfg.rate_limit_window_s),
        trusted_header=cfg.trusted_proxy_header,
    )

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_document(
        actor: Annotated[str, Depends(guard("openapi.read"))],
    ) -> JSONResponse:
        return JSONResponse(app.openapi())

    if cfg.insecure_dev:

        @app.middleware("http")
        async def _warn(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            log.warning(
                "INSECURE DEV SERVER: %s %s (bound beyond loopback; --insecure-dev)",
                request.method,
                request.url.path,
            )
            return await call_next(request)

    for module in (
        health,
        auth,
        admin,
        records,
        links,
        reference,
        events,
        files,
        feed_routes,
        proposals,
        extypes,
        settings_routes,
        engineering,
        documents,
    ):
        app.include_router(module.router)
    app.include_router(commands.router)
    return app
