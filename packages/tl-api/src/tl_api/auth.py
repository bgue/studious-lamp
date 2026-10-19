"""Identity and authorisation at the HTTP edge (ADR-0009; the ADR-0005 stub in dev and test only).

* Identity: ``Authorization: Bearer <token>``. A :class:`Resolver` turns the token into a
  :class:`~tl_core.auth.types.Principal`: a session or agent token through the
  ``IdentityProvider`` (the seam Entra ID will replace), or, only when ``TL_ENV`` is ``dev``,
  ``test`` or ``ci``, a token of the dev token file. No token, or a bad one, is HTTP 401.
* Authorisation: every route depends on ``guard(action)``, which runs the ``Authorizer`` once
  (``admin.*`` needs the admin role) and, for the legacy 3-argument hook, once more.
  ``agent:*`` principals keep the fixed propose-only rule (``agent_must_propose``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from tl_core.auth.errors import InvalidCredentialsError
from tl_core.auth.types import IdentityProvider, Principal

from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError
from tl_api.tokens import TokenStore

Authorizer = Callable[[str, str, str], None]
"""The legacy 3-argument hook (actor, action, resource). The real model is ``tl_core.auth``."""


class Unauthorized(Exception):
    """No bearer token, or one the token file does not know."""


class Forbidden(Exception):
    """``authorize`` refused the action."""


def authorize(actor: str, action: str, resource: str) -> None:
    """The allow-all legacy hook (MCP and the simulator call it). Raise ``Forbidden`` to refuse.

    API routes do not rely on it: ``guard`` runs the role ``Authorizer`` first.
    """
    return None


def dev_principal(actor: str) -> Principal:
    """The principal of a dev-token actor: a ``user`` role, never admin (ADR-0009 section 9)."""
    kind = "agent" if actor.startswith("agent:") else "person"
    return Principal(
        actor=actor, account_id=f"dev:{actor}", kind=kind, roles=["user"], via="dev_token"
    )


class Resolver:
    """Bearer token to ``Principal``, or ``None`` when the token is not valid."""

    def __init__(
        self, identity: IdentityProvider, tokens: TokenStore | None, *, dev_tokens: bool
    ) -> None:
        self._identity = identity
        self._tokens = tokens
        self._dev_tokens = dev_tokens

    def resolve(self, token: str) -> Principal | None:
        if self._dev_tokens and self._tokens is not None:
            actor = self._tokens.actor_for(token)
            if actor is not None:
                return dev_principal(actor)
        try:
            return self._identity.principal_for_bearer(token)
        except InvalidCredentialsError:
            return None


AGENT_MUST_PROPOSE = "agent_must_propose"
AGENT_MUST_PROPOSE_MESSAGE = (
    "agents propose record changes through MCP (P0-I6 D4); a human accepts them"
)
#: The only commands an ``agent:`` token may run over REST: posting to the feed is a message, not a
#: record change (brief 21.3). Everything else that changes a record is propose-only.
AGENT_DIRECT_COMMANDS = frozenset(
    {
        "PostToFeed",
        "EditPost",
        "RetractPost",
        "ReactToPost",
        # P1-I7 WS-B: a thread message changes no record and never dispatches (brief 21.5)
        "PostThreadMessage",
        "EditThreadMessage",
        "RetractThreadMessage",
    }
)


def refuse_agent_writes(actor: str) -> None:
    """Raise ``ApiError`` 403 ``agent_must_propose`` when ``actor`` is an ``agent:<id>``.

    FANOUT decision D4: an agent proposes record changes (MCP tools, then a person accepts); it
    never changes a record directly. This is a fixed rule of the brief, not a permission model:
    it grants nobody anything, and which people may write what stays a human gate (ADR-0005).
    """
    if actor.startswith("agent:"):
        raise ApiError(403, AGENT_MUST_PROPOSE, AGENT_MUST_PROPOSE_MESSAGE)


_bearer = HTTPBearer(auto_error=False, description="Session token, agent token or dev token")


def guard(action: str, *, changes_records: bool = False) -> Callable[..., str]:
    """A dependency that authenticates, runs the hook for ``action`` and returns the actor.

    ``changes_records=True`` marks a route that changes a record (every command but the feed
    ones, the file writes): an ``agent:`` actor is then refused with ``agent_must_propose``.

    ``action`` is a dotted name such as ``record.read`` or ``command.CreateRecord``; the resource
    passed to the hook is the request path.
    """

    def dependency(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_ctx)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    ) -> str:
        principal = _principal(request, ctx, credentials)
        if changes_records:  # first, so an agent gets the specific code, not a bare 403
            refuse_agent_writes(principal.actor)
        ctx.authorizer.authorize(principal, action, request.url.path)
        ctx.authorize(principal.actor, action, request.url.path)
        return principal.actor

    dependency.action = action  # type: ignore[attr-defined]  # read by the route-coverage test
    return dependency


def _principal(
    request: Request, ctx: ApiContext, credentials: HTTPAuthorizationCredentials | None
) -> Principal:
    """The principal the middleware resolved, else resolve the credentials here."""
    found: Principal | None = request.scope.get(PRINCIPAL_KEY)
    if found is not None:
        return found
    if credentials is None or not credentials.credentials:
        raise Unauthorized("a bearer token is required")
    found = ctx.resolver.resolve(credentials.credentials)
    if found is None:
        raise Unauthorized("unknown token")
    return found


def current_principal(
    request: Request,
    ctx: Annotated[ApiContext, Depends(get_ctx)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Principal:
    """A dependency for routes that need the whole principal (roles, kind), not just the actor."""
    return _principal(request, ctx, credentials)


#: Where the middleware keeps the principal: a private key, not ``scope["state"]``, which
#: lifespan state and other middleware can write.
PRINCIPAL_KEY = "tl_api.principal"

#: Paths that need no token. Everything else, including paths that do not exist, needs one.
OPEN_PATHS = frozenset({"/health", "/auth/sign-in"})


def bearer_token(headers: list[tuple[bytes, bytes]]) -> str | None:
    """The token of an ``Authorization: Bearer <token>`` header, else ``None``."""
    for name, value in headers:
        if name.lower() == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
    return None


class AuthenticationMiddleware:
    """Resolves the bearer token before anything else reads the request.

    A request without a valid token is answered 401 here, so a malformed body, an unknown path or a
    bad query string cannot be told apart from a missing token by an unauthenticated caller. The
    principal is kept on ``request.state`` so ``guard`` does not look the token up again; ``guard``
    still runs per route to call the ``Authorizer`` with the route's action.
    """

    def __init__(self, app: ASGIApp, resolver: Resolver) -> None:
        self.app = app
        self._resolver = resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        token = bearer_token(scope["headers"])
        principal = (
            None if token is None else await run_in_threadpool(self._resolver.resolve, token)
        )
        if principal is None:
            message = "a bearer token is required" if token is None else "unknown token"
            response = JSONResponse(
                {"error": "unauthorized", "message": message},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        scope[PRINCIPAL_KEY] = principal
        await self.app(scope, receive, send)


#: Largest request body by path prefix; credentials and account forms are tiny.
BODY_LIMITS: tuple[tuple[str, int], ...] = (("/auth/", 16 * 1024), ("/admin/", 64 * 1024))


class BodyLimitMiddleware:
    """Answers 413 `payload_too_large` to an oversized body on the auth, admin and command routes.

    It checks ``Content-Length`` and also counts the bytes of a chunked body, so a sign-in cannot be
    used to make the server read or parse megabytes before it says no. It runs before the
    authentication middleware, so an unauthenticated caller gets the same limit.
    """

    def __init__(self, app: ASGIApp, limits: tuple[tuple[str, int], ...] = BODY_LIMITS) -> None:
        self.app = app
        self._limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = None
        if scope["type"] == "http":
            path = scope["path"]
            limit = next((size for prefix, size in self._limits if path.startswith(prefix)), None)
        if limit is None:
            await self.app(scope, receive, send)
            return
        for name, value in scope["headers"]:
            if name.lower() == b"content-length" and value.isdigit() and int(value) > limit:
                await self._refuse(scope, receive, send, limit)
                return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # an HTTPException is the one error FastAPI's body reading lets through; the
                    # app's handler answers it as 413 `payload_too_large`
                    raise HTTPException(413, f"the request body is over {limit} bytes")
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        response = JSONResponse(
            {"error": "payload_too_large", "message": f"the request body is over {limit} bytes"},
            status_code=413,
        )
        await response(scope, receive, send)
