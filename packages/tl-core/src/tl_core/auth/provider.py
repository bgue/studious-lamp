"""The password identity provider and the role authorizer (ADR-0009 sections 5 and 11).

``PasswordIdentityProvider`` is the Phase 1 :class:`~tl_core.auth.types.IdentityProvider`. Entra ID
(OIDC) replaces it behind the same two methods; callers only ever see a ``Principal``.
``RoleAuthorizer`` is the whole authorization model of Phase 1: two roles, no per-record rules.
"""

from __future__ import annotations

from tl_core.auth import sessions
from tl_core.auth._time import Clock
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.sessions import UowFactory
from tl_core.auth.types import ADMIN_ACTION_PREFIX, Principal
from tl_core.util import utcnow


class PasswordIdentityProvider:
    """Username and password, session tokens and agent tokens, against the local account store."""

    def __init__(self, backend: UowFactory, *, clock: Clock = utcnow) -> None:
        self._backend = backend
        self._clock = clock

    def authenticate_password(self, username: str, password: str) -> Principal:
        principal, _ = sessions.authenticate(
            self._backend, username, password, with_session=False, clock=self._clock
        )
        return principal

    def principal_for_bearer(self, token: str) -> Principal:
        return sessions.principal_for_bearer(self._backend, token, clock=self._clock)


class RoleAuthorizer:
    """``admin.*`` needs a human admin; every other action needs any role.

    An ``agent:*`` principal never runs an ``admin.*`` action, whatever its roles. The propose-only
    rule (B15) is not decided here: the API and MCP apply it to the commands that change records.
    """

    def authorize(self, principal: Principal, action: str, resource: str) -> None:
        if not principal.roles:
            raise ForbiddenError("the account has no role")
        if action.startswith(ADMIN_ACTION_PREFIX) and (
            principal.kind == "agent" or not principal.is_admin
        ):
            raise ForbiddenError(f"{action} needs the admin role")
