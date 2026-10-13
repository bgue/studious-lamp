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


#: What an ``agent:*`` principal may do over REST: reads, the feed commands (posting is a message,
#: not a record change, brief 21.3) and its own sign-out. Everything else is denied by default, so a
#: new route is closed to agents until someone adds it here; the propose-only rule
#: (``agent_must_propose``) is a second layer on the routes that change records.
AGENT_ACTIONS = frozenset(
    {
        "auth.me",
        "auth.sign_out",
        "document.read",
        "events.read",
        "events.stream",
        "feed.read",
        "file.read",
        "link.read",
        "openapi.read",
        "proposal.read",
        # An agent may call these two so the service can answer ProposalDeciderError (403
        # `proposal_decider`, a documented code): only a person decides a proposal.
        "proposal.accept",
        "proposal.reject",
        "record.read",
        "reference.read",
        "setting.read",
        "standards.read",
        "tag.read",
        "type.read",
        "command.PostToFeed",
        "command.EditPost",
        "command.RetractPost",
        "command.ReactToPost",
    }
)


def agent_may(action: str, allowed: frozenset[str] = AGENT_ACTIONS) -> bool:
    return action in allowed


class RoleAuthorizer:
    """``admin.*`` needs a human admin; a person with any role may do the rest; an agent is closed.

    An ``agent:*`` principal never runs an ``admin.*`` action, whatever its roles, and may run only
    the actions in :data:`AGENT_ACTIONS` (fail closed). The propose-only rule (B15) for the
    commands that change records is applied by the API and MCP as well. The MCP server passes its
    own list of tool and resource actions as ``agent_actions`` (``tl_mcp.identity.MCP_ACTIONS``
    on top of :data:`AGENT_ACTIONS`): there is no prefix rule, so a new tool is closed to agents
    until someone adds it to that list.
    """

    def __init__(self, *, agent_actions: frozenset[str] = AGENT_ACTIONS) -> None:
        self._agent_actions = agent_actions

    def authorize(self, principal: Principal, action: str, resource: str) -> None:
        if not principal.roles:
            raise ForbiddenError("the account has no role")
        if action.startswith(ADMIN_ACTION_PREFIX) and (
            principal.kind == "agent" or not principal.is_admin
        ):
            raise ForbiddenError(f"{action} needs the admin role")
        if principal.kind == "agent" and not agent_may(action, self._agent_actions):
            raise ForbiddenError(f"{action} is not open to agents")
