"""Authentication and authorization contracts for P1-I0 (ADR-0008; replaces the ADR-0005 stub).

Frozen for the increment: change only by orchestrator decision. Changed once, by the owner's
request of 2026-10-13 (ADR-0013): a third role, ``document_controller``.

Identity is resolved behind one seam, :class:`IdentityProvider`. Phase 1 ships a username and
password provider. Microsoft Entra ID (OIDC) replaces it later without changing callers: callers
only ever see a :class:`Principal`.

Authorization has three roles (ADR-0008 decision 3, amended by ADR-0013):

- ``admin`` may do everything;
- ``user`` may do everything except ``admin.*`` and ``control.*`` actions;
- ``document_controller`` is a ``user`` who may also run the ``control.*`` actions (the controlling
  acts of document control, ADR-0011 as superseded by ADR-0013). It is not an admin: no ``admin.*``;
- an ``agent:*`` principal keeps the fixed propose-only rule (B15): it never changes a record
  directly, whatever its role.

What goes where. Accounts, role changes and agent-token issue/revoke are ledger events, so the
admin history is auditable. Secrets never enter the ledger, the archive, the lake or webhooks:
password hashes, session token hashes, agent token hashes and failed-attempt counters live in
operational tables (like ``wh_secret``), created by the generated DDL but outside ``cur_*``
projections and excluded from archive and lake.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

# Account.Created: {account_id, username, display_name, kind, roles}
ACCOUNT_CREATED = "Account.Created"
# Account.RolesSet: {account_id, roles, reason}
ACCOUNT_ROLES_SET = "Account.RolesSet"
# Account.Disabled / Account.Enabled: {account_id, reason}
ACCOUNT_DISABLED = "Account.Disabled"
ACCOUNT_ENABLED = "Account.Enabled"
# Account.PasswordChanged: {account_id, by, forced: bool} -- metadata only, never the hash
ACCOUNT_PASSWORD_CHANGED = "Account.PasswordChanged"
# AgentToken.Issued: {token_id, account_id, label, expires_at} -- metadata only, never the token
AGENT_TOKEN_ISSUED = "AgentToken.Issued"
# AgentToken.Revoked: {token_id, account_id, reason}
AGENT_TOKEN_REVOKED = "AgentToken.Revoked"
# Stream type "core.Account", stream id "account:<account_id>", scope "company".

Role = Literal["admin", "user", "document_controller"]
#: Every role, in the order a role list is stored: alphabetical, as the projection keeps it.
ROLES: tuple[Role, ...] = ("admin", "document_controller", "user")
AccountKind = Literal["person", "agent", "sim"]
AccountStatus = Literal["active", "disabled"]

#: Actions only an admin may run. Every other action is open to any authenticated non-agent
#: principal, and to agents only where the propose-only rule allows it.
ADMIN_ACTION_PREFIX = "admin."

#: Actions an admin or a document controller may run (ADR-0013). Only the names the API lists as
#: controller commands are open to a document controller (``RoleAuthorizer.controller_actions``);
#: any other ``control.*`` action is an admin's, so a typo or a new name fails closed.
CONTROL_ACTION_PREFIX = "control."

#: The seeded dev/demo account (ADR-0008 decision 4). Never created when ``TL_ENV=prod``, and the
#: server refuses to start bound to a non-loopback address while it exists and is enabled.
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo"  # noqa: S105 - documented dev seed, refused outside dev (see above)


class Principal(BaseModel):
    """Who is calling. The only identity callers see."""

    actor: str  # "user:<username>" for people and sim accounts, "agent:<name>" for agents
    account_id: str
    kind: AccountKind
    roles: list[Role]
    via: Literal["password", "session", "agent_token", "oidc", "dev_token"]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_controller(self) -> bool:
        """An admin or a document controller, and never an agent (ADR-0013)."""
        return self.kind != "agent" and (
            "admin" in self.roles or "document_controller" in self.roles
        )


class AccountView(BaseModel):
    account_id: str
    username: str
    display_name: str
    kind: AccountKind
    roles: list[Role]
    status: AccountStatus
    locked_until: str | None  # ISO 8601 UTC while locked out after failed sign-ins
    created_at: str
    seq: int


class AgentTokenView(BaseModel):
    token_id: str
    account_id: str
    label: str
    expires_at: str | None
    revoked: bool
    issued_by: str


class IdentityProvider(Protocol):
    """Turns credentials into a Principal. Phase 1: username and password; later: Entra OIDC."""

    def authenticate_password(self, username: str, password: str) -> Principal: ...
    def principal_for_bearer(self, token: str) -> Principal: ...  # session or agent token


class Authorizer(Protocol):
    """Decides one action. Raises ``ForbiddenError`` (a ServiceError, 403 ``forbidden``)."""

    def authorize(self, principal: Principal, action: str, resource: str) -> None: ...


# Service signatures (implemented in tl_core.auth; supervisor-built: hashing, sessions, lockout,
# authorizer, account services):
#   create_account(uow, *, username, display_name, kind, roles, password: str | None, by)
#       -> AccountView
#   set_roles(uow, *, account_id, roles, by, reason)
#   disable / enable(uow, *, account_id, by, reason)
#   change_password(uow, *, account_id, new_password, by, current_password: str | None)
#       A person changing their own password gives the current one; an admin reset does not.
#   issue_agent_token(uow, *, account_id, label, expires_at, by) -> tuple[AgentTokenView, str]
#       Returns the token once; only its hash is stored.
#   revoke_agent_token(uow, *, token_id, by, reason)
#   sign_in(conn_factory, *, username, password) -> tuple[Principal, str]  # opaque session token
#   sign_out(conn_factory, *, token) ; list_accounts(conn) -> list[AccountView]
#   seed_demo(uow_factory, *, env: str) -> AccountView | None
#       No-op unless env is dev, demo or test.
# Errors (ServiceError subclasses, mapped in tl_api.errors): InvalidCredentialsError (401
# invalid_credentials, same message for unknown user and wrong password), AccountLockedError (423
# account_locked), AccountDisabledError (403 account_disabled), ForbiddenError (403 forbidden),
# LastAdminError (409 last_admin: the last active admin cannot be disabled or demoted),
# WeakPasswordError (422 weak_password), UsernameTakenError (409 username_taken).
