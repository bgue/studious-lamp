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

from tl_api.context import ApiContext, get_ctx

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
