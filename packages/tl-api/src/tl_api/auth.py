"""Dev-only identity and the authorisation hook (ADR-0005). This is not an auth model.

* Identity: ``Authorization: Bearer <token>``; the token file maps it to an actor. No token, or an
  unknown one, is HTTP 401.
* Authorisation: every route depends on ``guard(action)``, which calls ``authorize(actor, action,
  resource)`` once. Phase 0 allows everything. The real model (roles, ABAC, confidentiality) is a
  human gate: it replaces ``authorize`` and the token lookup, nothing else.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from tl_api.context import ApiContext, get_ctx
from tl_api.tokens import TokenStore

Authorizer = Callable[[str, str, str], None]


class Unauthorized(Exception):
    """No bearer token, or one the token file does not know."""


class Forbidden(Exception):
    """``authorize`` refused the action."""


def authorize(actor: str, action: str, resource: str) -> None:
    """Phase 0: every authenticated actor may do everything. Raise ``Forbidden`` to refuse."""
    return None


_bearer = HTTPBearer(auto_error=False, description="Static dev token (ADR-0005)")


def guard(action: str) -> Callable[..., str]:
    """A dependency that authenticates, runs the hook for ``action`` and returns the actor.

    ``action`` is a dotted name such as ``record.read`` or ``command.CreateRecord``; the resource
    passed to the hook is the request path.
    """

    def dependency(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_ctx)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    ) -> str:
        if credentials is None or not credentials.credentials:
            raise Unauthorized("a bearer token is required")
        actor = ctx.tokens.actor_for(credentials.credentials)
        if actor is None:
            raise Unauthorized("unknown token")
        ctx.authorize(actor, action, request.url.path)
        return actor

    return dependency


#: Paths that need no token. Everything else, including paths that do not exist, needs one.
OPEN_PATHS = frozenset({"/health"})


def bearer_token(headers: list[tuple[bytes, bytes]]) -> str | None:
    """The token of an ``Authorization: Bearer <token>`` header, else ``None``."""
    for name, value in headers:
        if name.lower() == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
    return None


class AuthenticationMiddleware:
    """Resolves the bearer token before anything else reads the request (ADR-0005).

    A request without a known token is answered 401 here, so a malformed body, an unknown path
    or a bad query string cannot be told apart from a missing token by an unauthenticated caller.
    ``guard`` still runs per route to call ``authorize`` with the route's action.
    """

    def __init__(self, app: ASGIApp, tokens: TokenStore) -> None:
        self.app = app
        self._tokens = tokens

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        token = bearer_token(scope["headers"])
        if token is None or self._tokens.actor_for(token) is None:
            message = "a bearer token is required" if token is None else "unknown token"
            response = JSONResponse(
                {"error": "unauthorized", "message": message},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
