"""Who the MCP server acts as: an agent token, checked again on every call (ADR-0009 sec. 5, 11).

``TL_AGENT_TOKEN`` (set by an admin's ``tl admin token issue``) is the only credential. It is read
from the environment, never from the command line, and is not printed, logged or put in a message.
The server's actor is the agent the token belongs to. Because a stdio server lives as long as its
client, the token is looked up **on every tool and resource call**: a token that is revoked,
expired or whose agent is disabled stops working at the next call, not at the next start. Each call
is then authorised by the role ``Authorizer``, which allows an agent only the actions in
``MCP_ACTIONS`` (an explicit list, no prefix rule: a new tool is closed until it is added).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from tl_api.auth import Forbidden
from tl_core.auth.provider import AGENT_ACTIONS, PasswordIdentityProvider, RoleAuthorizer
from tl_core.auth.sessions import UowFactory
from tl_core.auth.tokens import token_kind
from tl_core.auth.types import Authorizer, Principal

from tl_mcp.context import Authorizer as McpAuthorizer

#: Every action an MCP tool or resource asks the authorizer about (``mcp.<tool>`` and
#: ``mcp.resource.<name>``). A test registers the real server and fails on a tool or resource that
#: is missing here or listed here without existing.
MCP_ACTIONS = frozenset(
    {
        "mcp.search_records",
        "mcp.get_record",
        "mcp.get_links",
        "mcp.trace",
        "mcp.get_settings",
        "mcp.lake_query",
        "mcp.list_record_types",
        "mcp.get_record_type",
        "mcp.get_record_body",
        "mcp.list_code_values",
        "mcp.list_tag_classes",
        "mcp.get_tag",
        "mcp.list_documents",
        "mcp.get_document",
        "mcp.get_document_diff",
        "mcp.list_stale_links",
        "mcp.list_overdue_reviews",
        "mcp.list_transmittals",
        "mcp.get_transmittal",
        "mcp.list_derived_documents",
        "mcp.get_derived_document",
        "mcp.validate_against_schema",
        "mcp.start_extraction",
        "mcp.list_correspondence",
        "mcp.get_correspondence",
        "mcp.list_response_clocks",
        "mcp.list_parties",
        "mcp.suggest_triage",
        "mcp.list_rfis",
        "mcp.get_rfi",
        "mcp.list_commercial_items",
        "mcp.get_commercial_item",
        "mcp.get_evidence_trail",
        "mcp.propose_triage",
        "mcp.propose_import",
        "mcp.list_schedules",
        "mcp.get_schedule",
        "mcp.list_schedule_activities",
        "mcp.get_schedule_activity",
        "mcp.compare_schedule_snapshots",
        "mcp.get_look_ahead",
        "mcp.resolve_schedule_activity",
        "mcp.get_activity_float_trend",
        "mcp.list_orphaned_links",
        "mcp.get_record_activity_links",
        "mcp.list_cost_codes",
        "mcp.get_cost_code",
        "mcp.list_cost_snapshots",
        "mcp.propose_publish_schedule_snapshot",
        "mcp.create_record",
        "mcp.update_psets",
        "mcp.link_records",
        "mcp.transition_workflow",
        "mcp.propose_setting_change",
        "mcp.post_feed",
        "mcp.resource.record",
        "mcp.resource.schema",
        "mcp.resource.relations",
        "mcp.resource.lake_schema",
        "mcp.resource.types",
        "mcp.resource.type",
    }
)

TOKEN_ENV = "TL_AGENT_TOKEN"  # noqa: S105 - the name of the variable, not a secret
HOW_TO_GET_ONE = "an admin issues one with `tl admin token issue <agent> --label <what for>`"


class AgentTokenError(Exception):
    """The token is missing, is not an agent token, or is not valid. The text has no token."""


def token_from_env(env: Mapping[str, str] | None = None) -> str:
    """The agent token in ``TL_AGENT_TOKEN``.

    ``AgentTokenError`` when it is unset, blank or not an agent token: a person's session token
    is refused before any database is opened.
    """
    token = (os.environ if env is None else env).get(TOKEN_ENV, "").strip()
    if not token:
        raise AgentTokenError(f"set {TOKEN_ENV} to an agent token: {HOW_TO_GET_ONE}")
    if token_kind(token) != "agent":
        raise AgentTokenError(
            f"{TOKEN_ENV} must be an agent token (it starts with tla_), not a person's session"
        )
    return token


def resolve_agent(factory: UowFactory, token: str) -> Principal:
    """The agent principal of ``token``; ``AgentTokenError`` for a token that is not valid now."""
    from tl_core.auth.errors import InvalidCredentialsError

    try:
        principal = PasswordIdentityProvider(factory).principal_for_bearer(token)
    except InvalidCredentialsError as exc:
        raise AgentTokenError(f"{TOKEN_ENV} is invalid, expired or revoked") from exc
    if principal.kind != "agent" or principal.via != "agent_token":
        raise AgentTokenError(f"{TOKEN_ENV} must be an agent token")
    return principal


def token_authorizer(
    factory: UowFactory, token: str, *, roles: Authorizer | None = None
) -> McpAuthorizer:
    """The hook ``guarded`` runs before every tool and resource: token still valid, action allowed.

    A dead token raises ``InvalidCredentialsError`` (a service error: the agent reads "invalid or
    expired token"); an action outside the agent's allowance raises ``ForbiddenError``. A token
    that now belongs to another actor than the server started with is refused too.
    """
    provider = PasswordIdentityProvider(factory)
    authorizer: Authorizer = (
        roles if roles is not None else RoleAuthorizer(agent_actions=AGENT_ACTIONS | MCP_ACTIONS)
    )

    def hook(actor: str, action: str, resource: str) -> None:
        principal = provider.principal_for_bearer(token)
        if principal.actor != actor or principal.kind != "agent":
            raise Forbidden("the token no longer belongs to this server's agent")
        authorizer.authorize(principal, action, resource)

    return hook
