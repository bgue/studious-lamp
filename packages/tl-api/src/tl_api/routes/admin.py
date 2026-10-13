"""The admin module over HTTP: accounts, roles, passwords and agent tokens (ADR-0009, ADR-0008).

Every route needs the `admin` role: the guard actions are all `admin.*`, so the `Authorizer`
answers 403 `forbidden` to a `user` and to every agent. Thin: one `tl_core.auth` call per route
inside `ctx.backend()`; the token's actor is `by`. Errors are the account rows of
`tl_api.errors` (404 `account_not_found`, 409 `username_taken`, `last_admin`, `account_state`,
422 `invalid_account`, `weak_password`). A password or a token appears only in the request that
sets it and, for a new agent token, once in the answer; no route logs or echoes either.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from tl_core.auth import accounts, queries
from tl_core.auth.password import prepare_password
from tl_core.auth.types import ROLES, AccountKind, AccountView, AgentTokenView, Role
from tl_core.util import utcnow

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["admin"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Lister = Annotated[str, Depends(guard("admin.accounts.list"))]
Creator = Annotated[str, Depends(guard("admin.accounts.create"))]
RoleSetter = Annotated[str, Depends(guard("admin.accounts.roles"))]
StateSetter = Annotated[str, Depends(guard("admin.accounts.state"))]
Resetter = Annotated[str, Depends(guard("admin.accounts.password"))]
TokenLister = Annotated[str, Depends(guard("admin.tokens.list"))]
TokenIssuer = Annotated[str, Depends(guard("admin.tokens.issue"))]
TokenRevoker = Annotated[str, Depends(guard("admin.tokens.revoke"))]
MAX_SECRET = 1024
MAX_REASON = 500
DEFAULT_TOKEN_DAYS = 90

Reason = Annotated[str | None, Field(max_length=MAX_REASON)]


class CreateAccountBody(BaseModel):
    """Body of ``POST /admin/accounts``."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, Field(min_length=1, max_length=256)]
    display_name: Annotated[str, Field(min_length=1, max_length=256)]
    kind: AccountKind = "person"
    roles: list[Role] = Field(default_factory=lambda: ["user"], min_length=1, max_length=len(ROLES))
    password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)] | None = Field(
        default=None, description="Never for an `agent` account; it gets a token instead."
    )


class RolesBody(BaseModel):
    """Body of ``PUT /admin/accounts/{account_id}/roles``."""

    model_config = ConfigDict(extra="forbid")

    roles: list[Role] = Field(min_length=1, max_length=len(ROLES))
    reason: Reason = None


class ReasonBody(BaseModel):
    """Body of the disable, enable and token revoke calls."""

    model_config = ConfigDict(extra="forbid")

    reason: Reason = None


class ResetPasswordBody(BaseModel):
    """Body of ``POST /admin/accounts/{account_id}/password`` (an admin reset)."""

    model_config = ConfigDict(extra="forbid")

    new_password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]


class IssueTokenBody(BaseModel):
    """Body of ``POST /admin/tokens``."""

    model_config = ConfigDict(extra="forbid")

    account_id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=256)]
    expires_in_days: Annotated[int, Field(ge=1, le=3650)] | None = Field(
        default=DEFAULT_TOKEN_DAYS, description="Days until the token expires; null: never."
    )


class IssuedToken(BaseModel):
    """A new agent token. `token` is shown here once and cannot be read back."""

    token: str
    view: AgentTokenView

    def __repr__(self) -> str:
        return f"IssuedToken(view={self.view!r}, token=<hidden>)"

    __str__ = __repr__


@router.get("/admin/accounts", operation_id="admin_list_accounts", response_model=list[AccountView])
def list_accounts(ctx: Ctx, actor: Lister) -> list[AccountView]:
    """Every account with its roles, status and any lock in force. No secrets."""
    with ctx.backend(True) as uow:
        return queries.list_accounts(uow.conn())


@router.get(
    "/admin/accounts/{account_id}", operation_id="admin_get_account", response_model=AccountView
)
def get_account(account_id: str, ctx: Ctx, actor: Lister) -> AccountView:
    """One account by id (404 `account_not_found`)."""
    with ctx.backend(True) as uow:
        return queries.get_account(uow.conn(), account_id)


@router.post(
    "/admin/accounts",
    operation_id="admin_create_account",
    response_model=AccountView,
    status_code=201,
)
def create_account(body: CreateAccountBody, ctx: Ctx, actor: Creator) -> AccountView:
    """Create an account. A password must meet the policy (422 `weak_password`); agents get none."""
    # The policy and the slow hash run before the write transaction opens: no hash may run
    # while a write transaction is open.
    prepared = (
        None if body.password is None else prepare_password(body.password, username=body.username)
    )
    with ctx.backend() as uow:
        return accounts.create_account(
            uow,
            username=body.username,
            display_name=body.display_name,
            kind=body.kind,
            roles=list(body.roles),
            password=prepared,
            by=actor,
        )


@router.put(
    "/admin/accounts/{account_id}/roles",
    operation_id="admin_set_roles",
    response_model=AccountView,
)
def set_roles(account_id: str, body: RolesBody, ctx: Ctx, actor: RoleSetter) -> AccountView:
    """Replace the roles. The last active admin cannot be demoted (409 `last_admin`)."""
    with ctx.backend() as uow:
        return accounts.set_roles(
            uow,
            account_id=account_id,
            roles=list(body.roles),
            by=actor,
            reason=body.reason,
        )


@router.post(
    "/admin/accounts/{account_id}/disable",
    operation_id="admin_disable_account",
    response_model=AccountView,
)
def disable_account(account_id: str, body: ReasonBody, ctx: Ctx, actor: StateSetter) -> AccountView:
    """Disable an account: its sessions and agent tokens stop working. Not the last admin."""
    with ctx.backend() as uow:
        return accounts.disable(uow, account_id=account_id, by=actor, reason=body.reason)


@router.post(
    "/admin/accounts/{account_id}/enable",
    operation_id="admin_enable_account",
    response_model=AccountView,
)
def enable_account(account_id: str, body: ReasonBody, ctx: Ctx, actor: StateSetter) -> AccountView:
    """Enable a disabled account again."""
    with ctx.backend() as uow:
        return accounts.enable(uow, account_id=account_id, by=actor, reason=body.reason)


@router.post(
    "/admin/accounts/{account_id}/password",
    operation_id="admin_reset_password",
    response_model=AccountView,
)
def reset_password(
    account_id: str, body: ResetPasswordBody, ctx: Ctx, actor: Resetter
) -> AccountView:
    """Set a new password without the old one. Ends the account's sessions and clears its lock."""
    with ctx.backend(True) as uow:
        account = queries.get_account(uow.conn(), account_id)
    # No transaction is open here: the policy and the slow hash run outside the writer lock.
    prepared = prepare_password(body.new_password, username=account.username)
    with ctx.backend() as uow:
        accounts.change_password(uow, account_id=account_id, new_password=prepared, by=actor)
        return queries.get_account(uow.conn(), account_id)


@router.get("/admin/tokens", operation_id="admin_list_tokens", response_model=list[AgentTokenView])
def list_tokens(
    ctx: Ctx,
    actor: TokenLister,
    account_id: Annotated[str | None, Query(description="Only this agent account.")] = None,
    include_revoked: Annotated[bool, Query()] = True,
) -> list[AgentTokenView]:
    """Agent token metadata. The tokens themselves cannot be read back."""
    with ctx.backend(True) as uow:
        return queries.list_agent_tokens(
            uow.conn(), account_id=account_id, include_revoked=include_revoked
        )


@router.post(
    "/admin/tokens", operation_id="admin_issue_token", response_model=IssuedToken, status_code=201
)
def issue_token(body: IssueTokenBody, ctx: Ctx, actor: TokenIssuer) -> IssuedToken:
    """Issue an agent token (default 90 days; `expires_in_days: null` for none). Shown once."""
    expires = (
        None if body.expires_in_days is None else utcnow() + timedelta(days=body.expires_in_days)
    )
    with ctx.backend() as uow:
        view, token = accounts.issue_agent_token(
            uow,
            account_id=body.account_id,
            label=body.label,
            expires_at=expires,
            by=actor,
        )
    # The commit has happened: the token leaves the server only in this answer.
    return IssuedToken(token=token, view=view)


@router.post(
    "/admin/tokens/{token_id}/revoke",
    operation_id="admin_revoke_token",
    response_model=AgentTokenView,
)
def revoke_token(token_id: str, body: ReasonBody, ctx: Ctx, actor: TokenRevoker) -> AgentTokenView:
    """Revoke an agent token at once (404 `agent_token_not_found`, 409 `account_state`)."""
    with ctx.backend() as uow:
        return accounts.revoke_agent_token(uow, token_id=token_id, by=actor, reason=body.reason)
