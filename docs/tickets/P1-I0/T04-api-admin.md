# P1-I0-T04 — `/admin/*` routes and the client's admin calls

Status: ready
Tier: haiku
Labels: api
Depends on: P1-I0-S2b, S2c and the review fixes F1 to F3 (on `p1/i0a`)
Branch: `p1/i0a-t04-api-admin`

## Goal
The REST API serves the admin module: `GET/POST /admin/accounts`, `GET /admin/accounts/{id}`, `PUT /admin/accounts/{id}/roles`, `POST /admin/accounts/{id}/disable|enable|password`, `GET/POST /admin/tokens` and `POST /admin/tokens/{id}/revoke`. Every route is behind an `admin.*` guard action, so only a human admin can call it. The HTTP client gains the ten matching `ApiClient` methods. `routes/admin.py` has the router, the request and response models and every route's decorator, parameters and docstring (they make the committed OpenAPI document); the eleven route functions raise `NotImplementedError`; `client/admin.py` has the methods the same way. Both modules are already wired into the app and `ApiClient`. Two provided test files (31 test functions, 45 cases) must pass and `docs/reference/openapi.json` must not change.

## Brief references (pasted)
> **Brief 11.1 Auth.** OAuth2/OIDC bearer tokens; API keys for service accounts; scopes per module.
> **ADR-0008 (owner).** Username and password now, behind an identity seam; two roles `admin` and `user`; the admin module manages accounts, roles and agent service tokens and is reachable from the CLI, API and TUI; service tokens for MCP agents are issued per agent by an admin (`agent:<name>`); the propose-only rule stays.
> **ADR-0009 (the design, already implemented in `tl_core.auth`).** Session tokens are `tls_` + 256 random bits, stored only as SHA-256, 12 hours, deleted on sign-out, disable and password change. Agent tokens are `tla_` + 256 random bits, stored as a hash, shown once, optional expiry, revocable at once. Five failed sign-ins within 15 minutes lock a name for 15 minutes (doubling to 24 hours); the counters are keyed by the normalised username whether or not the account exists, so an unknown name locks like a real one and the response never tells them apart; a locked name is refused before any password is checked. A disabled account is reported (403) only to the right password. Passwords: 12 to 128 characters, a common-password list, no composition rules (422 `weak_password` names the rule, never the password). Account events are ledger events with metadata only; every secret lives in `auth_*` operational tables. The last active admin cannot be disabled or demoted (409 `last_admin`). `admin.*` actions need a human admin: the `Authorizer` refuses `user`s and every `agent:*` principal with 403 `forbidden`.

### Specification
Each route is one call into `tl_core.auth.accounts` or `tl_core.auth.queries` inside `ctx.backend()` (a write unit of work) or `ctx.backend(True)` (a read snapshot), as the `STEPS` comment in each body says. The caller's actor, which the guard dependency returns as `actor`, is `by`. The guards are all `admin.*` actions (`Lister`, `Creator`, ... in the stub), so the `Authorizer` already answers 403 `forbidden` to a `user`, to an agent and to a dev token; do not check roles yourself. The errors are mapped rows (404 `account_not_found`, `agent_token_not_found`; 409 `username_taken`, `last_admin`, `account_state`; 422 `invalid_account`, `weak_password`); no route catches anything.

A password reset is `accounts.change_password` with `by=actor` and no current password; it ends the account's sessions and clears its lockout. It returns the `AccountView` read inside the same block, so it sees the write. A new agent token is the one place a token leaves the server: `IssuedToken(token=..., view=...)` is built after the `with` block (the commit has happened). `expires_in_days` defaults to 90; an explicit `null` means no expiry. Route order matters nowhere here; do not reorder.

The client mirrors the routes. Every id goes into the path through `quote(...)`. Failures raise the embedded exception classes via `ApiClientBase`.

**Hashing happens before the write transaction.** `accounts.create_account` and `accounts.change_password` take a `PreparedPassword`, not a string: `prepare_password(password, username=...)` applies the password policy (422 `weak_password`) and runs the slow scrypt, and it must be called before `ctx.backend()` is entered, because the writer lock is global and a hash inside it stalls every other write. A provided test fails if you hash inside the block.

Learnings that apply (paste of the relevant `docs/memory/LEARNINGS.md` entries):
- pyright is `standard` for `packages/tl-api`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P1-I0/provided/*.py.txt`; copy them into the test tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` clean and pyright clean.
- Commit your report at `docs/reports/P1-I0/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message.
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `ruff: noqa: F401` line.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py`; run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- A route stub keeps every decorator, parameter, annotation and docstring that reaches the OpenAPI document, because the document is committed and drift-checked. You change function bodies only. Run `uv run python -m tl_api.openapi --check` before committing; it must pass without regenerating.
- An exception inside a unit of work rolls the whole unit back; the services already handle every case that must survive a refusal. Do not add `try`/`except` around service calls, and do not call `uow.conn()` yourself except where a step says so.
- This is credential-handling glue. Never log, print, echo, store or put in an exception message a password, a hash or a token, and never add a debug line that does. Reviewers check this first.
- The Starlette `TestClient` cannot send a non-ASCII header value; the provided tests already deal with it.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number after "cases".

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-api/src/tl_api/routes/admin.py` (the stub you complete):
```python
"""The admin module over HTTP: accounts, roles, passwords and agent tokens (ADR-0009, ADR-0008).

Every route needs the `admin` role: the guard actions are all `admin.*`, so the `Authorizer`
answers 403 `forbidden` to a `user` and to every agent. Thin: one `tl_core.auth` call per route
inside `ctx.backend()`; the token's actor is `by`. Errors are the account rows of
`tl_api.errors` (404 `account_not_found`, 409 `username_taken`, `last_admin`, `account_state`,
422 `invalid_account`, `weak_password`). A password or a token appears only in the request that
sets it and, for a new agent token, once in the answer; no route logs or echoes either.

STUB (P1-I0-T04): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final (they make the committed OpenAPI document). Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from tl_core.auth import accounts, queries
from tl_core.auth.password import prepare_password
from tl_core.auth.types import AccountKind, AccountView, AgentTokenView, Role
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
    roles: list[Role] = Field(default_factory=lambda: ["user"], min_length=1, max_length=2)
    password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)] | None = Field(
        default=None, description="Never for an `agent` account; it gets a token instead."
    )


class RolesBody(BaseModel):
    """Body of ``PUT /admin/accounts/{account_id}/roles``."""

    model_config = ConfigDict(extra="forbid")

    roles: list[Role] = Field(min_length=1, max_length=2)
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
    # STEPS:
    # 1. `with ctx.backend(True) as uow:` return `queries.list_accounts(uow.conn())`.
    raise NotImplementedError


@router.get(
    "/admin/accounts/{account_id}", operation_id="admin_get_account", response_model=AccountView
)
def get_account(account_id: str, ctx: Ctx, actor: Lister) -> AccountView:
    """One account by id (404 `account_not_found`)."""
    # STEPS:
    # 1. `with ctx.backend(True) as uow:` return `queries.get_account(uow.conn(),
    #    account_id)`.
    raise NotImplementedError


@router.post(
    "/admin/accounts",
    operation_id="admin_create_account",
    response_model=AccountView,
    status_code=201,
)
def create_account(body: CreateAccountBody, ctx: Ctx, actor: Creator) -> AccountView:
    """Create an account. A password must meet the policy (422 `weak_password`); agents get none."""
    # STEPS:
    # 1. `prepared` is None when `body.password` is None, else
    #    `prepare_password(body.password, username=body.username)`. Do this BEFORE the
    #    `with` block: it applies the policy and the slow hash, and no hash may run while
    #    a write transaction is open.
    # 2. `with ctx.backend() as uow:` return `accounts.create_account(uow,
    #    username=body.username, display_name=body.display_name, kind=body.kind,
    #    roles=list(body.roles), password=prepared, by=actor)`.
    raise NotImplementedError


@router.put(
    "/admin/accounts/{account_id}/roles",
    operation_id="admin_set_roles",
    response_model=AccountView,
)
def set_roles(account_id: str, body: RolesBody, ctx: Ctx, actor: RoleSetter) -> AccountView:
    """Replace the roles. The last active admin cannot be demoted (409 `last_admin`)."""
    # STEPS:
    # 1. `with ctx.backend() as uow:` return `accounts.set_roles(uow,
    #    account_id=account_id, roles=list(body.roles), by=actor, reason=body.reason)`.
    raise NotImplementedError


@router.post(
    "/admin/accounts/{account_id}/disable",
    operation_id="admin_disable_account",
    response_model=AccountView,
)
def disable_account(account_id: str, body: ReasonBody, ctx: Ctx, actor: StateSetter) -> AccountView:
    """Disable an account: its sessions and agent tokens stop working. Not the last admin."""
    # STEPS:
    # 1. `with ctx.backend() as uow:` return `accounts.disable(uow, account_id=account_id,
    #    by=actor, reason=body.reason)`.
    raise NotImplementedError


@router.post(
    "/admin/accounts/{account_id}/enable",
    operation_id="admin_enable_account",
    response_model=AccountView,
)
def enable_account(account_id: str, body: ReasonBody, ctx: Ctx, actor: StateSetter) -> AccountView:
    """Enable a disabled account again."""
    # STEPS:
    # 1. `with ctx.backend() as uow:` return `accounts.enable(uow, account_id=account_id,
    #    by=actor, reason=body.reason)`.
    raise NotImplementedError


@router.post(
    "/admin/accounts/{account_id}/password",
    operation_id="admin_reset_password",
    response_model=AccountView,
)
def reset_password(
    account_id: str, body: ResetPasswordBody, ctx: Ctx, actor: Resetter
) -> AccountView:
    """Set a new password without the old one. Ends the account's sessions and clears its lock."""
    # STEPS:
    # 1. `with ctx.backend(True) as uow:` read `account = queries.get_account(uow.conn(),
    #    account_id)` (404 `account_not_found` for an unknown id).
    # 2. After that block (no transaction open) `prepared =
    #    prepare_password(body.new_password, username=account.username)`: the policy and
    #    the slow hash.
    # 3. `with ctx.backend() as uow:` call `accounts.change_password(uow,
    #    account_id=account_id, new_password=prepared, by=actor)`, then in the same block
    #    return `queries.get_account(uow.conn(), account_id)` (it sees the write; the lock
    #    is gone).
    raise NotImplementedError


@router.get("/admin/tokens", operation_id="admin_list_tokens", response_model=list[AgentTokenView])
def list_tokens(
    ctx: Ctx,
    actor: TokenLister,
    account_id: Annotated[str | None, Query(description="Only this agent account.")] = None,
    include_revoked: Annotated[bool, Query()] = True,
) -> list[AgentTokenView]:
    """Agent token metadata. The tokens themselves cannot be read back."""
    # STEPS:
    # 1. `with ctx.backend(True) as uow:` return `queries.list_agent_tokens(uow.conn(),
    #    account_id=account_id, include_revoked=include_revoked)`.
    raise NotImplementedError


@router.post(
    "/admin/tokens", operation_id="admin_issue_token", response_model=IssuedToken, status_code=201
)
def issue_token(body: IssueTokenBody, ctx: Ctx, actor: TokenIssuer) -> IssuedToken:
    """Issue an agent token (default 90 days; `expires_in_days: null` for none). Shown once."""
    # STEPS:
    # 1. `expires` is None when `body.expires_in_days` is None, else `utcnow() +
    #    timedelta(days=body.expires_in_days)`.
    # 2. `with ctx.backend() as uow:` call `view, token = accounts.issue_agent_token(uow,
    #    account_id=body.account_id, label=body.label, expires_at=expires, by=actor)`.
    # 3. Return `IssuedToken(token=token, view=view)` after the block (the commit has
    #    happened).
    raise NotImplementedError


@router.post(
    "/admin/tokens/{token_id}/revoke",
    operation_id="admin_revoke_token",
    response_model=AgentTokenView,
)
def revoke_token(token_id: str, body: ReasonBody, ctx: Ctx, actor: TokenRevoker) -> AgentTokenView:
    """Revoke an agent token at once (404 `agent_token_not_found`, 409 `account_state`)."""
    # STEPS:
    # 1. `with ctx.backend() as uow:` return `accounts.revoke_agent_token(uow,
    #    token_id=token_id, by=actor, reason=body.reason)`.
    raise NotImplementedError
```

`packages/tl-api/src/tl_api/client/admin.py` (the stub you complete):
```python
"""The admin module over HTTP: accounts, roles, passwords and agent tokens (ADR-0009).

Every call needs a token whose account has the ``admin`` role; others get ``ForbiddenError``.
Failures raise the embedded exception classes (``AccountNotFoundError``, ``UsernameTakenError``,
``LastAdminError``, ``WeakPasswordError`` ...). Passwords and tokens never appear in exception
texts. ``issue_agent_token`` returns the token once; it cannot be read back.

STUB (P1-I0-T04): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from collections.abc import Sequence

from tl_core.auth.types import AccountKind, AccountView, AgentTokenView

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.admin import IssuedToken


class AdminApi(ApiClientBase):
    def list_accounts(self) -> list[AccountView]:
        """Every account (``GET /admin/accounts``)."""
        # STEPS:
        # 1. `return self._models(AccountView, self._get_json("/admin/accounts"))`.
        raise NotImplementedError

    def get_account(self, account_id: str) -> AccountView:
        """One account (``GET /admin/accounts/{id}``); the id goes through ``quote``."""
        # STEPS:
        # 1. `return self._model(AccountView,
        #    self._get_json(f"/admin/accounts/{quote(account_id)}"))`.
        raise NotImplementedError

    def create_account(
        self,
        username: str,
        display_name: str,
        *,
        kind: AccountKind = "person",
        roles: Sequence[str] = ("user",),
        password: str | None = None,
    ) -> AccountView:
        """Create an account (``POST /admin/accounts``, 201)."""
        # STEPS:
        # 1. POST `/admin/accounts` with the body shown in the test: username,
        #    display_name, kind, roles (as a list) and password; decode an
        #    `AccountView`.
        raise NotImplementedError

    def set_roles(
        self, account_id: str, roles: Sequence[str], *, reason: str | None = None
    ) -> AccountView:
        """Replace the roles (``PUT /admin/accounts/{id}/roles``)."""
        # STEPS:
        # 1. `self._send("PUT", path, json={"roles": list(roles), "reason":
        #    reason}).json()`, decode an `AccountView`.
        raise NotImplementedError

    def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Disable an account (``POST /admin/accounts/{id}/disable``)."""
        # STEPS:
        # 1. POST `.../disable` with `{"reason": reason}`; decode an `AccountView`.
        raise NotImplementedError

    def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Enable an account (``POST /admin/accounts/{id}/enable``)."""
        # STEPS:
        # 1. POST `.../enable` with `{"reason": reason}`; decode an `AccountView`.
        raise NotImplementedError

    def reset_password(self, account_id: str, new_password: str) -> AccountView:
        """Set a new password without the old one (``POST /admin/accounts/{id}/password``)."""
        # STEPS:
        # 1. POST `.../password` with `{"new_password": new_password}`; decode an
        #    `AccountView`.
        raise NotImplementedError

    def list_agent_tokens(
        self, account_id: str | None = None, *, include_revoked: bool = True
    ) -> list[AgentTokenView]:
        """Agent token metadata (``GET /admin/tokens``)."""
        # STEPS:
        # 1. GET `/admin/tokens` with params `account_id` and `include_revoked`
        #    (`_get_json` drops None); decode with `self._models(AgentTokenView,
        #    data)`.
        raise NotImplementedError

    def issue_agent_token(
        self, account_id: str, label: str, *, expires_in_days: int | None = 90
    ) -> tuple[AgentTokenView, str]:
        """Issue an agent token (``POST /admin/tokens``, 201). Returns the view and the token."""
        # STEPS:
        # 1. POST `/admin/tokens` with `account_id`, `label`, `expires_in_days`;
        #    decode `IssuedToken` and return `(issued.view, issued.token)`.
        raise NotImplementedError

    def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView:
        """Revoke an agent token (``POST /admin/tokens/{id}/revoke``)."""
        # STEPS:
        # 1. POST `/admin/tokens/{quote(token_id)}/revoke` with `{"reason": reason}`;
        #    decode an `AgentTokenView`.
        raise NotImplementedError
```

The service functions the routes call (`packages/tl-core/src/tl_core/auth/accounts.py` and `queries.py`, already implemented and reviewed; do not change them):
```python
def prepare_password(password: str, *, username: str | None = None, enforce_policy: bool = True) -> PreparedPassword: ...  # tl_core.auth.password; WeakPasswordError
def create_account(uow, *, username, display_name, kind, roles, password: PreparedPassword | None, by, clock=utcnow, allow_demo=False) -> AccountView: ...
def set_roles(uow, *, account_id, roles, by, reason) -> AccountView: ...
def disable(uow, *, account_id, by, reason) -> AccountView: ...
def enable(uow, *, account_id, by, reason) -> AccountView: ...
def change_password(uow, *, account_id, new_password: PreparedPassword, by, clock=utcnow, forced=None) -> None: ...  # an admin reset; no current password
def issue_agent_token(uow, *, account_id, label, expires_at, by, clock=utcnow) -> tuple[AgentTokenView, str]: ...
def revoke_agent_token(uow, *, token_id, by, reason) -> AgentTokenView: ...
def list_accounts(conn) -> list[AccountView]: ...   # queries
def get_account(conn, account_id) -> AccountView: ...  # queries; AccountNotFoundError
def list_agent_tokens(conn, *, account_id=None, include_revoked=True) -> list[AgentTokenView]: ...  # queries
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/admin.py`
- `packages/tl-api/src/tl_api/client/admin.py`
- `packages/tl-api/src/tl_api/client/proposals.py` (an example of the client style)
- `docs/tickets/P1-I0/provided/t04-test_api_admin.py.txt`
- `docs/tickets/P1-I0/provided/t04-test_client_admin.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/admin.py` (bodies only)
- `packages/tl-api/src/tl_api/client/admin.py` (bodies only)
- `packages/tl-api/tests/test_api_admin.py` (create, copy of the provided file)
- `packages/tl-api/tests/test_client_admin.py` (create, copy of the provided file)
- `docs/reports/P1-I0/P1-I0-T04.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I0/provided/t04-test_api_admin.py.txt packages/tl-api/tests/test_api_admin.py` and `cp docs/tickets/P1-I0/provided/t04-test_client_admin.py.txt packages/tl-api/tests/test_client_admin.py`.
2. Fill the eleven route bodies and the ten client bodies by their `STEPS` comments.
3. Delete the `STUB` paragraph, the `STEPS` comments and the `# ruff: noqa: F401` line in both modules.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-api && uv run ruff check packages/tl-api
uv run pytest packages/tl-api/tests/test_api_admin.py packages/tl-api/tests/test_client_admin.py -q
uv run pytest packages/tl-api -q
uv run python -m tl_api.openapi --check
just check
```
Expected: 45 passed in the first pytest command (39 + 6 cases); the whole `packages/tl-api` suite passes; the OpenAPI check reports no drift; `just check` is clean.

## Tests to add
- `packages/tl-api/tests/test_api_admin.py` (25 test functions, 39 cases, provided): every admin route refuses non-admins (users, agents, dev tokens) and the unauthenticated; listing, creating (and every refusal), roles and the last-admin rule, disable and enable, password reset, agent token issue, expiry, listing and revocation; the ledger holds actors and no secret; no password is hashed inside a write transaction.
- `packages/tl-api/tests/test_client_admin.py` (6 test functions, 6 cases, provided): the ten client calls and the exception classes they raise.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. Paste the decisive lines of the five acceptance commands. State that no `try`/`except` was added and that no log line or exception text includes a password or a token.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and the fix needs a change outside the two modules (a service, `tl_api/auth.py`, `errors.py`, `app.py`).
- Stop if `uv run python -m tl_api.openapi --check` reports drift: you changed something that reaches the document.
- Stop if a step seems to ask you to decide who may do what: the guards and the `Authorizer` already do.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
