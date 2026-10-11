# P1-I0-T03 — `/auth/*` routes and the client's sign-in calls

Status: ready
Tier: haiku
Labels: api
Depends on: P1-I0-S2b, S2c and the review fixes F1 to F3 (on `p1/i0a`)
Branch: `p1/i0a-t03-api-auth`

## Goal
The REST API can sign a person in and out and say who a token belongs to: `POST /auth/sign-in` (open: it is the only route that needs no token), `POST /auth/sign-out`, `GET /auth/me` and `POST /auth/password` (change your own password). The HTTP client gains the matching calls: the function `tl_api.client.auth.sign_in(base_url, username, password)` and the `ApiClient` methods `sign_out()`, `whoami()` and `change_own_password(current, new)`. The module `routes/auth.py` has the router, the request and response models and every route's decorator, parameters and docstring (they make the committed OpenAPI document); the four route functions raise `NotImplementedError`. `client/auth.py` has the function and three methods the same way. Both modules are already wired into the app and `ApiClient`. Two provided test files (33 test functions, 41 cases) must pass and `docs/reference/openapi.json` must not change.

## Brief references (pasted)
> **Brief 11.1 Auth.** OAuth2/OIDC bearer tokens; API keys for service accounts; scopes per module.
> **ADR-0008 (owner).** Username and password now, behind an identity seam; two roles `admin` and `user`; the admin module manages accounts, roles and agent service tokens and is reachable from the CLI, API and TUI; service tokens for MCP agents are issued per agent by an admin (`agent:<name>`); the propose-only rule stays.
> **ADR-0009 (the design, already implemented in `tl_core.auth`).** Session tokens are `tls_` + 256 random bits, stored only as SHA-256, 12 hours, deleted on sign-out, disable and password change. Agent tokens are `tla_` + 256 random bits, stored as a hash, shown once, optional expiry, revocable at once. Five failed sign-ins within 15 minutes lock a name for 15 minutes (doubling to 24 hours); the counters are keyed by the normalised username whether or not the account exists, so an unknown name locks like a real one and the response never tells them apart; a locked name is refused before any password is checked. A disabled account is reported (403) only to the right password. Passwords: 12 to 128 characters, a common-password list, no composition rules (422 `weak_password` names the rule, never the password). Account events are ledger events with metadata only; every secret lives in `auth_*` operational tables. The last active admin cannot be disabled or demoted (409 `last_admin`). `admin.*` actions need a human admin: the `Authorizer` refuses `user`s and every `agent:*` principal with 403 `forbidden`.

### Specification
Each route is one call into `tl_core.auth.sessions` (ADR-0009), as the `STEPS` comment in each body says. `sessions.sign_in` returns `(Principal, token)`; the route wraps them in `SignInOut`. Sign-in has no `guard`: `/auth/sign-in` is listed in `tl_api.auth.OPEN_PATHS`, so the authentication middleware lets it through and the route authenticates by the credentials in the body. Every failure is already a mapped error row in `tl_api/errors.py` (401 `invalid_credentials`, 423 `account_locked`, 403 `account_disabled`, 422 `weak_password`, 403 `forbidden`); no route catches anything.

The other three routes use `guard(...)` for the token check and `Me = Depends(current_principal)` for the whole principal. Sign-out deletes only the session of the token in the `Authorization` header (`bearer_token(request.scope["headers"])`); an agent or dev token answers 204 and nothing changes. Changing a password goes through `sessions.change_own_password` (not `accounts.change_password`), because that function counts a wrong current password towards the lockout; agents and dev tokens have no password and get `ForbiddenError`.

The client: `sign_in` is a function because nothing is authenticated yet. With `http=` it sends the relative path `/auth/sign-in` on that client (the same convention as `ApiClientBase`), so the provided tests can pass a Starlette `TestClient`. Errors become the embedded exception classes through `ApiClientBase.error_from(response)`.

Already done for you, with tests in the provided files, so do not build it again: the body limit on `/auth/*` (16 KiB, 413 `payload_too_large`, in `BodyLimitMiddleware`), usernames are never stripped, input with a NUL or a lone surrogate is invalid credentials (the service, after the usual hash) or a 422 (the JSON parser), and a busy hash gate is 503 `auth_busy` with `Retry-After` (the app's error handler). Your bodies only call the services; they must not touch the strings.

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
`packages/tl-api/src/tl_api/routes/auth.py` (the stub you complete):
```python
"""Sign-in, sign-out, who am I, and changing your own password (ADR-0009, brief 11.1).

Thin: one `tl_core.auth` call per route. `POST /auth/sign-in` is the only route that needs no
token (`tl_api.auth.OPEN_PATHS`); every failure is a mapped error (401 `invalid_credentials`, 423
`account_locked`, 403 `account_disabled`, 422 `weak_password`) and no route catches anything. No
body, header, log line or error text may hold a password or a token except the one token that
`sign_in` returns to its caller.

STUB (P1-I0-T03): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final (they make the committed OpenAPI document). Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from tl_core.auth import sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.types import Principal

from tl_api.auth import bearer_token, current_principal, guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["auth"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Me = Annotated[Principal, Depends(current_principal)]
MAX_SECRET = 1024


class SignInBody(BaseModel):
    """Body of ``POST /auth/sign-in``."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, Field(min_length=1, max_length=256)]
    password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]


class SignInOut(BaseModel):
    """The session token (shown once), how long it lives, and who it belongs to."""

    token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the session ends.")
    principal: Principal

    def __repr__(self) -> str:
        return f"SignInOut(principal={self.principal.actor!r}, token=<hidden>)"

    __str__ = __repr__


class PasswordBody(BaseModel):
    """Body of ``POST /auth/password``."""

    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]
    new_password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]


@router.post("/auth/sign-in", operation_id="sign_in", response_model=SignInOut)
def sign_in(body: SignInBody, ctx: Ctx) -> SignInOut:
    """Sign in with a username and password; answers a session token for `Authorization: Bearer`.

    The same 401 `invalid_credentials` answers an unknown user and a wrong password. After repeated
    failures the name is locked: 423 `account_locked` with `locked_until`, even for the right
    password. A disabled account answers 403 `account_disabled` only to the right password.
    """
    # STEPS:
    # 1. Call `sessions.sign_in(ctx.backend, username=body.username,
    #    password=body.password)`.
    # 2. Return `SignInOut(token=token,
    #    expires_in=int(sessions.SESSION_TTL.total_seconds()), principal=principal)`.
    # 3. Do not catch anything: the errors are mapped rows.
    raise NotImplementedError


@router.post("/auth/sign-out", operation_id="sign_out", status_code=204)
def sign_out(
    request: Request,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("auth.sign_out"))],
) -> Response:
    """End the session of the token in `Authorization`. Other tokens (agent, dev) are unaffected."""
    # STEPS:
    # 1. Read the token with `bearer_token(request.scope["headers"])`.
    # 2. When it is not None call `sessions.sign_out(ctx.backend, token=token)` (it
    #    ignores tokens that are not sessions).
    # 3. Return `Response(status_code=204)`.
    raise NotImplementedError


@router.get("/auth/me", operation_id="whoami", response_model=Principal)
def whoami(
    me: Me,
    actor: Annotated[str, Depends(guard("auth.me"))],
) -> Principal:
    """Who the token belongs to: actor, account id, kind, roles and how it authenticated."""
    # STEPS:
    # 1. Return `me`: the dependency already resolved the principal.
    raise NotImplementedError


@router.post("/auth/password", operation_id="change_own_password", status_code=204)
def change_own_password(
    body: PasswordBody,
    me: Me,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("auth.password"))],
) -> Response:
    """Change your own password. Every session of the account ends, this one included.

    A wrong current password is 401 `invalid_credentials` and counts towards the lockout. Agents
    and dev tokens have no password: 403 `forbidden`.
    """
    # STEPS:
    # 1. If `me.kind == "agent"` or `me.via == "dev_token"` raise `ForbiddenError("this
    #    token has no password to change")`.
    # 2. Call `sessions.change_own_password(ctx.backend, account_id=me.account_id,
    #    current_password=body.current_password, new_password=body.new_password)`.
    # 3. Return `Response(status_code=204)`.
    raise NotImplementedError
```

`packages/tl-api/src/tl_api/client/auth.py` (the stub you complete):
```python
"""Sign-in and the caller's own account over HTTP (ADR-0009).

``sign_in`` is a function, not a method: nothing is authenticated yet, so there is no client to
call it on. It answers the session token once; give it to ``ApiClient(base_url, out.token)``.
Failures raise the embedded exception classes (``InvalidCredentialsError``,
``AccountLockedError`` with ``locked_until``, ``AccountDisabledError``). Nothing here logs or
includes a password or a token in an exception text.

STUB (P1-I0-T03): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

import httpx2
from tl_core.auth.types import Principal

from tl_api.client.base import DEFAULT_TIMEOUT_S, ApiClientBase, ApiUnavailableError
from tl_api.routes.auth import SignInOut


def sign_in(
    base_url: str,
    username: str,
    password: str,
    *,
    http: httpx2.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> SignInOut:
    """``POST /auth/sign-in`` with a username and password.

    Use ``http`` when given (tests pass a Starlette ``TestClient``; like ``ApiClient`` it sends the
    relative path ``/auth/sign-in``), else a client for ``base_url`` that is closed afterwards.
    A response of 400 or above raises ``ApiClientBase.error_from(response)``; a transport failure
    raises ``ApiUnavailableError``.
    """
    # STEPS:
    # 1. Use `http` when given, else build `httpx2.Client(base_url=base_url.rstrip("/"),
    #    timeout=timeout)` and close it in a `finally`.
    # 2. POST the relative path `/auth/sign-in` with `json={"username": username,
    #    "password": password}` and no Authorization header.
    # 3. Wrap `httpx2.TransportError` in `ApiUnavailableError(exc)` (`raise ... from
    #    exc`).
    # 4. For a status of 400 or more `raise ApiClientBase.error_from(response)`.
    # 5. Return `SignInOut.model_validate(response.json())`.
    raise NotImplementedError


class AuthApi(ApiClientBase):
    def sign_out(self) -> None:
        """End this client's session (``POST /auth/sign-out``, 204)."""
        # STEPS:
        # 1. Read the token with `bearer_token(request.scope["headers"])`.
        # 2. When it is not None call `sessions.sign_out(ctx.backend, token=token)`
        #    (it ignores tokens that are not sessions).
        # 3. Return `Response(status_code=204)`.
        raise NotImplementedError

    def whoami(self) -> Principal:
        """Who the token belongs to (``GET /auth/me``)."""
        # STEPS:
        # 1. Return `me`: the dependency already resolved the principal.
        raise NotImplementedError

    def change_own_password(self, current_password: str, new_password: str) -> None:
        """Change your own password (``POST /auth/password``, 204). Every session then ends."""
        # STEPS:
        # 1. If `me.kind == "agent"` or `me.via == "dev_token"` raise
        #    `ForbiddenError("this token has no password to change")`.
        # 2. Call `sessions.change_own_password(ctx.backend, account_id=me.account_id,
        #    current_password=body.current_password, new_password=body.new_password)`.
        # 3. Return `Response(status_code=204)`.
        raise NotImplementedError
```

The service functions the routes call (`packages/tl-core/src/tl_core/auth/sessions.py`, already implemented and reviewed; do not change them):
```python
def sign_in(backend: UowFactory, *, username: str, password: str, clock: Clock = utcnow) -> tuple[Principal, str]: ...
def sign_out(backend: UowFactory, *, token: str) -> None: ...  # idempotent; ignores non-session tokens
def change_own_password(backend: UowFactory, *, account_id: str, current_password: str, new_password: str, clock: Clock = utcnow) -> None: ...
SESSION_TTL = timedelta(hours=12)
```
`ctx.backend` is a `Backend` and satisfies `UowFactory`. `tl_api.auth` already provides `guard`, `current_principal` and `bearer_token(headers)`.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/auth.py`
- `packages/tl-api/src/tl_api/client/auth.py`
- `packages/tl-api/src/tl_api/client/proposals.py` (an example of the client style)
- `docs/tickets/P1-I0/provided/t03-test_api_auth.py.txt`
- `docs/tickets/P1-I0/provided/t03-test_client_auth.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/auth.py` (bodies only)
- `packages/tl-api/src/tl_api/client/auth.py` (bodies only)
- `packages/tl-api/tests/test_api_auth.py` (create, copy of the provided file)
- `packages/tl-api/tests/test_client_auth.py` (create, copy of the provided file)
- `docs/reports/P1-I0/P1-I0-T03.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I0/provided/t03-test_api_auth.py.txt packages/tl-api/tests/test_api_auth.py` and `cp docs/tickets/P1-I0/provided/t03-test_client_auth.py.txt packages/tl-api/tests/test_client_auth.py`.
2. Fill the four route bodies and the four client bodies by their `STEPS` comments.
3. Delete the `STUB` paragraph, the `STEPS` comments and the `# ruff: noqa: F401` line in both modules.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-api && uv run ruff check packages/tl-api
uv run pytest packages/tl-api/tests/test_api_auth.py packages/tl-api/tests/test_client_auth.py -q
uv run pytest packages/tl-api -q
uv run python -m tl_api.openapi --check
just check
```
Expected: 41 passed in the first pytest command (31 + 10 cases); the whole `packages/tl-api` suite passes; the OpenAPI check reports no drift; `just check` is clean.

## Tests to add
- `packages/tl-api/tests/test_api_auth.py` (23 test functions, 31 cases, provided): sign-in answers, enumeration resistance, lockout, disabled accounts, malformed bodies, NUL and surrogates, no stripping, the 413 body limit, the 503 busy answer, log hygiene, sign-out, `/auth/me` for every token kind, own password change.
- `packages/tl-api/tests/test_client_auth.py` (10 test functions, 10 cases, provided): the client calls and the exception classes they raise.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. Paste the decisive lines of the five acceptance commands. State that no `try`/`except` was added and that no log line or exception text includes a password or a token.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and the fix needs a change outside the two modules (a service, `tl_api/auth.py`, `errors.py`, `app.py`).
- Stop if `uv run python -m tl_api.openapi --check` reports drift: you changed something that reaches the document.
- Stop if the ticket seems to ask for password or token handling beyond calling the services listed above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
